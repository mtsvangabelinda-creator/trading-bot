# Autonomous Multi-Strategy Trading System
# Module 10 — Drawdown Guard
# Primary safety net for the whole account
# Monitors three independent drawdown measurements
# Fires hard halts when loss limits are breached

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional

import aiosqlite

from config import (
    MAX_ACCOUNT_DRAWDOWN,
    INTRADAY_DRAWDOWN,
    WEEKLY_LOSS_LIMIT
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

logger      = setup_logger('drawdown_guard', 'logs/errors.log')
risk_logger = setup_logger('risk', 'logs/risk.log')

# ── Halt States ───────────────────────────────────────────────
ACTIVE         = 'ACTIVE'
PEAK_HALT      = 'PEAK_HALT'
INTRADAY_HALT  = 'INTRADAY_HALT'
WEEKLY_HALT    = 'WEEKLY_HALT'
COOLOFF        = 'COOLOFF'

# ── Cooloff Duration ──────────────────────────────────────────
COOLOFF_HOURS  = 24


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def init_db(
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Create drawdown tracking tables if they do not exist.

    Args:
        db_path: Path to SQLite database

    Returns:
        True if successful, False on failure
    """
    try:
        os.makedirs('data', exist_ok=True)
        async with aiosqlite.connect(db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS drawdown_history (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp          TEXT NOT NULL,
                    account_value      REAL NOT NULL,
                    peak_value         REAL NOT NULL,
                    daily_start_value  REAL NOT NULL,
                    weekly_start_value REAL NOT NULL,
                    halt_state         TEXT NOT NULL,
                    note               TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS halt_log (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp     TEXT NOT NULL,
                    halt_type     TEXT NOT NULL,
                    account_value REAL NOT NULL,
                    trigger_pct   REAL NOT NULL,
                    resolved_at   TEXT
                )
            ''')
            await db.commit()
        logger.info('Drawdown Guard database initialised')
        return True

    except Exception as e:
        logger.error(f'init_db failed: {e}')
        return False


async def update(
    account_value: float,
    db_path: str = 'data/trading_data.db'
) -> Optional[dict]:
    """
    Update drawdown tracking with current account value.
    Checks all three drawdown measurements and fires halts.

    Args:
        account_value: Current total account value in dollars
        db_path: Path to SQLite database

    Returns:
        Dictionary with all drawdown metrics and halt state
        or None on failure
    """
    try:
        now = now_utc()
        today_str = now.strftime('%Y-%m-%d')

        async with aiosqlite.connect(db_path) as db:
            # Load most recent record
            cursor = await db.execute('''
                SELECT account_value, peak_value,
                       daily_start_value, weekly_start_value,
                       halt_state, timestamp
                FROM drawdown_history
                ORDER BY id DESC LIMIT 1
            ''')
            last = await cursor.fetchone()

            if last is None:
                # First run — initialise all values
                peak_value         = account_value
                daily_start_value  = account_value
                weekly_start_value = account_value
                prev_halt          = ACTIVE
                prev_timestamp     = now
            else:
                (prev_value, peak_value, daily_start_value,
                 weekly_start_value, prev_halt,
                 prev_ts_str) = last
                prev_timestamp = datetime.fromisoformat(prev_ts_str)

                # Update peak if new high
                if account_value > peak_value:
                    peak_value = account_value

                # Reset daily start if new UTC day
                prev_day = prev_timestamp.strftime('%Y-%m-%d')
                if today_str != prev_day:
                    daily_start_value = account_value
                    logger.info('Daily drawdown counter reset')

                # Reset weekly start if more than 7 days
                days_elapsed = (now - prev_timestamp).days
                if days_elapsed >= 7:
                    weekly_start_value = account_value
                    logger.info('Weekly drawdown counter reset')

            # Calculate drawdown percentages
            peak_dd = (
                (peak_value - account_value) / peak_value
                if peak_value > 0 else 0.0
            )
            intraday_dd = (
                (daily_start_value - account_value) /
                daily_start_value
                if daily_start_value > 0 else 0.0
            )
            weekly_dd = (
                (weekly_start_value - account_value) /
                weekly_start_value
                if weekly_start_value > 0 else 0.0
            )

            # Determine halt state
            peak_triggered     = False
            intraday_triggered = False
            weekly_triggered   = False
            alert_message      = None
            cooloff_active     = False
            cooloff_ends_at    = None

            # Priority: PEAK > WEEKLY > INTRADAY > COOLOFF > ACTIVE
            if peak_dd >= MAX_ACCOUNT_DRAWDOWN:
                halt_state         = PEAK_HALT
                peak_triggered     = True
                cooloff_ends_at    = now + timedelta(hours=COOLOFF_HOURS)
                if prev_halt != PEAK_HALT:
                    alert_message = (
                        f'DRAWDOWN ALERT — PEAK HALT TRIGGERED\n'
                        f'Peak Drawdown: {round(peak_dd*100,2)}% '
                        f'(limit {round(MAX_ACCOUNT_DRAWDOWN*100)}%)\n'
                        f'Account: ${account_value:,.2f} '
                        f'(peak: ${peak_value:,.2f})\n'
                        f'All new entries blocked.\n'
                        f'24h cool-off begins now.'
                    )
                    risk_logger.critical(
                        f'PEAK_HALT triggered: '
                        f'drawdown={round(peak_dd*100,2)}%'
                    )

            elif weekly_dd >= WEEKLY_LOSS_LIMIT:
                halt_state        = WEEKLY_HALT
                weekly_triggered  = True
                if prev_halt != WEEKLY_HALT:
                    alert_message = (
                        f'DRAWDOWN ALERT — WEEKLY HALT TRIGGERED\n'
                        f'Weekly Loss: {round(weekly_dd*100,2)}% '
                        f'(limit {round(WEEKLY_LOSS_LIMIT*100)}%)\n'
                        f'Trading paused until next Monday UTC.'
                    )
                    risk_logger.critical(
                        f'WEEKLY_HALT triggered: '
                        f'weekly_dd={round(weekly_dd*100,2)}%'
                    )

            elif intraday_dd >= INTRADAY_DRAWDOWN:
                halt_state          = INTRADAY_HALT
                intraday_triggered  = True
                if prev_halt != INTRADAY_HALT:
                    alert_message = (
                        f'DRAWDOWN ALERT — INTRADAY HALT\n'
                        f'Intraday Loss: {round(intraday_dd*100,2)}% '
                        f'(limit {round(INTRADAY_DRAWDOWN*100)}%)\n'
                        f'No new entries for rest of UTC day.'
                    )
                    risk_logger.warning(
                        f'INTRADAY_HALT triggered: '
                        f'intraday_dd={round(intraday_dd*100,2)}%'
                    )

            else:
                halt_state = ACTIVE

            # Save new record
            await db.execute('''
                INSERT INTO drawdown_history
                (timestamp, account_value, peak_value,
                 daily_start_value, weekly_start_value,
                 halt_state, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                now.isoformat(),
                account_value,
                peak_value,
                daily_start_value,
                weekly_start_value,
                halt_state,
                alert_message or ''
            ))
            await db.commit()

        return {
            'account_value':          round(account_value, 2),
            'peak_value':             round(peak_value, 2),
            'peak_drawdown_pct':      round(peak_dd, 4),
            'intraday_drawdown_pct':  round(intraday_dd, 4),
            'weekly_drawdown_pct':    round(weekly_dd, 4),
            'halt_state':             halt_state,
            'peak_halt_triggered':    peak_triggered,
            'intraday_halt_triggered': intraday_triggered,
            'weekly_halt_triggered':  weekly_triggered,
            'cooloff_active':         cooloff_active,
            'cooloff_ends_at':        cooloff_ends_at,
            'alert_message':          alert_message
        }

    except Exception as e:
        logger.error(f'update failed: {e}')
        return None


async def is_trading_allowed(
    db_path: str = 'data/trading_data.db'
) -> dict:
    """
    Check if trading is currently allowed.

    Args:
        db_path: Path to SQLite database

    Returns:
        Dictionary with allowed, halt_state, reason,
        resume_at
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute('''
                SELECT halt_state, timestamp, account_value,
                       peak_value
                FROM drawdown_history
                ORDER BY id DESC LIMIT 1
            ''')
            last = await cursor.fetchone()

        if last is None:
            return {
                'allowed':     True,
                'halt_state':  ACTIVE,
                'reason':      'No trading history — system is fresh',
                'resume_at':   None
            }

        halt_state, ts_str, account_val, peak_val = last
        ts = datetime.fromisoformat(ts_str)

        if halt_state == ACTIVE:
            return {
                'allowed':    True,
                'halt_state': ACTIVE,
                'reason':     'System active — trading allowed',
                'resume_at':  None
            }

        elif halt_state == INTRADAY_HALT:
            tomorrow = (ts + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return {
                'allowed':    False,
                'halt_state': INTRADAY_HALT,
                'reason':     'Intraday loss limit reached',
                'resume_at':  tomorrow
            }

        elif halt_state == WEEKLY_HALT:
            days_until_monday = (7 - ts.weekday()) % 7 or 7
            next_monday = (ts + timedelta(days=days_until_monday)
                           ).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return {
                'allowed':    False,
                'halt_state': WEEKLY_HALT,
                'reason':     'Weekly loss limit reached',
                'resume_at':  next_monday
            }

        elif halt_state == PEAK_HALT:
            cooloff_end = ts + timedelta(hours=COOLOFF_HOURS)
            return {
                'allowed':    False,
                'halt_state': PEAK_HALT,
                'reason':     (
                    f'Peak drawdown limit reached — '
                    f'24h cool-off required'
                ),
                'resume_at':  cooloff_end
            }

        else:
            return {
                'allowed':    False,
                'halt_state': halt_state,
                'reason':     f'System halted: {halt_state}',
                'resume_at':  None
            }

    except Exception as e:
        logger.error(f'is_trading_allowed failed: {e}')
        return {
            'allowed':    False,
            'halt_state': 'ERROR',
            'reason':     f'Error checking trading status: {e}',
            'resume_at':  None
        }


async def record_halt(
    halt_type: str,
    account_value: float,
    trigger_pct: float,
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Record a halt event to the halt log.

    Args:
        halt_type: Type of halt triggered
        account_value: Account value at time of halt
        trigger_pct: Drawdown percentage that triggered halt
        db_path: Path to SQLite database

    Returns:
        True if saved successfully
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute('''
                INSERT INTO halt_log
                (timestamp, halt_type, account_value, trigger_pct)
                VALUES (?, ?, ?, ?)
            ''', (
                now_utc().isoformat(),
                halt_type,
                account_value,
                trigger_pct
            ))
            await db.commit()
        return True

    except Exception as e:
        logger.error(f'record_halt failed: {e}')
        return False


async def resolve_halt(
    halt_type: str,
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Resolve a halt by updating the most recent unresolved entry.

    Args:
        halt_type: The halt type to resolve
        db_path: Path to SQLite database

    Returns:
        True if resolved successfully
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            # Update most recent unresolved halt of this type
            await db.execute('''
                UPDATE halt_log
                SET resolved_at = ?
                WHERE halt_type = ?
                AND resolved_at IS NULL
                ORDER BY id DESC
                LIMIT 1
            ''', (now_utc().isoformat(), halt_type))

            # Also reset halt state in drawdown_history
            await db.execute('''
                INSERT INTO drawdown_history
                (timestamp, account_value, peak_value,
                 daily_start_value, weekly_start_value,
                 halt_state, note)
                SELECT ?, account_value, peak_value,
                       daily_start_value, weekly_start_value,
                       ?, ?
                FROM drawdown_history
                ORDER BY id DESC LIMIT 1
            ''', (
                now_utc().isoformat(),
                ACTIVE,
                f'{halt_type} resolved manually'
            ))
            await db.commit()

        risk_logger.info(f'{halt_type} resolved manually')
        return True

    except Exception as e:
        logger.error(f'resolve_halt failed: {e}')
        return False


async def get_status(
    db_path: str = 'data/trading_data.db'
) -> str:
    """
    Get formatted drawdown status for Telegram.

    Args:
        db_path: Path to SQLite database

    Returns:
        Formatted status string
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute('''
                SELECT account_value, peak_value,
                       daily_start_value, weekly_start_value,
                       halt_state, timestamp
                FROM drawdown_history
                ORDER BY id DESC LIMIT 1
            ''')
            last = await cursor.fetchone()

        if last is None:
            return 'DRAWDOWN STATUS\nNo trading history yet.'

        (account_val, peak_val, daily_start,
         weekly_start, halt_state, ts_str) = last

        peak_dd    = (peak_val - account_val) / peak_val * 100
        intraday   = (
            (daily_start - account_val) / daily_start * 100
        )
        weekly     = (
            (weekly_start - account_val) / weekly_start * 100
        )

        trading = await is_trading_allowed(db_path)
        resume  = trading.get('resume_at')
        resume_str = (
            resume.strftime('%Y-%m-%d %H:%M UTC')
            if resume else 'N/A'
        )

        return (
            f'DRAWDOWN STATUS\n'
            f'{"─" * 24}\n'
            f'Current Account: ${account_val:,.2f}\n'
            f'Peak Value: ${peak_val:,.2f}\n'
            f'Peak Drawdown: {round(peak_dd,2)}% '
            f'(limit {round(MAX_ACCOUNT_DRAWDOWN*100)}%)\n'
            f'Intraday Loss: {round(intraday,2)}% '
            f'(limit {round(INTRADAY_DRAWDOWN*100)}%)\n'
            f'Weekly Loss: {round(weekly,2)}% '
            f'(limit {round(WEEKLY_LOSS_LIMIT*100)}%)\n'
            f'Status: {halt_state}\n'
            f'Resume At: {resume_str}\n'
            f'{"─" * 24}'
        )

    except Exception as e:
        logger.error(f'get_status failed: {e}')
        return 'DRAWDOWN STATUS\nError retrieving status.'


async def simulate(
    values: list,
    db_path: str = 'data/trading_data.db'
) -> list:
    """
    Simulate a sequence of account values for testing.

    Args:
        values: List of account values to simulate
        db_path: Path to test database

    Returns:
        List of halt states produced
    """
    states = []
    for value in values:
        result = await update(value, db_path)
        if result:
            states.append(result['halt_state'])
        else:
            states.append('ERROR')
    return states


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        TEST_DB = 'data/test_drawdown.db'
        print('\n=== MODULE 10 — DRAWDOWN GUARD TESTS ===\n')

        try:
            # Test 1 — Init database
            print('Test 1: Initialising test database...')
            result = await init_db(TEST_DB)
            print(
                f'Database initialised: '
                f'{"PASSED" if result else "FAILED"}\n'
            )

            # Test 2 — Normal trading sequence
            print('Test 2: Normal trading — no halts...')
            states = await simulate(
                [1000, 1010, 1020, 1015, 1025], TEST_DB
            )
            print(f'  States: {states}')
            passed = all(s == ACTIVE for s in states)
            print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

            # Test 3 — Intraday halt
            print('Test 3: Intraday halt (5.1% drop)...')
            await init_db(TEST_DB)
            states3 = await simulate([1000, 949], TEST_DB)
            print(f'  States: {states3}')
            passed = INTRADAY_HALT in states3
            print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

            # Test 4 — Peak drawdown halt
            print('Test 4: Peak halt (15.5% from peak)...')
            await init_db(TEST_DB)
            states4 = await simulate([1000, 1100, 930], TEST_DB)
            print(f'  States: {states4}')
            passed = PEAK_HALT in states4
            print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')

            # Test 5 — is_trading_allowed
            print('Test 5: is_trading_allowed after peak halt...')
            trading = await is_trading_allowed(TEST_DB)
            print(f'  Allowed: {trading["allowed"]}')
            print(f'  Halt state: {trading["halt_state"]}')
            passed = trading['allowed'] is False
            print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

            # Test 6 — get_status
            print('Test 6: get_status...')
            status = await get_status(TEST_DB)
            print(status)
            print('Test 6: PASSED\n')

            # Test 7 — resolve_halt
            print('Test 7: resolve_halt...')
            resolved = await resolve_halt(PEAK_HALT, TEST_DB)
            trading2 = await is_trading_allowed(TEST_DB)
            print(f'  Resolved: {resolved}')
            print(f'  Trading allowed after resolve: '
                  f'{trading2["allowed"]}')
            print('Test 7: PASSED\n')

            all_passed = (
                all(s == ACTIVE for s in states) and
                INTRADAY_HALT in states3 and
                PEAK_HALT in states4 and
                trading['allowed'] is False
            )
            print(
                '=== MODULE 10 — DRAWDOWN GUARD: '
                f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
            )

        finally:
            # Clean up test database
            import os
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
                print('\nTest database deleted.')

    asyncio.run(run_tests())
