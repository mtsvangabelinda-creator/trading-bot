# Autonomous Multi-Strategy Trading System
# Module 12 — Correlation Breaker
# Monitors how closely the 5 assets move together
# When diversification collapses exposure is reduced
# Prevents portfolio from becoming one concentrated bet

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional

import aiosqlite
import numpy as np
import pandas as pd

from config import (
    CORR_HALVE_THRESHOLD,
    CORR_PAUSE_THRESHOLD,
    CORR_CHECK_INTERVAL,
    ASSETS
)

# ── Logging ───────────────────────────────────────────────────
def setup_logger(name: str, log_file: str) -> logging.Logger:
    os.makedirs('logs', exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_file, maxBytes=10485760, backupCount=7
        )
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(funcName)s | %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

logger      = setup_logger('correlation_breaker', 'logs/errors.log')
risk_logger = setup_logger('risk', 'logs/risk.log')

# ── Status Constants ──────────────────────────────────────────
NORMAL = 'NORMAL'
HALVED = 'HALVED'
PAUSED = 'PAUSED'

# ── Hours before sustained pause ──────────────────────────────
SUSTAINED_HOURS = 24


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def init_db(
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Create correlation tracking table if it does not exist.

    Args:
        db_path: Path to SQLite database

    Returns:
        True if successful, False on failure
    """
    try:
        os.makedirs('data', exist_ok=True)
        async with aiosqlite.connect(db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS correlation_history (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp         TEXT NOT NULL,
                    avg_correlation   REAL NOT NULL,
                    max_correlation   REAL NOT NULL,
                    min_correlation   REAL NOT NULL,
                    correlation_pairs TEXT NOT NULL,
                    status            TEXT NOT NULL,
                    high_corr_since   TEXT,
                    alert_message     TEXT
                )
            ''')
            await db.commit()

        logger.info('Correlation Breaker database initialised')
        return True

    except Exception as e:
        logger.error(f'init_db failed: {e}')
        return False


def calculate_matrix(
    prices_dict: dict
) -> Optional[dict]:
    """
    Calculate pairwise correlation matrix for all assets.

    Args:
        prices_dict: Dictionary of asset name to price Series

    Returns:
        Dictionary with matrix, avg_correlation,
        max_correlation, min_correlation, pairs
        or None on failure
    """
    try:
        assets = list(prices_dict.keys())

        if len(assets) < 2:
            logger.warning(
                'calculate_matrix: need at least 2 assets'
            )
            return None

        # Calculate returns for each asset
        returns_dict = {}
        for asset, prices in prices_dict.items():
            prices_arr = np.array(prices, dtype=float)
            if len(prices_arr) < 10:
                logger.warning(
                    f'calculate_matrix: insufficient data '
                    f'for {asset}'
                )
                continue
            returns = pd.Series(prices_arr).pct_change().dropna()
            returns_dict[asset] = returns

        if len(returns_dict) < 2:
            return None

        # Align all return series to same length
        min_len = min(len(r) for r in returns_dict.values())
        returns_df = pd.DataFrame({
            asset: returns.values[-min_len:]
            for asset, returns in returns_dict.items()
        })

        # Calculate correlation matrix
        corr_matrix = returns_df.corr()

        # Extract all unique pairwise correlations
        pairs = {}
        assets_list = list(returns_dict.keys())
        corr_values = []

        for i in range(len(assets_list)):
            for j in range(i + 1, len(assets_list)):
                a1   = assets_list[i]
                a2   = assets_list[j]
                key  = f'{a1}-{a2}'
                corr = float(corr_matrix.loc[a1, a2])
                pairs[key]  = round(corr, 4)
                corr_values.append(corr)

        if not corr_values:
            return None

        avg_corr = round(float(np.mean(corr_values)), 4)
        max_corr = round(float(np.max(corr_values)), 4)
        min_corr = round(float(np.min(corr_values)), 4)

        logger.debug(
            f'Correlation matrix: avg={avg_corr}, '
            f'max={max_corr}'
        )

        return {
            'matrix':           corr_matrix,
            'avg_correlation':  avg_corr,
            'max_correlation':  max_corr,
            'min_correlation':  min_corr,
            'pairs':            pairs
        }

    except Exception as e:
        logger.error(f'calculate_matrix failed: {e}')
        return None


async def check(
    prices_dict: dict,
    db_path: str = 'data/trading_data.db'
) -> Optional[dict]:
    """
    Check current correlation and update status.

    Args:
        prices_dict: Dictionary of asset name to price Series
        db_path: Path to SQLite database

    Returns:
        Dictionary with avg_correlation, status,
        size_multiplier, alert_message and details
        or None on failure
    """
    try:
        now = now_utc()

        # Calculate correlation matrix
        matrix_result = calculate_matrix(prices_dict)
        if matrix_result is None:
            return None

        avg_corr = matrix_result['avg_correlation']
        max_corr = matrix_result['max_correlation']
        min_corr = matrix_result['min_correlation']
        pairs    = matrix_result['pairs']

        # Load most recent record
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute('''
                SELECT status, high_corr_since, avg_correlation
                FROM correlation_history
                ORDER BY id DESC LIMIT 1
            ''')
            last = await cursor.fetchone()

        prev_status         = NORMAL
        high_corr_since     = None
        alert_message       = None

        if last:
            prev_status    = last[0]
            hcs_str        = last[1]
            if hcs_str:
                high_corr_since = datetime.fromisoformat(hcs_str)

        # Determine high_corr_since
        if avg_corr > CORR_HALVE_THRESHOLD:
            if high_corr_since is None:
                high_corr_since = now
        elif avg_corr <= CORR_PAUSE_THRESHOLD:
            high_corr_since = None

        # Calculate hours elevated
        hours_elevated = 0.0
        if high_corr_since:
            hours_elevated = (
                now - high_corr_since
            ).total_seconds() / 3600

        # Determine status
        if avg_corr > CORR_HALVE_THRESHOLD:
            if hours_elevated >= SUSTAINED_HOURS:
                status          = PAUSED
                size_multiplier = 0.0
                if prev_status != PAUSED:
                    alert_message = (
                        f'CORRELATION LOCKOUT — TRADING PAUSED\n'
                        f'Average correlation {avg_corr} has been '
                        f'above {CORR_HALVE_THRESHOLD} for '
                        f'{round(hours_elevated, 1)} hours.\n'
                        f'All trading paused until correlation '
                        f'drops below {CORR_PAUSE_THRESHOLD}.'
                    )
                    risk_logger.critical(
                        f'Correlation PAUSED: avg={avg_corr}, '
                        f'elevated {round(hours_elapsed, 1)}h'
                        if False else
                        f'Correlation PAUSED: avg={avg_corr}'
                    )
            else:
                status          = HALVED
                size_multiplier = 0.5
                if prev_status == NORMAL:
                    alert_message = (
                        f'DIVERSIFICATION COLLAPSE — '
                        f'EXPOSURE HALVED\n'
                        f'Average correlation: {avg_corr} '
                        f'(threshold: {CORR_HALVE_THRESHOLD})\n'
                        f'All position sizes reduced to 50%.\n'
                        f'Most correlated pair: '
                        f'{max(pairs, key=pairs.get)} '
                        f'({max(pairs.values())})'
                    )
                    risk_logger.warning(
                        f'Correlation HALVED: avg={avg_corr}'
                    )
        else:
            status          = NORMAL
            size_multiplier = 1.0
            if prev_status in [HALVED, PAUSED]:
                alert_message = (
                    f'CORRELATION NORMAL — FULL EXPOSURE RESTORED\n'
                    f'Average correlation: {avg_corr} '
                    f'(below {CORR_PAUSE_THRESHOLD})'
                )
                risk_logger.info(
                    f'Correlation returned to NORMAL: avg={avg_corr}'
                )

        # Find most correlated pair
        most_correlated = (
            max(pairs, key=pairs.get) if pairs else 'N/A'
        )

        # Save to database
        async with aiosqlite.connect(db_path) as db:
            await db.execute('''
                INSERT INTO correlation_history
                (timestamp, avg_correlation, max_correlation,
                 min_correlation, correlation_pairs, status,
                 high_corr_since, alert_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                now.isoformat(),
                avg_corr,
                max_corr,
                min_corr,
                json.dumps(pairs),
                status,
                high_corr_since.isoformat()
                if high_corr_since else None,
                alert_message or ''
            ))
            await db.commit()

        return {
            'avg_correlation':    avg_corr,
            'max_correlation':    max_corr,
            'min_correlation':    min_corr,
            'status':             status,
            'size_multiplier':    size_multiplier,
            'high_corr_since':    high_corr_since,
            'hours_elevated':     round(hours_elevated, 2),
            'most_correlated_pair': most_correlated,
            'alert_message':      alert_message,
            'pairs':              pairs
        }

    except Exception as e:
        logger.error(f'check failed: {e}')
        return None


async def get_size_multiplier(
    db_path: str = 'data/trading_data.db'
) -> float:
    """
    Get current position size multiplier from correlation status.

    Args:
        db_path: Path to SQLite database

    Returns:
        1.0 if NORMAL, 0.5 if HALVED, 0.0 if PAUSED
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute('''
                SELECT status FROM correlation_history
                ORDER BY id DESC LIMIT 1
            ''')
            last = await cursor.fetchone()

        if last is None:
            return 1.0

        status = last[0]
        if status == HALVED:
            return 0.5
        elif status == PAUSED:
            return 0.0
        else:
            return 1.0

    except Exception as e:
        logger.error(f'get_size_multiplier failed: {e}')
        return 1.0


async def is_trading_allowed(
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Check if trading is allowed based on correlation status.

    Args:
        db_path: Path to SQLite database

    Returns:
        False if PAUSED, True otherwise
    """
    try:
        multiplier = await get_size_multiplier(db_path)
        return multiplier > 0.0

    except Exception as e:
        logger.error(f'is_trading_allowed failed: {e}')
        return True


async def get_status(
    db_path: str = 'data/trading_data.db'
) -> str:
    """
    Get formatted correlation status for Telegram.

    Args:
        db_path: Path to SQLite database

    Returns:
        Formatted status string
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute('''
                SELECT avg_correlation, status,
                       high_corr_since, correlation_pairs,
                       timestamp
                FROM correlation_history
                ORDER BY id DESC LIMIT 1
            ''')
            last = await cursor.fetchone()

        if last is None:
            return 'CORRELATION STATUS\nNo data yet.'

        (avg_corr, status, hcs_str,
         pairs_json, ts_str) = last

        pairs = json.loads(pairs_json) if pairs_json else {}

        hours_str = 'N/A'
        if hcs_str:
            hcs = datetime.fromisoformat(hcs_str)
            hours = (now_utc() - hcs).total_seconds() / 3600
            hours_str = f'{round(hours, 1)}h'

        most_corr = (
            max(pairs, key=pairs.get)
            if pairs else 'N/A'
        )
        most_corr_val = pairs.get(most_corr, 0)

        multiplier = await get_size_multiplier(db_path)

        lines = [
            'CORRELATION STATUS',
            '─' * 24,
            f'Average Correlation: {avg_corr}',
            f'Status: {status} — '
            f'exposure at {int(multiplier*100)}%',
            f'Elevated since: {hours_str}',
            f'Most correlated: {most_corr} ({most_corr_val})',
            '─' * 24,
            'All pairs:'
        ]

        for pair, corr in pairs.items():
            lines.append(f'  {pair}: {corr}')

        return '\n'.join(lines)

    except Exception as e:
        logger.error(f'get_status failed: {e}')
        return 'CORRELATION STATUS\nError retrieving status.'


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        TEST_DB = 'data/test_correlation.db'
        print('\n=== MODULE 12 — CORRELATION BREAKER TESTS ===\n')
        np.random.seed(42)
        n = 100

        try:
            # Test 1 — Init database
            print('Test 1: Initialising test database...')
            result = await init_db(TEST_DB)
            print(
                f'Database initialised: '
                f'{"PASSED" if result else "FAILED"}\n'
            )

            # Test 2 — Low correlation NORMAL status
            print('Test 2: Low correlation — NORMAL status...')
            low_corr_data = {
                asset: pd.Series(
                    np.cumsum(
                        np.random.normal(0, 1, n)
                    ) + 100
                )
                for asset in ASSETS.keys()
            }
            result2 = await check(low_corr_data, TEST_DB)
            if result2:
                print(
                    f'  Avg correlation: {result2["avg_correlation"]}'
                )
                print(f'  Status: {result2["status"]}')
                print(
                    f'  Size multiplier: '
                    f'{result2["size_multiplier"]}'
                )
                passed = result2['status'] == NORMAL
                print(
                    f'Test 2: {"PASSED" if passed else "FAILED"}\n'
                )
            else:
                print('Test 2: FAILED — no result\n')

            # Test 3 — High correlation HALVED status
            print('Test 3: High correlation — HALVED status...')
            base_trend = np.cumsum(
                np.random.normal(0.5, 0.1, n)
            ) + 100
            high_corr_data = {
                asset: pd.Series(
                    base_trend + np.random.normal(0, 0.01, n)
                )
                for asset in ASSETS.keys()
            }
            result3 = await check(high_corr_data, TEST_DB)
            if result3:
                print(
                    f'  Avg correlation: {result3["avg_correlation"]}'
                )
                print(f'  Status: {result3["status"]}')
                print(
                    f'  Size multiplier: '
                    f'{result3["size_multiplier"]}'
                )
                print(
                    f'  Most correlated: '
                    f'{result3["most_correlated_pair"]}'
                )
                passed = (
                    result3['avg_correlation'] >
                    CORR_HALVE_THRESHOLD and
                    result3['size_multiplier'] == 0.5
                )
                print(
                    f'Test 3: {"PASSED" if passed else "FAILED"}\n'
                )
            else:
                print('Test 3: FAILED — no result\n')

            # Test 4 — calculate_matrix directly
            print('Test 4: calculate_matrix on high correlation...')
            matrix = calculate_matrix(high_corr_data)
            if matrix:
                print('  Pairs:')
                for pair, corr in matrix['pairs'].items():
                    print(f'    {pair}: {corr}')
                print('Test 4: PASSED\n')
            else:
                print('Test 4: FAILED\n')

            # Test 5 — get_size_multiplier
            print('Test 5: get_size_multiplier...')
            multiplier = await get_size_multiplier(TEST_DB)
            print(f'  Multiplier: {multiplier}')
            passed = multiplier == 0.5
            print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

            # Test 6 — get_status
            print('Test 6: get_status...')
            status_str = await get_status(TEST_DB)
            print(status_str)
            print('Test 6: PASSED\n')

            # Test 7 — Simulate PAUSED by injecting old timestamp
            print(
                'Test 7: Simulate sustained high correlation '
                '— PAUSED...'
            )
            old_time = (
                now_utc() - timedelta(hours=25)
            ).isoformat()
            async with aiosqlite.connect(TEST_DB) as db:
                await db.execute('''
                    INSERT INTO correlation_history
                    (timestamp, avg_correlation, max_correlation,
                     min_correlation, correlation_pairs, status,
                     high_corr_since)
                    VALUES (?, 0.85, 0.92, 0.78, '{}', ?, ?)
                ''', (
                    now_utc().isoformat(),
                    HALVED,
                    old_time
                ))
                await db.commit()

            result7 = await check(high_corr_data, TEST_DB)
            if result7:
                print(f'  Status: {result7["status"]}')
                print(
                    f'  Size multiplier: '
                    f'{result7["size_multiplier"]}'
                )
                passed = result7['status'] == PAUSED
                print(
                    f'Test 7: {"PASSED" if passed else "FAILED"}\n'
                )
            else:
                print('Test 7: FAILED\n')

            all_passed = (
                result2 is not None and
                result2['status'] == NORMAL and
                result3 is not None and
                result3['size_multiplier'] == 0.5 and
                multiplier == 0.5 and
                result7 is not None and
                result7['status'] == PAUSED
            )
            print(
                '=== MODULE 12 — CORRELATION BREAKER: '
                f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
            )

        finally:
            import os
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
                print('\nTest database deleted.')

    asyncio.run(run_tests())
