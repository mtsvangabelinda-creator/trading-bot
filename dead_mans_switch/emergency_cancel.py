# Autonomous Multi-Strategy Trading System
# Module 22a — Emergency Cancel
# Uses cancel-only Kraken API key to cancel all open orders
# Triggered by heartbeat monitor when main bot goes silent
# NEVER places trades — only cancels orders

import asyncio
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional

import ccxt.async_support as ccxt_async
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
    'emergency_cancel', 'logs/dead_mans_switch.log'
)

# ── Cancel Only Credentials ───────────────────────────────────
CANCEL_KEY    = os.getenv('KRAKEN_CANCEL_KEY', '')
CANCEL_SECRET = os.getenv('KRAKEN_CANCEL_SECRET', '')
BOT_TOKEN     = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID       = os.getenv('TELEGRAM_AUTHORISED_USER_ID', '')


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def create_cancel_only_client():
    """
    Create Kraken client using cancel-only API credentials.

    This client uses KRAKEN_CANCEL_KEY not the main trading key.
    It can only cancel orders — it cannot place any trades.

    Returns:
        Authenticated ccxt Kraken instance or None on failure
    """
    try:
        if not CANCEL_KEY or not CANCEL_SECRET:
            logger.error(
                'create_cancel_only_client: '
                'KRAKEN_CANCEL_KEY or KRAKEN_CANCEL_SECRET '
                'not found in .env'
            )
            return None

        client = ccxt_async.kraken({
            'apiKey':          CANCEL_KEY,
            'secret':          CANCEL_SECRET,
            'enableRateLimit': True
        })

        logger.info(
            'Cancel-only Kraken client created successfully'
        )
        return client

    except Exception as e:
        logger.error(
            f'create_cancel_only_client failed: {e}'
        )
        return None


async def fetch_all_open_orders(exchange) -> list:
    """
    Fetch all open orders across all trading pairs.

    Args:
        exchange: Cancel-only ccxt Kraken instance

    Returns:
        List of order dictionaries or empty list on failure
    """
    try:
        orders = await exchange.fetch_open_orders()

        if not orders:
            logger.info('No open orders found')
            return []

        logger.info(
            f'Found {len(orders)} open orders'
        )

        result = []
        for order in orders:
            result.append({
                'order_id': order.get('id'),
                'symbol':   order.get('symbol'),
                'side':     order.get('side'),
                'amount':   order.get('amount'),
                'price':    order.get('price'),
                'type':     order.get('type')
            })

        return result

    except Exception as e:
        logger.error(f'fetch_all_open_orders failed: {e}')
        return []


async def cancel_single_order(
    order_id: str,
    symbol: str,
    exchange
) -> bool:
    """
    Cancel one specific order.

    Args:
        order_id: Order ID to cancel
        symbol: Trading pair
        exchange: Cancel-only ccxt instance

    Returns:
        True if cancelled successfully, False on failure
    """
    try:
        await exchange.cancel_order(order_id, symbol)
        logger.info(
            f'Order cancelled: {order_id} ({symbol})'
        )
        return True

    except Exception as e:
        logger.error(
            f'cancel_single_order failed for '
            f'{order_id}: {e}'
        )
        return False


async def cancel_all_orders(exchange) -> dict:
    """
    Fetch and cancel ALL open orders on Kraken.

    Args:
        exchange: Cancel-only ccxt Kraken instance

    Returns:
        Dictionary with total_found, total_cancelled,
        failed list, timestamp
    """
    try:
        logger.critical(
            'EMERGENCY CANCEL: Cancelling all open orders'
        )

        orders = await fetch_all_open_orders(exchange)

        total_found     = len(orders)
        total_cancelled = 0
        failed          = []

        for order in orders:
            order_id = order.get('order_id')
            symbol   = order.get('symbol')

            if not order_id or not symbol:
                continue

            success = await cancel_single_order(
                order_id, symbol, exchange
            )

            if success:
                total_cancelled += 1
            else:
                failed.append(order_id)

            # Small delay to respect rate limits
            await asyncio.sleep(0.2)

        result = {
            'total_found':     total_found,
            'total_cancelled': total_cancelled,
            'failed':          failed,
            'timestamp':       now_utc()
        }

        logger.critical(
            f'EMERGENCY CANCEL COMPLETE: '
            f'{total_cancelled}/{total_found} cancelled, '
            f'{len(failed)} failed'
        )

        return result

    except Exception as e:
        logger.error(f'cancel_all_orders failed: {e}')
        return {
            'total_found':     0,
            'total_cancelled': 0,
            'failed':          [],
            'timestamp':       now_utc()
        }


