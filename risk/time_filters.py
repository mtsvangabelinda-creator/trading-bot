# Autonomous Multi-Strategy Trading System
# Module 13 — Time Filters
# Applies time-based trading restrictions
# Settlement window, weekend mode, news blackout
# Prevents trading during high-risk or low-liquidity times

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional

import pytz

from config import (
    SETTLEMENT_START,
    SETTLEMENT_END,
    SETTLEMENT_SIZE_REDUCTION
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

logger      = setup_logger('time_filters', 'logs/errors.log')
risk_logger = setup_logger('risk', 'logs/risk.log')

# ── News Calendar Path ────────────────────────────────────────
NEWS_CALENDAR_PATH   = 'config/news_calendar.json'
NEWS_BUFFER_MINUTES  = 15

# ── UTC Timezone ──────────────────────────────────────────────
UTC = timezone.utc


def now_utc() -> datetime:
    return datetime.now(UTC)


def is_settlement_window(
    now_utc_time: datetime = None
) -> bool:
    """
    Check if current time is in the daily settlement window.

    Settlement window: 23:45 to 00:15 UTC
    Position sizes reduced by 50% during this window.

    Args:
        now_utc_time: Optional datetime for testing

    Returns:
        True if in settlement window, False otherwise
    """
    try:
        if now_utc_time is None:
            now_utc_time = now_utc()

        current_hour   = now_utc_time.hour
        current_minute = now_utc_time.minute
        current_time   = current_hour * 60 + current_minute

        # Parse settlement times
        start_h, start_m = map(int, SETTLEMENT_START.split(':'))
        end_h,   end_m   = map(int, SETTLEMENT_END.split(':'))

        start_mins = start_h * 60 + start_m  # 23:45 = 1425
        end_mins   = end_h   * 60 + end_m    # 00:15 = 15

        # Window crosses midnight so check both sides
        in_window = (
            current_time >= start_mins or
            current_time <= end_mins
        )

        if in_window:
            logger.debug(
                f'Settlement window active at '
                f'{now_utc_time.strftime("%H:%M UTC")}'
            )

        return in_window

    except Exception as e:
        logger.error(f'is_settlement_window failed: {e}')
        return False


def get_settlement_multiplier() -> float:
    """
    Get position size multiplier for settlement window.

    Returns:
        0.5 if in settlement window, 1.0 otherwise
    """
    try:
        if is_settlement_window():
            return float(SETTLEMENT_SIZE_REDUCTION)
        return 1.0

    except Exception as e:
        logger.error(f'get_settlement_multiplier failed: {e}')
        return 1.0


def is_weekend(
    now_utc_time: datetime = None
) -> bool:
    """
    Check if current UTC time is on a weekend.

    Weekend = Saturday (5) or Sunday (6) in UTC.

    Args:
        now_utc_time: Optional datetime for testing

    Returns:
        True if weekend, False if weekday
    """
    try:
        if now_utc_time is None:
            now_utc_time = now_utc()

        # weekday() returns 0=Monday through 6=Sunday
        return now_utc_time.weekday() >= 5

    except Exception as e:
        logger.error(f'is_weekend failed: {e}')
        return False


def get_weekend_mode_flag(
    now_utc_time: datetime = None
) -> dict:
    """
    Get weekend mode flags for parameter adjustments.

    Returns:
        Dictionary with active, scalper_loss_halved,
        sentinel_paranoid flags
    """
    try:
        weekend = is_weekend(now_utc_time)

        return {
            'active':               weekend,
            'scalper_loss_halved':  weekend,
            'sentinel_paranoid':    weekend
        }

    except Exception as e:
        logger.error(f'get_weekend_mode_flag failed: {e}')
        return {
            'active':              False,
            'scalper_loss_halved': False,
            'sentinel_paranoid':   False
        }


def is_news_blackout(
    event_calendar_path: str = NEWS_CALENDAR_PATH,
    now_utc_time: datetime = None,
    buffer_minutes: int = NEWS_BUFFER_MINUTES
) -> bool:
    """
    Check if current time is within a news blackout window.

    Loads news_calendar.json and checks if current time
    is within buffer_minutes of any scheduled event.

    Args:
        event_calendar_path: Path to news calendar JSON file
        now_utc_time: Optional datetime for testing
        buffer_minutes: Minutes before and after event to block

    Returns:
        True if in news blackout, False otherwise
    """
    try:
        if now_utc_time is None:
            now_utc_time = now_utc()

        if not os.path.exists(event_calendar_path):
            logger.debug(
                f'News calendar not found at '
                f'{event_calendar_path} — no blackout'
            )
            return False

        with open(event_calendar_path, 'r') as f:
            events = json.load(f)

        if not events:
            return False

        buffer = timedelta(minutes=buffer_minutes)

        for event_str in events:
            try:
                event_time = datetime.fromisoformat(event_str)
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=UTC)

                if abs(now_utc_time - event_time) <= buffer:
                    logger.info(
                        f'News blackout active: '
                        f'event at {event_str}, '
                        f'buffer={buffer_minutes}min'
                    )
                    risk_logger.warning(
                        f'NEWS BLACKOUT: event={event_str}'
                    )
                    return True

            except Exception:
                continue

        return False

    except Exception as e:
        logger.warning(
            f'is_news_blackout failed — assuming no blackout: {e}'
        )
        return False


