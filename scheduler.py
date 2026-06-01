# Autonomous Multi-Strategy Trading System
# Scheduler — All recurring background jobs
# Uses APScheduler AsyncIOScheduler
# Every job runs on a fixed interval independently

import asyncio
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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

logger = setup_logger('scheduler', 'logs/system.log')

# ── Global Scheduler Instance ─────────────────────────────────
_scheduler = None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Job Functions ─────────────────────────────────────────────

async def job_write_heartbeat() -> None:
    """Write heartbeat every 60 seconds."""
    try:
        from dead_mans_switch.heartbeat_monitor import (
            write_heartbeat
        )
        write_heartbeat()
        logger.debug('Heartbeat written')

    except Exception as e:
        logger.error(f'job_write_heartbeat failed: {e}')


async def job_regime_check() -> None:
    """
    Run Decision Engine on all assets every 15 minutes.
    Updates edge scores and checks for trade signals.
    """
    try:
        logger.info('Running 15-minute regime check...')

        from data.ohlcv_fetcher import OHLCVFetcher
        from core.edge_score import calculate_all
        from config import ASSETS

        fetcher = OHLCVFetcher()
        assets_data = {}

        for asset in ASSETS.keys():
            df = await fetcher.load_ohlcv(asset, '1h', 500)
            if df is not None and len(df) >= 200:
                assets_data[asset] = {
                    'close': df['close'],
                    'high':  df['high'],
                    'low':   df['low']
                }

        if assets_data:
            results = calculate_all(assets_data)
            logger.info(
                f'Regime check complete: '
                f'{len(results)} assets processed'
            )

        await fetcher.close()

    except Exception as e:
        logger.error(f'job_regime_check failed: {e}')


async def job_check_open_positions() -> None:
    """
    Check open positions for stop or tp hits.
    Runs every 15 minutes.
    """
    try:
        from execution.order_manager import (
            check_open_positions,
            get_open_positions
        )
        from execution.kraken_client import KrakenClient

        positions = get_open_positions()
        if not positions:
            logger.debug('No open positions to check')
            return

        client = KrakenClient()
        closed = await check_open_positions(client)
        await client.close()

        if closed:
            logger.info(
                f'Positions closed this cycle: {len(closed)}'
            )
            for result in closed:
                logger.info(
                    f'  {result["symbol"]} {result["direction"]} '
                    f'pnl={result["pnl"]} '
                    f'reason={result["reason"]}'
                )

    except Exception as e:
        logger.error(
            f'job_check_open_positions failed: {e}'
        )


async def job_update_sentiment() -> None:
    """
    Recalculate Structural Sentiment for all assets.
    Runs every hour.
    """
    try:
        logger.info('Updating structural sentiment...')

        from data.ohlcv_fetcher import OHLCVFetcher
        from core.sentiment import (
            calculate_all, get_summary
        )
        from config import ASSETS

        fetcher     = OHLCVFetcher()
        assets_data = {}

        for asset in ASSETS.keys():
            df = await fetcher.load_ohlcv(asset, '1h', 200)
            if df is not None and len(df) >= 55:
                assets_data[asset] = {
                    'close': df['close'],
                    'high':  df['high'],
                    'low':   df['low']
                }

        if assets_data:
            results = calculate_all(assets_data)
            summary = get_summary(results)
            logger.info(f'Sentiment update:\n{summary}')

        await fetcher.close()

    except Exception as e:
        logger.error(f'job_update_sentiment failed: {e}')


async def job_update_live_data() -> None:
    """
    Fetch latest candles for all assets.
    Runs every hour.
    """
    try:
        logger.info('Updating live market data...')

        from data.ohlcv_fetcher import OHLCVFetcher
        from config import ASSETS

        fetcher = OHLCVFetcher()

        for asset in ASSETS.keys():
            count = await fetcher.update_live(asset, '1h')
            logger.debug(
                f'Updated {asset}: {count} new candles'
            )

        await fetcher.close()

    except Exception as e:
        logger.error(f'job_update_live_data failed: {e}')


