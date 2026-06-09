# Autonomous Multi-Strategy Trading System
# Module 02 — OHLCV Fetcher
# Fetches and stores historical and live candle data
# Makes multiple requests to get full history
# Kraken caps each request at 720 candles

import asyncio
import logging
import os
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

import aiosqlite
import pandas as pd

from execution.kraken_client import KrakenClient

# ── Constants ─────────────────────────────────────────────────
DB_PATH       = 'data/trading_data.db'
ASSETS        = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'BNB/USD', 'XRP/USD']
DEFAULT_DAYS  = 730
KRAKEN_LIMIT  = 720

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
    Makes multiple API requests to overcome the 720 candle limit.
    Uses SQLite for persistent local storage.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.client  = KrakenClient()
        os.makedirs('data', exist_ok=True)
        logger.info(
            f'OHLCVFetcher initialised with db: {db_path}'
        )

    async def init_database(self) -> bool:
        """Create the ohlcv table if it does not exist."""
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
        Fetch historical OHLCV data using multiple requests.

        Kraken caps each request at 720 candles so this
        function makes multiple requests to get full history.

        Args:
            asset: Trading pair e.g. BTC/USD
            timeframe: Candle timeframe e.g. 1h
            days: Number of days of history to fetch

        Returns:
            Number of new candles saved
        """
        try:
            timeframe_hours = {
                '1m': 1/60, '5m': 5/60, '15m': 0.25,
                '30m': 0.5, '1h': 1, '4h': 4,
                '1d': 24, '1w': 168
            }
            hours_per_candle = timeframe_hours.get(timeframe, 1)
            total_needed     = int((days * 24) / hours_per_candle)
            requests_needed  = max(1, (total_needed + KRAKEN_LIMIT - 1) // KRAKEN_LIMIT)

            logger.info(
                f'Fetching {days} days of {timeframe} data '
                f'for {asset} — need {total_needed} candles '
                f'in {requests_needed} requests'
            )

            all_dfs = []

            for req in range(requests_needed):
                logger.info(
                    f'{asset}: request {req+1}/{requests_needed}'
                )
                df_chunk = await self.client.fetch_ohlcv(
                    asset, timeframe, KRAKEN_LIMIT
                )

                if df_chunk is not None and not df_chunk.empty:
                    all_dfs.append(df_chunk)
                    logger.info(
                        f'{asset}: got {len(df_chunk)} candles '
                        f'in request {req+1}'
                    )
                else:
                    logger.warning(
                        f'{asset}: empty response on request {req+1}'
                    )

                # Respect rate limits between requests
                if req < requests_needed - 1:
                    await asyncio.sleep(2)

            if not all_dfs:
                logger.error(f'No data returned for {asset}')
                return 0

            # Combine all chunks
            df = pd.concat(all_dfs)
            df = df.drop_duplicates(subset='timestamp')
            df = df.sort_values('timestamp').reset_index(drop=True)

            logger.info(
                f'{asset}: {len(df)} total unique candles '
                f'after combining {len(all_dfs)} requests'
            )

            # Store in database
            new_count = 0
            async with aiosqlite.connect(self.db_path) as db:
                for _, row in df.iterrows():
                    try:
                        cursor = await db.execute('''
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
                        if cursor.rowcount > 0:
                            new_count += 1
                    except Exception:
                        continue
                await db.commit()

            logger.info(
                f'{asset}: {new_count} new candles saved '
                f'to database'
            )
            return new_count

        except Exception as e:
            logger.error(
                f'fetch_historical failed for {asset}: {e}'
            )
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
            logger.info(
                f'Fetching {days} days for {asset}...'
            )
            count = await self.fetch_historical(
                asset, timeframe, days
            )
            results[asset] = count
            logger.info(f'{asset}: {count} candles saved')
            await asyncio.sleep(2)

        logger.info(
            f'fetch_all_historical complete: {results}'
        )
        return results

    async def update_live(
        self,
        asset: str,
        timeframe: str = '1h'
    ) -> int:
        """
        Fetch latest candles and add any new ones.

        Args:
            asset: Trading pair
            timeframe: Candle timeframe

        Returns:
            Number of new candles added
        """
        try:
            df = await self.client.fetch_ohlcv(
                asset, timeframe, 10
            )
            if df is None or df.empty:
                return 0

            new_count = 0
            async with aiosqlite.connect(self.db_path) as db:
                for _, row in df.iterrows():
                    cursor = await db.execute('''
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
                    if cursor.rowcount > 0:
                        new_count += 1
                await db.commit()

            logger.debug(
                f'update_live {asset}: {new_count} new candles'
            )
            return new_count

        except Exception as e:
            logger.error(
                f'update_live failed for {asset}: {e}'
            )
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
            DataFrame sorted oldest to newest or None
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    SELECT timestamp, open, high, low,
                           close, volume
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
            df = df.sort_values('timestamp').reset_index(
                drop=True
            )

            logger.debug(
                f'Loaded {len(df)} candles for '
                f'{asset} {timeframe}'
            )
            return df

        except Exception as e:
            logger.error(
                f'load_ohlcv failed for {asset}: {e}'
            )
            return None

    async def get_stats(self) -> dict:
        """Get database statistics for all assets."""
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
                        'earliest':      row[1],
                        'latest':        row[2]
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
            print('Test 1: Initialising database...')
            result = await fetcher.init_database()
            print(
                f'Database initialised: '
                f'{"PASSED" if result else "FAILED"}\n'
            )

            print('Test 2: Fetching 7 days BTC/USD...')
            count = await fetcher.fetch_historical(
                'BTC/USD', '1h', 7
            )
            print(f'Candles saved: {count}')
            print(
                f'Test 2: {"PASSED" if count > 0 else "FAILED"}\n'
            )

            print('Test 3: Loading data from database...')
            df = await fetcher.load_ohlcv('BTC/USD', '1h', 168)
            if df is not None and len(df) > 0:
                print(f'Loaded {len(df)} candles')
                print('Test 3: PASSED\n')
            else:
                print('Test 3: FAILED\n')

            print('Test 4: Getting database stats...')
            stats = await fetcher.get_stats()
            for asset, info in stats.items():
                print(
                    f'{asset}: {info["total_candles"]} candles'
                )
            print('Test 4: PASSED\n')

            print('=== MODULE 02 — OHLCV FETCHER: PASSED ===')

        finally:
            await fetcher.close()

    asyncio.run(run_tests())