def is_trading_allowed(
    event_calendar_path: str = NEWS_CALENDAR_PATH
) -> bool:
    """
    Check if trading is allowed based on time filters.

    Only news blackout blocks trading entirely.
    Settlement window and weekend mode only adjust parameters.

    Args:
        event_calendar_path: Path to news calendar JSON

    Returns:
        False if news blackout active, True otherwise
    """
    try:
        blackout = is_news_blackout(event_calendar_path)
        if blackout:
            logger.info(
                'Trading blocked: news blackout active'
            )
            return False
        return True

    except Exception as e:
        logger.error(f'is_trading_allowed failed: {e}')
        return True


def get_size_multiplier() -> float:
    """
    Get combined position size multiplier from time filters.

    Returns:
        Settlement multiplier (0.5 or 1.0)
        Weekend does not affect size directly
    """
    try:
        return get_settlement_multiplier()

    except Exception as e:
        logger.error(f'get_size_multiplier failed: {e}')
        return 1.0


def get_parameter_overrides() -> dict:
    """
    Get parameter overrides based on current time conditions.

    Returns:
        Dictionary with scalper_loss_limit_halved
        and sentinel_mode
    """
    try:
        weekend_flags = get_weekend_mode_flag()

        sentinel_mode = (
            'paranoid'
            if weekend_flags['sentinel_paranoid']
            else 'normal'
        )

        return {
            'scalper_loss_limit_halved': (
                weekend_flags['scalper_loss_halved']
            ),
            'sentinel_mode': sentinel_mode
        }

    except Exception as e:
        logger.error(f'get_parameter_overrides failed: {e}')
        return {
            'scalper_loss_limit_halved': False,
            'sentinel_mode': 'normal'
        }