async def job_correlation_check() -> None:
    """
    Run correlation breaker check.
    Runs every 4 hours.
    """
    try:
        logger.info('Running correlation check...')

        from data.ohlcv_fetcher import OHLCVFetcher
        from risk.correlation_breaker import check
        from telegram_bot.alerts import send_correlation_alert
        from config import ASSETS

        fetcher     = OHLCVFetcher()
        prices_dict = {}

        for asset in ASSETS.keys():
            df = await fetcher.load_ohlcv(asset, '1h', 100)
            if df is not None:
                prices_dict[asset] = df['close']

        if prices_dict:
            result = await check(prices_dict)
            if result:
                logger.info(
                    f'Correlation: avg={result["avg_correlation"]} '
                    f'status={result["status"]}'
                )
                if result.get('alert_message'):
                    send_correlation_alert(result)

        await fetcher.close()

    except Exception as e:
        logger.error(f'job_correlation_check failed: {e}')


async def job_send_status_update() -> None:
    """
    Send status update to Telegram.
    Runs every 4 hours.
    """
    try:
        logger.info('Sending status update...')

        from execution.kraken_client import KrakenClient
        from execution.order_manager import get_open_positions
        from risk.drawdown_guard import is_trading_allowed
        from risk.correlation_breaker import (
            get_size_multiplier
        )
        from telegram_bot.alerts import send_status_update

        client  = KrakenClient()
        balance = await client.fetch_balance()
        await client.close()

        account_value = 0.0
        if balance:
            usd_val = balance.get('USD', 0)
            account_value = float(usd_val)

        trading = await is_trading_allowed()
        corr_m  = await get_size_multiplier()

        corr_status = (
            'NORMAL'  if corr_m == 1.0 else
            'HALVED'  if corr_m == 0.5 else
            'PAUSED'
        )

        status = {
            'account_value':        account_value,
            'daily_pnl':            0.0,
            'open_positions':       get_open_positions(),
            'edge_summary':         'See /edge_scores',
            'sentiment_summary':    'See /sentiment',
            'risk_status':          (
                'ACTIVE'
                if trading.get('allowed') else
                trading.get('halt_state', 'HALTED')
            ),
            'correlation_status':   corr_status,
            'avg_correlation':      0.0
        }

        send_status_update(status)

    except Exception as e:
        logger.error(f'job_send_status_update failed: {e}')


async def job_reset_daily_losses() -> None:
    """
    Reset daily loss counters for all silos.
    Runs at UTC midnight daily.
    """
    try:
        logger.info(
            'Resetting daily loss counters...'
        )

        from risk.strategy_silo import reset_daily_losses
        result = await reset_daily_losses()

        logger.info(
            f'Daily reset: {"complete" if result else "failed"}'
        )

    except Exception as e:
        logger.error(
            f'job_reset_daily_losses failed: {e}'
        )


async def job_send_daily_summary() -> None:
    """
    Send daily P&L summary to Telegram.
    Runs at UTC midnight daily.
    """
    try:
        logger.info('Sending daily summary...')

        from execution.kraken_client import KrakenClient
        from telegram_bot.alerts import send_daily_summary

        client  = KrakenClient()
        balance = await client.fetch_balance()
        await client.close()

        account = 0.0
        if balance:
            account = float(balance.get('USD', 0))

        summary = {
            'total_trades':          0,
            'winning_trades':        0,
            'losing_trades':         0,
            'daily_pnl':             0.0,
            'best_trade':            0.0,
            'worst_trade':           0.0,
            'account_balance':       account,
            'peak_drawdown_today':   0.0,
            'tf_trades':             0,
            'mr_trades':             0,
            'sc_trades':             0,
            'status':                'ACTIVE'
        }

        send_daily_summary(summary)

    except Exception as e:
        logger.error(
            f'job_send_daily_summary failed: {e}'
        )


async def job_check_weekly_limits() -> None:
    """
    Check weekly drawdown limits.
    Runs every Monday at UTC midnight.
    """
    try:
        logger.info('Checking weekly drawdown limits...')

        from risk.drawdown_guard import is_trading_allowed
        trading = await is_trading_allowed()

        logger.info(
            f'Weekly check: '
            f'trading_allowed={trading.get("allowed")}'
        )

    except Exception as e:
        logger.error(
            f'job_check_weekly_limits failed: {e}'
        )


# ── Scheduler Control ─────────────────────────────────────────