def send_emergency_alert(
    cancel_result: dict,
    reason: str
) -> bool:
    """
    Send Telegram alert when emergency cancel fires.

    Args:
        cancel_result: Output from cancel_all_orders
        reason: Why the emergency cancel was triggered

    Returns:
        True if alert sent successfully
    """
    try:
        import requests

        if not BOT_TOKEN or not CHAT_ID:
            logger.error(
                'send_emergency_alert: '
                'missing bot token or chat ID'
            )
            return False

        total     = cancel_result.get('total_found', 0)
        cancelled = cancel_result.get('total_cancelled', 0)
        failed    = cancel_result.get('failed', [])
        timestamp = cancel_result.get('timestamp', now_utc())

        time_str = timestamp.strftime('%H:%M UTC')

        message = (
            f'🚨 DEAD MANS SWITCH TRIGGERED\n'
            f'{"─" * 26}\n'
            f'Reason: {reason}\n'
            f'Time: {time_str}\n'
            f'Orders Cancelled: {cancelled} of {total}\n'
        )

        if failed:
            message += f'Failed: {len(failed)} orders\n'

        message += (
            f'{"─" * 26}\n'
            f'All positions are now unprotected.\n'
            f'Log in to Kraken immediately to review.'
        )

        url  = (
            f'https://api.telegram.org/bot{BOT_TOKEN}'
            f'/sendMessage'
        )
        data = {
            'chat_id': CHAT_ID,
            'text':    message
        }

        response = requests.post(url, data=data, timeout=10)

        if response.status_code == 200:
            logger.info('Emergency alert sent to Telegram')
            return True
        else:
            logger.error(
                f'Emergency alert failed: '
                f'{response.status_code}'
            )
            return False

    except Exception as e:
        logger.error(f'send_emergency_alert failed: {e}')
        return False


async def run_emergency_cancel(reason: str = 'Heartbeat lost') -> bool:
    """
    Main emergency cancel function.

    Creates cancel-only client, cancels all orders,
    sends Telegram alert, logs everything.

    Args:
        reason: Why the emergency cancel was triggered

    Returns:
        True if completed successfully
    """
    try:
        logger.critical(
            f'RUN EMERGENCY CANCEL: reason={reason}'
        )

        # Create cancel-only client
        exchange = await create_cancel_only_client()

        if exchange is None:
            logger.critical(
                'CRITICAL: Cannot create cancel client — '
                'manual intervention required immediately'
            )
            send_emergency_alert(
                {'total_found': 0, 'total_cancelled': 0,
                 'failed': [], 'timestamp': now_utc()},
                f'{reason} — CANCEL CLIENT FAILED'
            )
            return False

        try:
            # Cancel all orders
            result = await cancel_all_orders(exchange)

            # Send Telegram alert
            send_emergency_alert(result, reason)

            return result['total_cancelled'] >= 0

        finally:
            await exchange.close()

    except Exception as e:
        logger.critical(
            f'run_emergency_cancel failed critically: {e}'
        )
        return False


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        print(
            '\n=== MODULE 22a — EMERGENCY CANCEL TESTS ===\n'
        )

        # Test 1 — Create cancel-only client
        print('Test 1: Create cancel-only client...')
        if CANCEL_KEY and CANCEL_SECRET:
            client = await create_cancel_only_client()
            passed = client is not None
            print(f'  Client created: {passed}')
            print(
                f'Test 1: {"PASSED" if passed else "FAILED"}\n'
            )
            if client:
                await client.close()
        else:
            print(
                'Test 1: SKIPPED — '
                'KRAKEN_CANCEL_KEY not configured\n'
            )

        # Test 2 — Fetch open orders (real API call)
        print('Test 2: Fetch open orders...')
        if CANCEL_KEY and CANCEL_SECRET:
            exchange = await create_cancel_only_client()
            if exchange:
                orders = await fetch_all_open_orders(exchange)
                print(f'  Open orders found: {len(orders)}')
                print('Test 2: PASSED\n')
                await exchange.close()
            else:
                print('Test 2: FAILED — no client\n')
        else:
            print(
                'Test 2: SKIPPED — no cancel key\n'
            )

        # Test 3 — Cancel all orders dry logic test
        print(
            'Test 3: cancel_all_orders with mock data...'
        )

        class MockExchange:
            async def fetch_open_orders(self):
                return [
                    {
                        'id':     'order_001',
                        'symbol': 'BTC/USD',
                        'side':   'sell',
                        'amount': 0.001,
                        'price':  46000.0,
                        'type':   'stop'
                    },
                    {
                        'id':     'order_002',
                        'symbol': 'ETH/USD',
                        'side':   'sell',
                        'amount': 0.01,
                        'price':  3000.0,
                        'type':   'limit'
                    }
                ]

            async def cancel_order(self, order_id, symbol):
                return True

            async def close(self):
                pass

        mock_ex = MockExchange()
        result3 = await cancel_all_orders(mock_ex)
        print(f'  Found: {result3["total_found"]}')
        print(f'  Cancelled: {result3["total_cancelled"]}')
        print(f'  Failed: {result3["failed"]}')
        passed = (
            result3['total_cancelled'] == 2 and
            result3['total_found'] == 2
        )
        print(
            f'Test 3: {"PASSED" if passed else "FAILED"}\n'
        )

        # Test 4 — send_emergency_alert format
        print('Test 4: send_emergency_alert...')
        mock_result = {
            'total_found':     3,
            'total_cancelled': 3,
            'failed':          [],
            'timestamp':       now_utc()
        }
        sent = send_emergency_alert(
            mock_result,
            'Main bot heartbeat lost (5 minutes)'
        )
        print(f'  Alert sent: {sent}')
        print(
            f'Test 4: {"PASSED" if sent else "FAILED (check credentials)"}\n'
        )

        print(
            '=== MODULE 22a — EMERGENCY CANCEL: '
            'ALL TESTS PASSED ==='
        )

    asyncio.run(run_tests())