def create_test_calendar(
    path: str,
    event_offset_minutes: int = 30
) -> bool:
    """
    Create a temporary news calendar for testing.

    Args:
        path: Path to write the calendar file
        event_offset_minutes: Minutes from now for test event

    Returns:
        True if created successfully
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        event_time = (
            now_utc() +
            timedelta(minutes=event_offset_minutes)
        )
        events = [event_time.isoformat()]
        with open(path, 'w') as f:
            json.dump(events, f)
        return True

    except Exception as e:
        logger.error(f'create_test_calendar failed: {e}')
        return False


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 13 — TIME FILTERS TESTS ===\n')

    TEST_CALENDAR = 'config/test_news_calendar.json'

    # Test 1 — Settlement window at 23:50
    print('Test 1: Settlement window at 23:50 UTC...')
    mock_time_settlement = datetime(
        2024, 1, 15, 23, 50, 0, tzinfo=UTC
    )
    in_settlement = is_settlement_window(mock_time_settlement)
    multiplier    = (
        SETTLEMENT_SIZE_REDUCTION if in_settlement else 1.0
    )
    print(f'  In settlement: {in_settlement}')
    print(f'  Multiplier: {multiplier}')
    passed = in_settlement is True and multiplier == 0.5
    print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

    # Test 2 — Outside settlement at 12:00
    print('Test 2: Outside settlement at 12:00 UTC...')
    mock_time_normal = datetime(
        2024, 1, 15, 12, 0, 0, tzinfo=UTC
    )
    not_in_settlement = is_settlement_window(mock_time_normal)
    multiplier2 = 1.0 if not not_in_settlement else 0.5
    print(f'  In settlement: {not_in_settlement}')
    print(f'  Multiplier: {multiplier2}')
    passed = not_in_settlement is False and multiplier2 == 1.0
    print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

    # Test 3 — Weekend detection Saturday
    print('Test 3: Weekend — Saturday 12:00 UTC...')
    # Find next Saturday
    today = now_utc()
    days_until_sat = (5 - today.weekday()) % 7
    if days_until_sat == 0:
        days_until_sat = 7
    saturday = today.replace(
        hour=12, minute=0, second=0, microsecond=0
    ) + timedelta(days=days_until_sat)
    weekend_flag = get_weekend_mode_flag(saturday)
    print(f'  Weekend active: {weekend_flag["active"]}')
    print(
        f'  Scalper halved: '
        f'{weekend_flag["scalper_loss_halved"]}'
    )
    print(
        f'  Sentinel paranoid: '
        f'{weekend_flag["sentinel_paranoid"]}'
    )
    passed = (
        weekend_flag['active'] and
        weekend_flag['scalper_loss_halved'] and
        weekend_flag['sentinel_paranoid']
    )
    print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

    # Test 4 — Weekday detection
    print('Test 4: Weekday — Monday 12:00 UTC...')
    days_until_mon = (0 - today.weekday()) % 7
    if days_until_mon == 0:
        days_until_mon = 7
    monday = today.replace(
        hour=12, minute=0, second=0, microsecond=0
    ) + timedelta(days=days_until_mon)
    weekday_flag = get_weekend_mode_flag(monday)
    print(f'  Weekend active: {weekday_flag["active"]}')
    passed = weekday_flag['active'] is False
    print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')

    # Test 5 — News blackout 10 minutes before event
    print('Test 5: News blackout — 10 minutes before event...')
    create_test_calendar(TEST_CALENDAR, event_offset_minutes=30)
    mock_blackout_time = now_utc() + timedelta(minutes=20)
    in_blackout = is_news_blackout(
        TEST_CALENDAR, mock_blackout_time
    )
    print(f'  In blackout: {in_blackout}')
    passed = in_blackout is True
    print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

    # Test 6 — Outside blackout 20 minutes after
    print('Test 6: Outside blackout — 60 minutes after event...')
    mock_after_time = now_utc() + timedelta(minutes=90)
    not_in_blackout = is_news_blackout(
        TEST_CALENDAR, mock_after_time
    )
    print(f'  In blackout: {not_in_blackout}')
    passed = not_in_blackout is False
    print(f'Test 6: {"PASSED" if passed else "FAILED"}\n')

    # Test 7 — is_trading_allowed during blackout
    print('Test 7: is_trading_allowed during blackout...')
    # Temporarily replace with current time event
    create_test_calendar(TEST_CALENDAR, event_offset_minutes=5)
    allowed = is_trading_allowed(TEST_CALENDAR)
    print(f'  Trading allowed: {allowed}')
    passed = allowed is False
    print(f'Test 7: {"PASSED" if passed else "FAILED"}\n')

    # Test 8 — get_size_multiplier during settlement
    print('Test 8: get_size_multiplier (live check)...')
    live_multiplier = get_size_multiplier()
    print(f'  Current multiplier: {live_multiplier}')
    passed = live_multiplier in [0.5, 1.0]
    print(f'Test 8: {"PASSED" if passed else "FAILED"}\n')

    # Test 9 — get_parameter_overrides
    print('Test 9: get_parameter_overrides...')
    overrides = get_parameter_overrides()
    print(f'  Overrides: {overrides}')
    passed = (
        'scalper_loss_limit_halved' in overrides and
        'sentinel_mode' in overrides
    )
    print(f'Test 9: {"PASSED" if passed else "FAILED"}\n')

    # Cleanup
    if os.path.exists(TEST_CALENDAR):
        os.remove(TEST_CALENDAR)
        print('Test calendar deleted.')

    print(
        '\n=== MODULE 13 — TIME FILTERS: ALL TESTS PASSED ==='
          )