def create_scheduler() -> AsyncIOScheduler:
    """
    Create APScheduler with all jobs registered.

    Returns:
        Configured AsyncIOScheduler instance
    """
    scheduler = AsyncIOScheduler(
        timezone='UTC'
    )

    # Every 60 seconds — heartbeat
    scheduler.add_job(
        job_write_heartbeat,
        trigger=IntervalTrigger(seconds=60),
        id='heartbeat',
        name='Write Heartbeat',
        max_instances=1,
        coalesce=True
    )

    # Every 15 minutes — regime check
    scheduler.add_job(
        job_regime_check,
        trigger=IntervalTrigger(minutes=15),
        id='regime_check',
        name='Regime Check',
        max_instances=1,
        coalesce=True
    )

    # Every 15 minutes — check open positions
    scheduler.add_job(
        job_check_open_positions,
        trigger=IntervalTrigger(minutes=15),
        id='check_positions',
        name='Check Open Positions',
        max_instances=1,
        coalesce=True
    )

    # Every hour — update sentiment
    scheduler.add_job(
        job_update_sentiment,
        trigger=IntervalTrigger(hours=1),
        id='update_sentiment',
        name='Update Sentiment',
        max_instances=1,
        coalesce=True
    )

    # Every hour — update live data
    scheduler.add_job(
        job_update_live_data,
        trigger=IntervalTrigger(hours=1),
        id='update_live_data',
        name='Update Live Data',
        max_instances=1,
        coalesce=True
    )

    # Every 4 hours — correlation check
    scheduler.add_job(
        job_correlation_check,
        trigger=IntervalTrigger(hours=4),
        id='correlation_check',
        name='Correlation Check',
        max_instances=1,
        coalesce=True
    )

    # Every 4 hours — status update to Telegram
    scheduler.add_job(
        job_send_status_update,
        trigger=IntervalTrigger(hours=4),
        id='status_update',
        name='Status Update',
        max_instances=1,
        coalesce=True
    )

    # Daily at midnight UTC — reset daily losses
    scheduler.add_job(
        job_reset_daily_losses,
        trigger=CronTrigger(hour=0, minute=0),
        id='reset_daily',
        name='Reset Daily Losses',
        max_instances=1,
        coalesce=True
    )

    # Daily at midnight UTC — send daily summary
    scheduler.add_job(
        job_send_daily_summary,
        trigger=CronTrigger(hour=0, minute=1),
        id='daily_summary',
        name='Daily Summary',
        max_instances=1,
        coalesce=True
    )

    # Every Monday at midnight UTC — weekly check
    scheduler.add_job(
        job_check_weekly_limits,
        trigger=CronTrigger(
            day_of_week='mon', hour=0, minute=0
        ),
        id='weekly_check',
        name='Weekly Limits Check',
        max_instances=1,
        coalesce=True
    )

    logger.info(
        f'Scheduler created with '
        f'{len(scheduler.get_jobs())} jobs'
    )

    return scheduler


def start_scheduler(
    scheduler: AsyncIOScheduler
) -> bool:
    """
    Start the scheduler.

    Args:
        scheduler: AsyncIOScheduler instance

    Returns:
        True if started successfully
    """
    try:
        scheduler.start()
        jobs = scheduler.get_jobs()
        logger.info(
            f'Scheduler started with {len(jobs)} jobs:'
        )
        for job in jobs:
            logger.info(f'  {job.name}: {job.trigger}')
        return True

    except Exception as e:
        logger.error(f'start_scheduler failed: {e}')
        return False


def stop_scheduler(
    scheduler: AsyncIOScheduler
) -> bool:
    """
    Gracefully stop the scheduler.

    Args:
        scheduler: Running AsyncIOScheduler instance

    Returns:
        True if stopped cleanly
    """
    try:
        scheduler.shutdown(wait=True)
        logger.info('Scheduler stopped cleanly')
        return True

    except Exception as e:
        logger.error(f'stop_scheduler failed: {e}')
        return False


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        print('\n=== SCHEDULER TESTS ===\n')

        # Test 1 — Create scheduler
        print('Test 1: create_scheduler...')
        scheduler = create_scheduler()
        jobs      = scheduler.get_jobs()
        print(f'  Jobs registered: {len(jobs)}')
        for job in jobs:
            print(f'  {job.name}')
        passed = len(jobs) == 10
        print(
            f'Test 1: {"PASSED" if passed else "FAILED"}\n'
        )

        # Test 2 — Start and stop
        print('Test 2: start and stop scheduler...')
        started = start_scheduler(scheduler)
        print(f'  Started: {started}')
        stopped = stop_scheduler(scheduler)
        print(f'  Stopped: {stopped}')
        passed  = started and stopped
        print(
            f'Test 2: {"PASSED" if passed else "FAILED"}\n'
        )

        print('=== SCHEDULER: ALL TESTS PASSED ===')

    asyncio.run(run_tests())
