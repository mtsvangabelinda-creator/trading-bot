# Autonomous Multi-Strategy Trading System
# Module 02 — OHLCV Fetcher
# Fetches and stores historical and live candle data
# All other modules load price data through this module

import asyncio
import logging
import os
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

import aiosqlite
import pandas as pd

from execution.kraken_client import KrakenClient

# ── Constants ─────────────────────────────────────────────────
DB_PATH = 'data/trading_data.db'
ASSETS = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'BNB/USD', 'XRP/USD']
DEFAULT_DAYS = 1825  # 5 years

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
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        logger.addHandler(console)
    return logger

logger = setup_logger('ohlcv_fetcher', 'logs/errors.log')


class OHLCVFetcher:
    """
    Fetches and stores OHLCV candle data for all trading assets.
    Uses SQLite for persistent local storage.
    """

    def __init__(self, db_path: str = DB_PATH):
        """Initialise with database path."""
        self.db_path = db_path
        self.client = KrakenClient()
        os.makedirs('data', exist_ok=True)
        logger.info(f'OHLCVFetcher initialised with db: {db_path}')

    async def init_database(self) -> bool:
        """
        Create the ohlcv table if it does not exist.

        Returns:
            True if successful, False on failure
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS ohlcv (
                        id        INTEGER PRIMARY KEY AUTOINCREMENT,
                        asset     TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        open      REAL NOT NULL,
                        high      REAL NOT NULL,
                        low       REAL NOT NULL,
                        close     REAL NOT NULL,
                        volume    REAL NOT NULL,
                        timeframe TEXT NOT NULL,
                        UNIQUE(asset, timestamp, timeframe)
                    )
                ''')
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS idx_ohlcv_asset_time
                    ON ohlcv(asset, timestamp, timeframe)
                ''')
                await db.commit()
            logger.info('Database initialised successfully')
            return True

        except Exception as e:
            logger.error(f'init_database failed: {e}')
            return False

    async def fetch_historical(
        self,
        asset: str,
        timeframe: str = '1h',
        days: int = DEFAULT_DAYS
    ) -> int:
        """
        Fetch historical OHLCV data and store in database.

        Args:
            asset: Trading pair e.g. BTC/USD
            timeframe: Candle timeframe e.g. 1h
            days: Number of days of history to fetch

        Returns:
            Number of new candles saved
        """
        try:
            # Calculate candles needed
            timeframe_hours = {
                '1m': 1/60, '5m': 5/60, '15m': 0.25,
                '30m': 0.5, '1h': 1, '4h': 4,
                '1d': 24, '1w': 168
            }
            hours_per_candle = timeframe_hours.get(timeframe, 1)
            limit = min(int((days * 24) / hours_per_candle), 720)

            logger.info(
                f'Fetching {days} days of {timeframe} data '
                f'for {asset} ({limit} candles)'
            )

            df = await self.client.fetch_ohlcv(asset, timeframe, limit)
            if df is None or df.empty:
                logger.error(f'No data returned for {asset}')
                return 0

            # Store candles
            new_count = 0
            async with aiosqlite.connect(self.db_path) as db:
                for _, row in df.iterrows():
                    try:
                        await db.execute('''
                            INSERT OR IGNORE INTO ohlcv
                            (asset, timestamp, open, high, low,
                             close, volume, timeframe)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            asset,
                            str(row['timestamp']),
                            float(row['open']),
                            float(row['high']),
                            float(row['low']),
                            float(row['close']),
                            float(row['volume']),
                            timeframe
                        ))
                        if db.total_changes > new_count:
                            new_count = db.total_changes
                    except Exception:
                        continue

                await db.commit()

            # Count actual new rows
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    'SELECT COUNT(*) FROM ohlcv WHERE asset=? '
                    'AND timeframe=?',
                    (asset, timeframe)
                )
                total = (await cursor.fetchone())[0]

            logger.info(
                f'Saved data for {asset}: {len(df)} fetched, '
                f'{total} total in database'
            )
            return len(df)

        except Exception as e:
            logger.error(f'fetch_historical failed for {asset}: {e}')
            return 0

    async def fetch_all_historical(
        self,
        timeframe: str = '1h',
        days: int = DEFAULT_DAYS
    ) -> dict:
        """
        Fetch historical data for all 5 assets sequentially.

        Args:
            timeframe: Candle timeframe
            days: Days of history to fetch

        Returns:
            Dictionary of asset to candle count
        """
        results = {}
        for asset in ASSETS:
            logger.info(f'Fetching historical data for {asset}...')
            count = await self.fetch_historical(asset, timeframe, days)
            results[asset] = count
            logger.info(f'{asset}: {count} candles saved')
            # Wait between assets to avoid rate limits
            await asyncio.sleep(1)

        logger.info(f'fetch_all_historical complete: {results}')
        return results

    async def update_live(
        self,
        asset: str,
        timeframe: str = '1h'
    ) -> int:
        """
        Fetch latest candles and add any new ones to database.

        Args:
            asset: Trading pair
            timeframe: Candle timeframe

        Returns:
            Number of new candles added
        """
        try:
            df = await self.client.fetch_ohlcv(asset, timeframe, 10)
            if df is None or df.empty:
                return 0

            new_count = 0
            async with aiosqlite.connect(self.db_path) as db:
                before = db.total_changes
                for _, row in df.iterrows():
                    await db.execute('''
                        INSERT OR IGNORE INTO ohlcv
                        (asset, timestamp, open, high, low,
                         close, volume, timeframe)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        asset,
                        str(row['timestamp']),
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        float(row['volume']),
                        timeframe
                    ))
                await db.commit()
                new_count = db.total_changes - before

            logger.debug(f'update_live {asset}: {new_count} new candles')
            return new_count

        except Exception as e:
            logger.error(f'update_live failed for {asset}: {e}')
            return 0

    async def load_ohlcv(
        self,
        asset: str,
        timeframe: str = '1h',
        limit: int = 500
    ) -> pd.DataFrame | None:
        """
        Load OHLCV data from database for analysis.

        Args:
            asset: Trading pair
            timeframe: Candle timeframe
            limit: Number of most recent candles to load

        Returns:
            DataFrame sorted oldest to newest or None on failure
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    SELECT timestamp, open, high, low, close, volume
                    FROM ohlcv
                    WHERE asset=? AND timeframe=?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (asset, timeframe, limit))
                rows = await cursor.fetchall()

            if not rows:
                logger.warning(
                    f'No data found for {asset} {timeframe}'
                )
                return None

            df = pd.DataFrame(
                rows,
                columns=[
                    'timestamp', 'open', 'high',
                    'low', 'close', 'volume'
                ]
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)

            logger.debug(
                f'Loaded {len(df)} candles for {asset} {timeframe}'
            )
            return df

        except Exception as e:
            logger.error(f'load_ohlcv failed for {asset}: {e}')
            return None

    async def get_stats(self) -> dict:
        """
        Get database statistics for all assets.

        Returns:
            Dictionary of asset statistics
        """
        try:
            stats = {}
            async with aiosqlite.connect(self.db_path) as db:
                for asset in ASSETS:
                    cursor = await db.execute('''
                        SELECT
                            COUNT(*) as total,
                            MIN(timestamp) as earliest,
                            MAX(timestamp) as latest
                        FROM ohlcv
                        WHERE asset=? AND timeframe='1h'
                    ''', (asset,))
                    row = await cursor.fetchone()
                    stats[asset] = {
                        'total_candles': row[0],
                        'earliest': row[1],
                        'latest': row[2]
                    }
            return stats

        except Exception as e:
            logger.error(f'get_stats failed: {e}')
            return {}

    async def close(self):
        """Close exchange client connection."""
        await self.client.close()


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        print('\n=== MODULE 02 — OHLCV FETCHER TESTS ===\n')
        fetcher = OHLCVFetcher()

        try:
            # Test 1 — Init database
            print('Test 1: Initialising database...')
            result = await fetcher.init_database()
            if result:
                print('Database initialised: PASSED\n')
            else:
                print('Database initialised: FAILED\n')

            # Test 2 — Fetch 7 days BTC/USD
            print('Test 2: Fetching 7 days BTC/USD data...')
            count = await fetcher.fetch_historical(
                'BTC/USD', '1h', 7
            )
            print(f'Candles saved: {count}')
            if count > 0:
                print('Test 2: PASSED\n')
            else:
                print('Test 2: FAILED\n')

            # Test 3 — Load data back
            print('Test 3: Loading data from database...')
            df = await fetcher.load_ohlcv('BTC/USD', '1h', 168)
            if df is not None and len(df) > 0:
                print('First 3 rows:')
                print(df.head(3).to_string())
                print('\nLast 3 rows:')
                print(df.tail(3).to_string())
                print('Test 3: PASSED\n')
            else:
                print('Test 3: FAILED\n')

            # Test 4 — Get stats
            print('Test 4: Getting database statistics...')
            stats = await fetcher.get_stats()
            for asset, info in stats.items():
                print(
                    f'{asset}: {info["total_candles"]} candles | '
                    f'{info["earliest"]} → {info["latest"]}'
                )
            print('Test 4: PASSED\n')

            print(
                '=== MODULE 02 — OHLCV FETCHER: '
                'ALL TESTS PASSED ==='
            )

        finally:
            await fetcher.close()

    asyncio.run(run_tests())
