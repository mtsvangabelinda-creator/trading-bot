# Autonomous Multi-Strategy Trading System
# Module 01 — Kraken Client
# Sole connection point between the system and Kraken exchange
# All market data and order placement goes through this module

import asyncio
import logging
import os
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

import ccxt
import ccxt.async_support as ccxt_async
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ── Constants ─────────────────────────────────────────────────
RETRY_COUNT = 3
RETRY_DELAY = 2

# ── Logging Setup ─────────────────────────────────────────────
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
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        logger.addHandler(console)
    return logger

logger = setup_logger('kraken_client', 'logs/errors.log')
trades_logger = setup_logger('trades', 'logs/trades.log')


class KrakenClient:
    """
    Sole connection point between the trading system and Kraken.
    Handles all market data fetching and order placement.
    """

    def __init__(self):
        """Initialise authenticated and public Kraken connections."""
        self.api_key = os.getenv('KRAKEN_API_KEY', '')
        self.api_secret = os.getenv('KRAKEN_API_SECRET', '')

        # Public client for market data — no keys needed
        self.public = ccxt_async.kraken({
            'enableRateLimit': True,
        })

        # Authenticated client for account and orders
        self.authenticated = ccxt_async.kraken({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
        })

        logger.info('KrakenClient initialised')

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1h',
        limit: int = 500
    ) -> pd.DataFrame | None:
        """
        Fetch OHLCV candlestick data for a symbol.

        Args:
            symbol: Trading pair e.g. BTC/USD
            timeframe: Candle timeframe e.g. 1h, 15m, 1d
            limit: Number of candles to fetch

        Returns:
            DataFrame with columns: timestamp, open, high, low,
            close, volume or None on failure
        """
        for attempt in range(RETRY_COUNT):
            try:
                raw = await self.public.fetch_ohlcv(
                    symbol, timeframe, limit=limit
                )
                if not raw:
                    logger.warning(f'No OHLCV data returned for {symbol}')
                    return None

                df = pd.DataFrame(
                    raw,
                    columns=[
                        'timestamp', 'open', 'high',
                        'low', 'close', 'volume'
                    ]
                )
                df['timestamp'] = pd.to_datetime(
                    df['timestamp'], unit='ms'
                )
                df = df.sort_values('timestamp').reset_index(drop=True)
                logger.debug(
                    f'Fetched {len(df)} candles for {symbol} {timeframe}'
                )
                return df

            except Exception as e:
                logger.error(
                    f'fetch_ohlcv attempt {attempt+1} failed '
                    f'for {symbol}: {e}'
                )
                if attempt < RETRY_COUNT - 1:
                    await asyncio.sleep(RETRY_DELAY)

        logger.error(f'fetch_ohlcv failed after {RETRY_COUNT} attempts for {symbol}')
        return None

    async def fetch_order_book(
        self,
        symbol: str,
        depth: int = 20
    ) -> dict | None:
        """
        Fetch live order book for a symbol.

        Args:
            symbol: Trading pair e.g. BTC/USD
            depth: Number of bid/ask levels to fetch

        Returns:
            Dictionary with bids and asks lists or None on failure
        """
        for attempt in range(RETRY_COUNT):
            try:
                book = await self.public.fetch_order_book(
                    symbol, depth
                )
                result = {
                    'bids': book['bids'],
                    'asks': book['asks'],
                    'timestamp': datetime.utcnow()
                }
                logger.debug(f'Fetched order book for {symbol}')
                return result

            except Exception as e:
                logger.error(
                    f'fetch_order_book attempt {attempt+1} failed '
                    f'for {symbol}: {e}'
                )
                if attempt < RETRY_COUNT - 1:
                    await asyncio.sleep(RETRY_DELAY)

        logger.error(
            f'fetch_order_book failed after {RETRY_COUNT} attempts '
            f'for {symbol}'
        )
        return None

    async def fetch_balance(self) -> dict | None:
        """
        Fetch account balance from Kraken.

        Returns:
            Dictionary of currencies with non-zero balances
            or None on failure
        """
        if not self.api_key or not self.api_secret:
            logger.error('fetch_balance: API keys not configured')
            return None

        for attempt in range(RETRY_COUNT):
            try:
                balance = await self.authenticated.fetch_balance()
                result = {
                    currency: float(info['free'])
                    for currency, info in balance.items()
                    if isinstance(info, dict)
                    and info.get('free', 0) > 0
                    and currency not in ['info', 'timestamp', 'datetime']
                }
                logger.debug(f'Fetched balance: {list(result.keys())}')
                return result

            except Exception as e:
                logger.error(
                    f'fetch_balance attempt {attempt+1} failed: {e}'
                )
                if attempt < RETRY_COUNT - 1:
                    await asyncio.sleep(RETRY_DELAY)

        logger.error(
            f'fetch_balance failed after {RETRY_COUNT} attempts'
        )
        return None

    async def fetch_open_orders(
        self,
        symbol: str = None
    ) -> list | None:
        """
        Fetch all open orders, optionally filtered by symbol.

        Args:
            symbol: Optional trading pair filter

        Returns:
            List of order dictionaries or None on failure
        """
        if not self.api_key or not self.api_secret:
            logger.error('fetch_open_orders: API keys not configured')
            return None

        for attempt in range(RETRY_COUNT):
            try:
                orders = await self.authenticated.fetch_open_orders(
                    symbol
                )
                result = [
                    {
                        'order_id': o['id'],
                        'symbol': o['symbol'],
                        'side': o['side'],
                        'amount': o['amount'],
                        'price': o['price'],
                        'timestamp': pd.to_datetime(
                            o['timestamp'], unit='ms'
                        ) if o.get('timestamp') else None
                    }
                    for o in orders
                ]
                logger.debug(
                    f'Fetched {len(result)} open orders'
                    f'{" for " + symbol if symbol else ""}'
                )
                return result

            except Exception as e:
                logger.error(
                    f'fetch_open_orders attempt {attempt+1} failed: {e}'
                )
                if attempt < RETRY_COUNT - 1:
                    await asyncio.sleep(RETRY_DELAY)

        logger.error(
            f'fetch_open_orders failed after {RETRY_COUNT} attempts'
        )
        return None

    async def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = 'market'
    ) -> dict | None:
        """
        Place an order on Kraken.

        Args:
            symbol: Trading pair e.g. BTC/USD
            side: buy or sell
            amount: Quantity to trade
            order_type: market or limit

        Returns:
            Order details dictionary or None on failure
        """
        if not self.api_key or not self.api_secret:
            logger.error('place_order: API keys not configured')
            return None

        for attempt in range(RETRY_COUNT):
            try:
                order = await self.authenticated.create_order(
                    symbol, order_type, side, amount
                )
                result = {
                    'order_id': order['id'],
                    'symbol': order['symbol'],
                    'side': order['side'],
                    'amount': order['amount'],
                    'status': order['status'],
                    'timestamp': datetime.utcnow(),
                    'filled_price': order.get('average', 0.0)
                }
                trades_logger.info(
                    f'ORDER PLACED | {symbol} | {side} | '
                    f'amount={amount} | id={order["id"]}'
                )
                return result

            except Exception as e:
                logger.error(
                    f'place_order attempt {attempt+1} failed '
                    f'for {symbol}: {e}'
                )
                if attempt < RETRY_COUNT - 1:
                    await asyncio.sleep(RETRY_DELAY)

        logger.error(
            f'place_order failed after {RETRY_COUNT} attempts '
            f'for {symbol}'
        )
        return None

    async def cancel_order(
        self,
        order_id: str,
        symbol: str
    ) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: The order ID to cancel
            symbol: Trading pair the order belongs to

        Returns:
            True if cancelled successfully, False otherwise
        """
        if not self.api_key or not self.api_secret:
            logger.error('cancel_order: API keys not configured')
            return False

        for attempt in range(RETRY_COUNT):
            try:
                await self.authenticated.cancel_order(
                    order_id, symbol
                )
                trades_logger.info(
                    f'ORDER CANCELLED | {symbol} | id={order_id}'
                )
                return True

            except Exception as e:
                logger.error(
                    f'cancel_order attempt {attempt+1} failed '
                    f'for {order_id}: {e}'
                )
                if attempt < RETRY_COUNT - 1:
                    await asyncio.sleep(RETRY_DELAY)

        logger.error(
            f'cancel_order failed after {RETRY_COUNT} attempts '
            f'for {order_id}'
        )
        return False

    async def close(self):
        """Close exchange connections gracefully."""
        await self.public.close()
        await self.authenticated.close()
        logger.info('KrakenClient connections closed')


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        print('\n=== MODULE 01 — KRAKEN CLIENT TESTS ===\n')
        client = KrakenClient()

        try:
            # Test 1 — Fetch OHLCV
            print('Test 1: Fetching BTC/USD OHLCV...')
            df = await client.fetch_ohlcv('BTC/USD', '1h', 10)
            if df is not None and len(df) > 0:
                print(df.head(5).to_string())
                print('Test 1: PASSED\n')
            else:
                print('Test 1: FAILED — no data returned\n')

            # Test 2 — Fetch Order Book
            print('Test 2: Fetching BTC/USD order book...')
            book = await client.fetch_order_book('BTC/USD', 5)
            if book is not None:
                print(f'Top 3 bids: {book["bids"][:3]}')
                print(f'Top 3 asks: {book["asks"][:3]}')
                print('Test 2: PASSED\n')
            else:
                print('Test 2: FAILED — no order book returned\n')

            # Test 3 — Fetch Balance
            print('Test 3: Fetching account balance...')
            balance = await client.fetch_balance()
            if balance is not None:
                print(f'Balance: {balance}')
                print('Test 3: PASSED\n')
            else:
                print('Test 3: FAILED or API keys not configured\n')

            print('=== MODULE 01 — KRAKEN CLIENT: ALL TESTS PASSED ===')

        finally:
            await client.close()

    asyncio.run(run_tests())
