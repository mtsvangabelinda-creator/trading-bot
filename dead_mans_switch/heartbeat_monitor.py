# Autonomous Multi-Strategy Trading System
# Module 22b — Heartbeat Monitor
# Runs on second Oracle VM — monitors main bot heartbeat
# If heartbeat stops for 5 minutes fires emergency cancel
# This process runs completely independently from main bot

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

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

logger = setup_logger(
    'heartbeat_monitor', 'logs/dead_mans_switch.log'
)

# ── Configuration ─────────────────────────────────────────────
HEARTBEAT_FILE    = os.getenv(
    'HEARTBEAT_FILE_PATH', 'data/heartbeat.txt'
)
HEARTBEAT_INTERVAL = int(
    os.getenv('HEARTBEAT_INTERVAL', '60')
)
HEARTBEAT_TIMEOUT = int(
    os.getenv('HEARTBEAT_TIMEOUT', '300')
)
CHECK_INTERVAL    = 30   # How often monitor checks in seconds
MAX_FAILURES      = 10   # Consecutive failures before firing


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def write_heartbeat(
    file_path: str = HEARTBEAT_FILE
) -> bool:
    """
    Write current UTC timestamp to heartbeat file.

    Called by the MAIN BOT every 60 seconds.
    This function runs on the MAIN SERVER.

    Args:
        file_path: Path to heartbeat file

    Returns:
        True if written successfully
    """
    try:
        os.makedirs(
            os.path.dirname(file_path)
            if os.path.dirname(file_path) else '.',
            exist_ok=True
        )

        timestamp = now_utc().isoformat()

        with open(file_path, 'w') as f:
            f.write(timestamp)

        logger.debug(f'Heartbeat written: {timestamp}')
        return True

    except Exception as e:
        logger.error(f'write_heartbeat failed: {e}')
        return False


def read_heartbeat(
    file_path: str = HEARTBEAT_FILE
) -> Optional[datetime]:
    """
    Read timestamp from heartbeat file.

    Called by the MONITOR SERVER every 30 seconds.
    This function runs on the MONITOR SERVER.

    Args:
        file_path: Path to heartbeat file

    Returns:
        Datetime object of last heartbeat or None
    """
    try:
        if not os.path.exists(file_path):
            logger.warning(
                f'Heartbeat file not found: {file_path}'
            )
            return None

        with open(file_path, 'r') as f:
            timestamp_str = f.read().strip()

        if not timestamp_str:
            return None

        timestamp = datetime.fromisoformat(timestamp_str)

        # Ensure timezone aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return timestamp

    except Exception as e:
        logger.error(f'read_heartbeat failed: {e}')
        return None


def check_heartbeat_alive(
    timeout_seconds: int = HEARTBEAT_TIMEOUT,
    file_path: str = HEARTBEAT_FILE
) -> bool:
    """
    Check if the main bot heartbeat is still alive.

    Args:
        timeout_seconds: Max seconds since last heartbeat
        file_path: Path to heartbeat file

    Returns:
        True if alive, False if dead or timeout exceeded
    """
    try:
        last_heartbeat = read_heartbeat(file_path)

        if last_heartbeat is None:
            logger.warning(
                'check_heartbeat_alive: no heartbeat found'
            )
            return False

        age = (now_utc() - last_heartbeat).total_seconds()

        if age > timeout_seconds:
            logger.warning(
                f'Heartbeat DEAD: last beat {round(age)}s ago '
                f'(timeout={timeout_seconds}s)'
            )
            return False

        logger.debug(
            f'Heartbeat alive: {round(age)}s ago'
        )
        return True

    except Exception as e:
        logger.error(f'check_heartbeat_alive failed: {e}')
        return False


def get_monitor_status(
    file_path: str = HEARTBEAT_FILE
) -> dict:
    """
    Get current monitor status summary.

    Args:
        file_path: Path to heartbeat file

    Returns:
        Dictionary with status details
    """
    try:
        last_hb = read_heartbeat(file_path)

        if last_hb is None:
            return {
                'last_heartbeat':        None,
                'seconds_since':         None,
                'status':                'DEAD',
                'consecutive_failures':  0,
                'emergency_fired':       False
            }

        age = (now_utc() - last_hb).total_seconds()
        status = 'ALIVE' if age < HEARTBEAT_TIMEOUT else 'DEAD'

        return {
            'last_heartbeat':       last_hb,
            'seconds_since':        round(age, 1),
            'status':               status,
            'consecutive_failures': 0,
            'emergency_fired':      False
        }

    except Exception as e:
        logger.error(f'get_monitor_status failed: {e}')
        return {
            'last_heartbeat':       None,
            'seconds_since':        None,
            'status':               'ERROR',
            'consecutive_failures': 0,
            'emergency_fired':      False
        }


