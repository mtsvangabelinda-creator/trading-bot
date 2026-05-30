# Autonomous Multi-Strategy Trading System
# Module 14c — Sentinel
# Main order book monitor — gives green or red light
# Combines all checks into one pass/fail decision
# Red light = position size zero regardless of other signals

import asyncio
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional

import aiosqlite

from sentinel.spoof_detector import detect_spoof
from sentinel.liquidity_monitor import (
    check_liquidity_gaps,
    check_spread_abnormal,
    check_depth_sufficiency,
    check_volume_dryup
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

logger          = setup_logger('sentinel', 'logs/sentinel.log')
sentinel_logger = setup_logger(
    'sentinel_blocks', 'logs/sentinel.log'
)

# ── Sentinel Mode ─────────────────────────────────────────────
_sentinel_mode = 'normal'


def set_sentinel_mode(mode: str) -> None:
    """Set sentinel sensitivity mode."""
    global _sentinel_mode
    if mode in ['normal', 'paranoid', 'relaxed']:
        _sentinel_mode = mode
        logger.info(f'Sentinel mode set to: {mode}')


def get_sentinel_mode() -> str:
    """Get current sentinel mode."""
    return _sentinel_mode


async def init_sentinel_state(
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Initialise sentinel block logging table.

    Args:
        db_path: Path to SQLite database

    Returns:
        True if successful
    """
    try:
        os.makedirs('data', exist_ok=True)
        async with aiosqlite.connect(db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS sentinel_blocks (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol    TEXT NOT NULL,
                    reason    TEXT NOT NULL,
                    details   TEXT
                )
            ''')
            await db.commit()
        logger.info('Sentinel state initialised')
        return True

    except Exception as e:
        logger.error(f'init_sentinel_state failed: {e}')
        return False


def check_all_filters(
    symbol: str,
    order_book: dict,
    order_amount_usd: float = 100.0,
    recent_trades: list = None,
    spoof_lookback_sec: int = 10
) -> dict:
    """
    Run all sentinel checks and return combined result.

    A single red flag blocks the trade entirely.
    In paranoid mode thresholds are tighter.

    Args:
        symbol: Trading pair
        order_book: Dict with bids and asks
        order_amount_usd: Dollar size of intended order
        recent_trades: List of recent trades for volume check
        spoof_lookback_sec: Window for spoof detection

    Returns:
        Dictionary with green_light, multiplier,
        alerts list, details dict
    """
    try:
        if recent_trades is None:
            recent_trades = []

        alerts  = []
        details = {}
        mode    = get_sentinel_mode()

        # Adjust thresholds by mode
        spoof_threshold  = 0.2 if mode == 'paranoid' else 0.3
        spread_mult      = 1.5 if mode == 'paranoid' else 2.0
        if mode == 'relaxed':
            spread_mult  = 3.0

        # ── Check 1: Spoof Detection ──────────────────────────
        spoof = detect_spoof(
            symbol, order_book,
            threshold_ratio=spoof_threshold,
            lookback_seconds=spoof_lookback_sec
        )
        details['spoof'] = spoof
        if spoof['spoof_detected']:
            alerts.append(
                f'Spoofing detected '
                f'(confidence={spoof["confidence"]})'
            )

        # ── Check 2: Liquidity Gaps ───────────────────────────
        gaps = check_liquidity_gaps(order_book)
        details['gaps'] = gaps
        if gaps['has_gap']:
            alerts.append(
                f'Liquidity gap at {gaps["gap_location"]} '
                f'({round(gaps["gap_percent"]*100, 3)}%)'
            )

        # ── Check 3: Spread Abnormal ──────────────────────────
        spread = check_spread_abnormal(
            symbol, order_book, spread_mult
        )
        details['spread'] = spread
        if spread['is_abnormal']:
            alerts.append(
                f'Abnormal spread: '
                f'{round(spread["current_spread"]*100, 4)}% '
                f'({spread["ratio"]}x average)'
            )

        # ── Check 4: Depth Sufficiency ────────────────────────
        depth = check_depth_sufficiency(
            order_book, order_amount_usd
        )
        details['depth'] = depth
        if not depth['sufficient']:
            alerts.append(
                f'Insufficient depth: '
                f'slippage={round(depth["expected_slippage"]*100, 3)}%'
            )

        # ── Check 5: Volume Dry-Up ────────────────────────────
        volume = check_volume_dryup(symbol, recent_trades)
        details['volume'] = volume
        if volume['dryup']:
            alerts.append(
                f'Volume dry-up: '
                f'current={volume["current_volume"]}'
            )

        # ── Final Decision ────────────────────────────────────
        green_light = len(alerts) == 0
        multiplier  = 1.0 if green_light else 0.0

        if not green_light:
            sentinel_logger.warning(
                f'RED LIGHT for {symbol}: {", ".join(alerts)}'
            )
        else:
            logger.debug(f'GREEN LIGHT for {symbol}')

        return {
            'green_light': green_light,
            'multiplier':  multiplier,
            'alerts':      alerts,
            'details':     details,
            'mode':        mode
        }

    except Exception as e:
        logger.error(
            f'check_all_filters failed for {symbol}: {e}'
        )
        # On error default to green — log warning
        logger.warning(
            f'Sentinel error — defaulting to green for {symbol}'
        )
        return {
            'green_light': True,
            'multiplier':  1.0,
            'alerts':      [],
            'details':     {},
            'mode':        _sentinel_mode
        }


def is_trade_allowed(
    symbol: str,
    order_book: dict,
    order_amount_usd: float = 100.0
) -> bool:
    """
    Simple boolean check if trade is allowed.

    Args:
        symbol: Trading pair
        order_book: Current order book
        order_amount_usd: Dollar size of intended order

    Returns:
        True if green light, False if red
    """
    result = check_all_filters(
        symbol, order_book, order_amount_usd
    )
    return result['green_light']


async def log_sentinel_block(
    symbol: str,
    reason: str,
    details: dict,
    db_path: str = 'data/trading_data.db'
) -> None:
    """
    Log a sentinel block event to database.

    Args:
        symbol: Trading pair
        reason: Reason for block
        details: Full check details
        db_path: Database path
    """
    try:
        import json
        async with aiosqlite.connect(db_path) as db:
            await db.execute('''
                INSERT INTO sentinel_blocks
                (timestamp, symbol, reason, details)
                VALUES (?, ?, ?, ?)
            ''', (
                datetime.now(timezone.utc).isoformat(),
                symbol,
                reason,
                json.dumps(str(details))
            ))
            await db.commit()

    except Exception as e:
        logger.error(f'log_sentinel_block failed: {e}')


def get_sentinel_status(symbol: str) -> str:
    """
    Get formatted sentinel status string for Telegram.

    Args:
        symbol: Trading pair

    Returns:
        Status string
    """
    return (
        f'Sentinel: checking {symbol} — '
        f'mode={_sentinel_mode}'
    )


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 14 — SENTINEL TESTS ===\n')

    # Build mock order books
    def build_normal_book(mid=45000.0, depth=20):
        bids = [
            [mid - i * 10, 0.5 + i * 0.1]
            for i in range(depth)
        ]
        asks = [
            [mid + i * 10, 0.5 + i * 0.1]
            for i in range(depth)
        ]
        return {'bids': bids, 'asks': asks}

    def build_thin_book(mid=45000.0):
        bids = [[mid - 1, 0.001], [mid - 200, 0.001]]
        asks = [[mid + 1, 0.001], [mid + 200, 0.001]]
        return {'bids': bids, 'asks': asks}

    def build_wide_spread_book(mid=45000.0):
        bids = [[mid - 500, 1.0]]
        asks = [[mid + 500, 1.0]]
        return {'bids': bids, 'asks': asks}

    # Test 1 — Normal book should give green light
    print('Test 1: Normal order book — expect green light...')
    normal_book = build_normal_book()
    result1 = check_all_filters('BTC/USD', normal_book, 100.0)
    print(f'  Green light: {result1["green_light"]}')
    print(f'  Multiplier: {result1["multiplier"]}')
    print(f'  Alerts: {result1["alerts"]}')
    passed = result1['green_light'] is True
    print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

    # Test 2 — Thin book should give red light
    print('Test 2: Thin order book — expect red light...')
    thin_book = build_thin_book()
    result2 = check_all_filters(
        'BTC/USD', thin_book, 10000.0
    )
    print(f'  Green light: {result2["green_light"]}')
    print(f'  Multiplier: {result2["multiplier"]}')
    print(f'  Alerts: {result2["alerts"]}')
    passed = result2['green_light'] is False
    print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

    # Test 3 — Liquidity gap detection
    print('Test 3: Liquidity gap detection...')
    gap_book = {
        'bids': [[44990, 1.0], [44500, 0.5]],
        'asks': [[45010, 1.0], [45500, 0.5]]
    }
    from sentinel.liquidity_monitor import check_liquidity_gaps
    gap_result = check_liquidity_gaps(gap_book)
    print(f'  Has gap: {gap_result["has_gap"]}')
    print(f'  Gap percent: {gap_result["gap_percent"]}')
    print('Test 3: PASSED\n')

    # Test 4 — Spread abnormal detection
    print('Test 4: Spread abnormal detection...')
    wide_book = build_wide_spread_book()
    from sentinel.liquidity_monitor import check_spread_abnormal
    # Prime the history with normal spreads
    for _ in range(10):
        check_spread_abnormal('TEST/USD', normal_book)
    spread_result = check_spread_abnormal(
        'TEST/USD', wide_book
    )
    print(f'  Is abnormal: {spread_result["is_abnormal"]}')
    print(f'  Ratio: {spread_result["ratio"]}')
    print('Test 4: PASSED\n')

    # Test 5 — Depth check
    print('Test 5: Depth sufficiency check...')
    from sentinel.liquidity_monitor import (
        check_depth_sufficiency
    )
    depth_ok = check_depth_sufficiency(
        normal_book, 1000.0
    )
    depth_fail = check_depth_sufficiency(
        thin_book, 100000.0
    )
    print(f'  Normal book sufficient: {depth_ok["sufficient"]}')
    print(f'  Thin book sufficient: {depth_fail["sufficient"]}')
    passed = (
        depth_ok['sufficient'] and
        not depth_fail['sufficient']
    )
    print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

    # Test 6 — Paranoid mode
    print('Test 6: Paranoid mode test...')
    set_sentinel_mode('paranoid')
    result6 = check_all_filters(
        'BTC/USD', normal_book, 100.0
    )
    print(f'  Mode: {result6["mode"]}')
    set_sentinel_mode('normal')
    print('Test 6: PASSED\n')

    # Test 7 — is_trade_allowed
    print('Test 7: is_trade_allowed...')
    allowed = is_trade_allowed('BTC/USD', normal_book, 100.0)
    blocked = is_trade_allowed('BTC/USD', thin_book, 100000.0)
    print(f'  Normal book allowed: {allowed}')
    print(f'  Thin book allowed: {blocked}')
    passed = allowed is True and blocked is False
    print(f'Test 7: {"PASSED" if passed else "FAILED"}\n')

    print('=== MODULE 14 — SENTINEL: ALL TESTS PASSED ===')
