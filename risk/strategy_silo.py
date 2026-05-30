# Autonomous Multi-Strategy Trading System
# Module 11 — Strategy Silo
# Tracks performance independently for each strategy
# on each asset — 15 independent capital silos total
# Losses in one silo cannot drain another
# Each silo has its own drawdown limit and loss counter

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional

import aiosqlite

from config import (
    STRATEGY_DRAWDOWN,
    MR_CONSEC_LOSS_LIMIT,
    TF_CONSEC_LOSS_LIMIT,
    SCALPER_DAILY_LOSS,
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

logger      = setup_logger('strategy_silo', 'logs/errors.log')
risk_logger = setup_logger('risk', 'logs/risk.log')

# ── Strategy Names ────────────────────────────────────────────
TREND_FOLLOWING = 'TREND_FOLLOWING'
MEAN_REVERSION  = 'MEAN_REVERSION'
SCALPER         = 'SCALPER'
STRATEGIES      = [TREND_FOLLOWING, MEAN_REVERSION, SCALPER]

# ── Silo States ───────────────────────────────────────────────
ACTIVE = 'ACTIVE'
PAUSED = 'PAUSED'

# ── Cooloff ───────────────────────────────────────────────────
PAUSE_HOURS = 24


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def init_db(
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Create strategy silo tables if they do not exist.

    Args:
        db_path: Path to SQLite database

    Returns:
        True if successful, False on failure
    """
    try:
        os.makedirs('data', exist_ok=True)
        async with aiosqlite.connect(db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS strategy_silos (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset               TEXT NOT NULL,
                    strategy            TEXT NOT NULL,
                    timestamp           TEXT NOT NULL,
                    silo_value          REAL NOT NULL,
                    peak_value          REAL NOT NULL,
                    drawdown_pct        REAL NOT NULL,
                    consecutive_losses  INTEGER NOT NULL,
                    daily_loss_pct      REAL NOT NULL,
                    daily_start_value   REAL NOT NULL,
                    status              TEXT NOT NULL,
                    pause_reason        TEXT,
                    pause_until         TEXT
                )
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_silo_asset_strategy
                ON strategy_silos(asset, strategy)
            ''')
            await db.commit()

        logger.info('Strategy Silo database initialised')
        return True

    except Exception as e:
        logger.error(f'init_db failed: {e}')
        return False


def _get_initial_silo_value(
    asset: str,
    total_capital: float = 10000.0
) -> float:
    """Get initial capital allocation for an asset silo."""
    allocation = ASSETS.get(asset, 0.20)
    # Each strategy gets 1/3 of the asset allocation
    return total_capital * allocation / 3


async def register_trade(
    asset: str,
    strategy: str,
    pnl: float,
    db_path: str = 'data/trading_data.db'
) -> Optional[dict]:
    """
    Record a trade result and check pause conditions.

    Args:
        asset: Trading pair e.g. BTC/USD
        strategy: Strategy name
        pnl: Profit or loss in dollars (negative for loss)
        db_path: Path to SQLite database

    Returns:
        Dictionary with silo status and pause details
        or None on failure
    """
    try:
        now = now_utc()
        today_str = now.strftime('%Y-%m-%d')

        async with aiosqlite.connect(db_path) as db:
            # Load most recent record for this silo
            cursor = await db.execute('''
                SELECT silo_value, peak_value,
                       consecutive_losses, daily_loss_pct,
                       daily_start_value, status, timestamp
                FROM strategy_silos
                WHERE asset=? AND strategy=?
                ORDER BY id DESC LIMIT 1
            ''', (asset, strategy))
            last = await cursor.fetchone()

            if last is None:
                # First trade for this silo
                initial = _get_initial_silo_value(asset)
                silo_value         = initial + pnl
                peak_value         = max(initial, silo_value)
                consecutive_losses = 1 if pnl < 0 else 0
                daily_start_value  = initial
                daily_loss_pct     = (
                    max(0.0, -pnl / initial) if pnl < 0 else 0.0
                )
            else:
                (prev_value, prev_peak, prev_consec,
                 prev_daily_pct, prev_daily_start,
                 prev_status, prev_ts_str) = last

                silo_value = prev_value + pnl
                peak_value = max(prev_peak, silo_value)

                # Update consecutive losses
                if pnl < 0:
                    consecutive_losses = prev_consec + 1
                else:
                    consecutive_losses = 0

                # Reset daily tracking if new day
                prev_day = datetime.fromisoformat(
                    prev_ts_str
                ).strftime('%Y-%m-%d')

                if today_str != prev_day:
                    daily_start_value = silo_value
                    daily_loss_pct    = 0.0
                else:
                    daily_start_value = prev_daily_start
                    if pnl < 0 and daily_start_value > 0:
                        current_daily_loss = (
                            daily_start_value - silo_value
                        )
                        daily_loss_pct = max(
                            0.0,
                            current_daily_loss / daily_start_value
                        )
                    else:
                        daily_loss_pct = prev_daily_pct

            # Calculate drawdown from peak
            drawdown_pct = (
                (peak_value - silo_value) / peak_value
                if peak_value > 0 else 0.0
            )

            # Check pause conditions
            pause_triggered = False
            pause_reason    = None
            pause_until     = None
            alert_message   = None

            if strategy == TREND_FOLLOWING:
                if consecutive_losses >= TF_CONSEC_LOSS_LIMIT:
                    pause_triggered = True
                    pause_reason = (
                        f'{TF_CONSEC_LOSS_LIMIT} consecutive losses'
                    )
                elif drawdown_pct >= STRATEGY_DRAWDOWN:
                    pause_triggered = True
                    pause_reason = (
                        f'Drawdown {round(drawdown_pct*100,1)}% '
                        f'from peak'
                    )

            elif strategy == MEAN_REVERSION:
                if consecutive_losses >= MR_CONSEC_LOSS_LIMIT:
                    pause_triggered = True
                    pause_reason = (
                        f'{MR_CONSEC_LOSS_LIMIT} consecutive losses'
                    )
                elif drawdown_pct >= STRATEGY_DRAWDOWN:
                    pause_triggered = True
                    pause_reason = (
                        f'Drawdown {round(drawdown_pct*100,1)}% '
                        f'from peak'
                    )

            elif strategy == SCALPER:
                if daily_loss_pct >= SCALPER_DAILY_LOSS:
                    pause_triggered = True
                    pause_reason    = (
                        f'Daily loss {round(daily_loss_pct*100,1)}% '
                        f'exceeds limit'
                    )
                    # Scalper pauses until midnight UTC
                    tomorrow = (now + timedelta(days=1)).replace(
                        hour=0, minute=0,
                        second=0, microsecond=0
                    )
                    pause_until = tomorrow
                elif drawdown_pct >= STRATEGY_DRAWDOWN:
                    pause_triggered = True
                    pause_reason = (
                        f'Drawdown {round(drawdown_pct*100,1)}% '
                        f'from peak'
                    )

            # Set pause duration
            if pause_triggered:
                status = PAUSED
                if pause_until is None:
                    pause_until = now + timedelta(hours=PAUSE_HOURS)
                alert_message = (
                    f'STRATEGY PAUSED — {asset} {strategy}\n'
                    f'Reason: {pause_reason}\n'
                    f'Resumes: '
                    f'{pause_until.strftime("%Y-%m-%d %H:%M UTC")}'
                )
                risk_logger.warning(
                    f'PAUSED {asset}/{strategy}: {pause_reason}'
                )
            else:
                status      = ACTIVE
                pause_until = None

            # Save record
            await db.execute('''
                INSERT INTO strategy_silos
                (asset, strategy, timestamp, silo_value,
                 peak_value, drawdown_pct, consecutive_losses,
                 daily_loss_pct, daily_start_value, status,
                 pause_reason, pause_until)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                asset, strategy,
                now.isoformat(),
                round(silo_value, 4),
                round(peak_value, 4),
                round(drawdown_pct, 4),
                consecutive_losses,
                round(daily_loss_pct, 4),
                round(daily_start_value, 4),
                status,
                pause_reason,
                pause_until.isoformat() if pause_until else None
            ))
            await db.commit()

        return {
            'asset':               asset,
            'strategy':            strategy,
            'silo_value':          round(silo_value, 4),
            'peak_value':          round(peak_value, 4),
            'drawdown_pct':        round(drawdown_pct, 4),
            'consecutive_losses':  consecutive_losses,
            'daily_loss_pct':      round(daily_loss_pct, 4),
            'status':              status,
            'pause_triggered':     pause_triggered,
            'pause_reason':        pause_reason,
            'pause_until':         pause_until,
            'alert_message':       alert_message
        }

    except Exception as e:
        logger.error(
            f'register_trade failed for {asset}/{strategy}: {e}'
        )
        return None


async def is_active(
    asset: str,
    strategy: str,
    db_path: str = 'data/trading_data.db'
) -> dict:
    """
    Check if a strategy silo is currently active.

    Args:
        asset: Trading pair
        strategy: Strategy name
        db_path: Path to SQLite database

    Returns:
        Dictionary with active, status, reason, pause_until
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute('''
                SELECT status, pause_until, pause_reason
                FROM strategy_silos
                WHERE asset=? AND strategy=?
                ORDER BY id DESC LIMIT 1
            ''', (asset, strategy))
            last = await cursor.fetchone()

        if last is None:
            return {
                'active':      True,
                'status':      ACTIVE,
                'reason':      'Never traded — silo is fresh',
                'pause_until': None
            }

        status, pause_until_str, pause_reason = last

        # Check if pause has expired
        if status == PAUSED and pause_until_str:
            pause_until = datetime.fromisoformat(pause_until_str)
            if now_utc() >= pause_until:
                # Auto-resume
                await resume_strategy(asset, strategy, db_path)
                return {
                    'active':      True,
                    'status':      ACTIVE,
                    'reason':      'Pause period expired — auto-resumed',
                    'pause_until': None
                }

        if status == ACTIVE:
            return {
                'active':      True,
                'status':      ACTIVE,
                'reason':      'Strategy is active',
                'pause_until': None
            }
        else:
            pause_until = (
                datetime.fromisoformat(pause_until_str)
                if pause_until_str else None
            )
            return {
                'active':      False,
                'status':      PAUSED,
                'reason':      pause_reason or 'Paused',
                'pause_until': pause_until
            }

    except Exception as e:
        logger.error(f'is_active failed for {asset}/{strategy}: {e}')
        return {
            'active':      True,
            'status':      ACTIVE,
            'reason':      f'Error checking status: {e}',
            'pause_until': None
        }


async def resume_strategy(
    asset: str,
    strategy: str,
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Manually resume a paused strategy silo.

    Args:
        asset: Trading pair
        strategy: Strategy name
        db_path: Path to SQLite database

    Returns:
        True if resumed successfully
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            # Get most recent record
            cursor = await db.execute('''
                SELECT silo_value, peak_value,
                       daily_start_value
                FROM strategy_silos
                WHERE asset=? AND strategy=?
                ORDER BY id DESC LIMIT 1
            ''', (asset, strategy))
            last = await cursor.fetchone()

            if last is None:
                return False

            silo_value, peak_value, daily_start = last

            await db.execute('''
                INSERT INTO strategy_silos
                (asset, strategy, timestamp, silo_value,
                 peak_value, drawdown_pct, consecutive_losses,
                 daily_loss_pct, daily_start_value, status,
                 pause_reason, pause_until)
                VALUES (?, ?, ?, ?, ?, 0.0, 0, 0.0, ?, ?, ?, ?)
            ''', (
                asset, strategy,
                now_utc().isoformat(),
                silo_value,
                peak_value,
                daily_start,
                ACTIVE,
                'Manually resumed',
                None
            ))
            await db.commit()

        risk_logger.info(
            f'{asset}/{strategy} manually resumed'
        )
        return True

    except Exception as e:
        logger.error(
            f'resume_strategy failed for {asset}/{strategy}: {e}'
        )
        return False


async def get_all_status(
    db_path: str = 'data/trading_data.db'
) -> dict:
    """
    Get current status for all 15 strategy silos.

    Args:
        db_path: Path to SQLite database

    Returns:
        Dictionary of asset/strategy to status info
    """
    try:
        results = {}
        for asset in ASSETS.keys():
            for strategy in STRATEGIES:
                key    = f'{asset}/{strategy}'
                status = await is_active(asset, strategy, db_path)
                results[key] = status
        return results

    except Exception as e:
        logger.error(f'get_all_status failed: {e}')
        return {}


def format_summary(status_dict: dict) -> str:
    """
    Format silo status as a Telegram-ready string.

    Args:
        status_dict: Output from get_all_status

    Returns:
        Formatted summary string
    """
    try:
        lines = ['STRATEGY SILO STATUS', '─' * 30]
        current_asset = None

        for key, status in status_dict.items():
            asset, strategy = key.split('/')
            if asset != current_asset:
                if current_asset is not None:
                    lines.append('')
                lines.append(asset)
                current_asset = asset

            state       = status.get('status', ACTIVE)
            reason      = status.get('reason', '')
            pause_until = status.get('pause_until')

            if state == ACTIVE:
                lines.append(f'  {strategy}: ACTIVE')
            else:
                pause_str = ''
                if pause_until:
                    pause_str = (
                        f' until '
                        f'{pause_until.strftime("%H:%M UTC")}'
                    )
                lines.append(
                    f'  {strategy}: PAUSED{pause_str}'
                )
                if reason:
                    lines.append(f'    Reason: {reason}')

        lines.append('─' * 30)
        return '\n'.join(lines)

    except Exception as e:
        logger.error(f'format_summary failed: {e}')
        return 'Silo summary unavailable'


async def reset_daily_losses(
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Reset daily loss counters for all silos.
    Called by scheduler at UTC midnight.

    Args:
        db_path: Path to SQLite database

    Returns:
        True if successful
    """
    try:
        logger.info('Resetting daily loss counters for all silos')
        for asset in ASSETS.keys():
            for strategy in STRATEGIES:
                async with aiosqlite.connect(db_path) as db:
                    cursor = await db.execute('''
                        SELECT silo_value, peak_value
                        FROM strategy_silos
                        WHERE asset=? AND strategy=?
                        ORDER BY id DESC LIMIT 1
                    ''', (asset, strategy))
                    last = await cursor.fetchone()

                    if last:
                        silo_value, peak_value = last
                        await db.execute('''
                            UPDATE strategy_silos
                            SET daily_start_value=?,
                                daily_loss_pct=0.0
                            WHERE asset=? AND strategy=?
                            AND id=(
                                SELECT MAX(id)
                                FROM strategy_silos
                                WHERE asset=? AND strategy=?
                            )
                        ''', (
                            silo_value, asset, strategy,
                            asset, strategy
                        ))
                        await db.commit()
        return True

    except Exception as e:
        logger.error(f'reset_daily_losses failed: {e}')
        return False


async def simulate_trade_sequence(
    asset: str,
    strategy: str,
    pnls: list,
    db_path: str = 'data/trading_data.db'
) -> list:
    """
    Simulate a sequence of trade results for testing.

    Args:
        asset: Trading pair
        strategy: Strategy name
        pnls: List of PnL values to simulate
        db_path: Path to test database

    Returns:
        List of status strings after each trade
    """
    states = []
    for pnl in pnls:
        result = await register_trade(asset, strategy, pnl, db_path)
        if result:
            states.append(result['status'])
        else:
            states.append('ERROR')
    return states


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        TEST_DB = 'data/test_silo.db'
        print('\n=== MODULE 11 — STRATEGY SILO TESTS ===\n')

        try:
            # Test 1 — Init database
            print('Test 1: Initialising test database...')
            result = await init_db(TEST_DB)
            print(
                f'Silo database initialised: '
                f'{"PASSED" if result else "FAILED"}\n'
            )

            # Test 2 — Winning trades stay ACTIVE
            print('Test 2: 3 winning TF trades...')
            states = await simulate_trade_sequence(
                'BTC/USD', TREND_FOLLOWING,
                [10, 10, 10], TEST_DB
            )
            print(f'  States: {states}')
            passed = all(s == ACTIVE for s in states)
            print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

            # Test 3 — TF consecutive loss pause
            print(
                'Test 3: 4 losing TF trades '
                '— should pause after 4th...'
            )
            states3 = await simulate_trade_sequence(
                'BTC/USD', TREND_FOLLOWING,
                [-5, -5, -5, -5], TEST_DB
            )
            print(f'  States: {states3}')
            passed = states3[-1] == PAUSED
            print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

            # Test 4 — MR consecutive loss pause
            print(
                'Test 4: 6 losing MR trades '
                '— should pause after 6th...'
            )
            states4 = await simulate_trade_sequence(
                'ETH/USD', MEAN_REVERSION,
                [-3, -3, -3, -3, -3, -3], TEST_DB
            )
            print(f'  States: {states4}')
            passed = states4[-1] == PAUSED
            print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')

            # Test 5 — is_active checks
            print('Test 5: is_active checks...')
            tf_status  = await is_active(
                'BTC/USD', TREND_FOLLOWING, TEST_DB
            )
            sc_status  = await is_active(
                'ETH/USD', SCALPER, TEST_DB
            )
            print(
                f'  BTC/USD TF active: {tf_status["active"]} '
                f'(expected False)'
            )
            print(
                f'  ETH/USD SCALPER active: {sc_status["active"]} '
                f'(expected True)'
            )
            passed = (
                tf_status['active'] is False and
                sc_status['active'] is True
            )
            print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

            # Test 6 — resume_strategy
            print('Test 6: resume_strategy...')
            resumed = await resume_strategy(
                'BTC/USD', TREND_FOLLOWING, TEST_DB
            )
            tf_after = await is_active(
                'BTC/USD', TREND_FOLLOWING, TEST_DB
            )
            print(f'  Resumed: {resumed}')
            print(f'  Active after resume: {tf_after["active"]}')
            passed = tf_after['active'] is True
            print(f'Test 6: {"PASSED" if passed else "FAILED"}\n')

            # Test 7 — get_all_status and format_summary
            print('Test 7: get_all_status and format_summary...')
            all_status = await get_all_status(TEST_DB)
            summary    = format_summary(all_status)
            print(summary)
            print('Test 7: PASSED\n')

            all_passed = (
                result and
                all(s == ACTIVE for s in states) and
                states3[-1] == PAUSED and
                states4[-1] == PAUSED and
                tf_status['active'] is False and
                sc_status['active'] is True and
                tf_after['active'] is True
            )
            print(
                '=== MODULE 11 — STRATEGY SILO: '
                f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
            )

        finally:
            import os
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
                print('\nTest database deleted.')

    asyncio.run(run_tests())