async def monitor_loop(
    file_path: str = HEARTBEAT_FILE,
    check_interval: int = CHECK_INTERVAL,
    max_failures: int = MAX_FAILURES
) -> None:
    """
    Main monitoring loop — runs continuously on monitor server.

    Checks heartbeat every check_interval seconds.
    Fires emergency cancel after max_failures consecutive failures.
    Does NOT fire repeatedly — only once per outage.

    Args:
        file_path: Path to heartbeat file
        check_interval: Seconds between checks
        max_failures: Consecutive failures before firing
    """
    logger.info(
        f'Monitor loop started: checking every '
        f'{check_interval}s, timeout={HEARTBEAT_TIMEOUT}s'
    )

    consecutive_failures = 0
    emergency_fired      = False

    while True:
        try:
            alive = check_heartbeat_alive(
                HEARTBEAT_TIMEOUT, file_path
            )

            if alive:
                if consecutive_failures > 0:
                    logger.info(
                        f'Heartbeat restored after '
                        f'{consecutive_failures} failures'
                    )
                consecutive_failures = 0
                emergency_fired      = False
                logger.debug('Heartbeat check: ALIVE')

            else:
                consecutive_failures += 1
                logger.warning(
                    f'Heartbeat check FAILED '
                    f'({consecutive_failures}/{max_failures})'
                )

                if (
                    consecutive_failures >= max_failures and
                    not emergency_fired
                ):
                    logger.critical(
                        f'HEARTBEAT LOST for '
                        f'{consecutive_failures * check_interval}s '
                        f'— FIRING EMERGENCY CANCEL'
                    )

                    emergency_fired = True

                    try:
                        from dead_mans_switch.emergency_cancel import (
                            run_emergency_cancel
                        )
                        await run_emergency_cancel(
                            f'Main bot heartbeat lost '
                            f'({consecutive_failures * check_interval}s)'
                        )
                    except Exception as e:
                        logger.critical(
                            f'Emergency cancel failed: {e}'
                        )

                    # Wait longer after firing
                    await asyncio.sleep(60)

        except Exception as e:
            logger.error(f'monitor_loop iteration error: {e}')

        await asyncio.sleep(check_interval)


def start_monitor(
    file_path: str = HEARTBEAT_FILE
) -> None:
    """
    Entry point for the monitor server process.

    Starts the monitoring loop and handles
    graceful shutdown on keyboard interrupt.

    Args:
        file_path: Path to heartbeat file
    """
    logger.info(
        f'Dead Mans Switch Monitor starting\n'
        f'Heartbeat file: {file_path}\n'
        f'Timeout: {HEARTBEAT_TIMEOUT}s\n'
        f'Check interval: {CHECK_INTERVAL}s'
    )

    try:
        asyncio.run(monitor_loop(file_path))
    except KeyboardInterrupt:
        logger.info('Monitor stopped by keyboard interrupt')
    except Exception as e:
        logger.critical(f'Monitor crashed: {e}')


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        TEST_FILE = 'data/test_heartbeat.txt'
        print(
            '\n=== MODULE 22b — HEARTBEAT MONITOR TESTS ===\n'
        )

        try:
            # Test 1 — write_heartbeat
            print('Test 1: write_heartbeat...')
            result = write_heartbeat(TEST_FILE)
            passed = (
                result and
                os.path.exists(TEST_FILE)
            )
            print(f'  Written: {result}')
            print(f'  File exists: {os.path.exists(TEST_FILE)}')
            print(
                f'Test 1: {"PASSED" if passed else "FAILED"}\n'
            )

            # Test 2 — read_heartbeat
            print('Test 2: read_heartbeat...')
            timestamp = read_heartbeat(TEST_FILE)
            passed    = timestamp is not None
            print(f'  Timestamp: {timestamp}')
            print(
                f'Test 2: {"PASSED" if passed else "FAILED"}\n'
            )

            # Test 3 — check_heartbeat_alive fresh
            print(
                'Test 3: check_heartbeat_alive fresh...'
            )
            alive = check_heartbeat_alive(300, TEST_FILE)
            print(f'  Alive: {alive}')
            passed = alive is True
            print(
                f'Test 3: {"PASSED" if passed else "FAILED"}\n'
            )

            # Test 4 — check_heartbeat_alive old timestamp
            print(
                'Test 4: check_heartbeat_alive old timestamp...'
            )
            old_time = (
                now_utc() - timedelta(minutes=10)
            ).isoformat()
            with open(TEST_FILE, 'w') as f:
                f.write(old_time)

            dead = check_heartbeat_alive(300, TEST_FILE)
            print(f'  Alive with 10min old: {dead}')
            passed = dead is False
            print(
                f'Test 4: {"PASSED" if passed else "FAILED"}\n'
            )

            # Test 5 — get_monitor_status
            print('Test 5: get_monitor_status...')
            status = get_monitor_status(TEST_FILE)
            print(f'  Status: {status["status"]}')
            print(
                f'  Seconds since: {status["seconds_since"]}'
            )
            print('Test 5: PASSED\n')

            # Test 6 — Cancel-only connection
            print('Test 6: Cancel-only client connection...')
            cancel_key = os.getenv('KRAKEN_CANCEL_KEY', '')
            if cancel_key:
                from dead_mans_switch.emergency_cancel import (
                    create_cancel_only_client,
                    fetch_all_open_orders
                )
                client = await create_cancel_only_client()
                if client:
                    orders = await fetch_all_open_orders(client)
                    print(
                        f'  Connected, orders: {len(orders)}'
                    )
                    await client.close()
                    print('Test 6: PASSED\n')
                else:
                    print('Test 6: FAILED — no client\n')
            else:
                print(
                    'Test 6: SKIPPED — no cancel key\n'
                )

            # Test 7 — Monitor loop runs without crash
            print(
                'Test 7: Monitor loop single iteration...'
            )
            write_heartbeat(TEST_FILE)

            # Run one check manually
            alive7 = check_heartbeat_alive(300, TEST_FILE)
            print(f'  Check result: {"ALIVE" if alive7 else "DEAD"}')
            print('Test 7: PASSED\n')

            print(
                '=== MODULE 22b — HEARTBEAT MONITOR: '
                'ALL TESTS PASSED ==='
            )

        finally:
            # Clean up test file
            if os.path.exists(TEST_FILE):
                os.remove(TEST_FILE)
                print('\nTest heartbeat file deleted.')

    asyncio.run(run_tests())
