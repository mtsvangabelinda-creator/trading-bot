# Autonomous Multi-Strategy Trading System
# Orchestrator — Master Control Program
# Single entry point for the entire trading system
# Initialises every module coordinates all components
# Runs continuously 24/7 in live mode

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────
def setup_logger(name: str, log_file: str) -> logging.Logger:
    os.makedirs('logs', exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_file,
            maxBytes=10485760,
            backupCount=7
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

logger = setup_logger('orchestrator', 'logs/system.log')

# ── Environment ───────────────────────────────────────────────
ENVIRONMENT = os.getenv('ENVIRONMENT', 'backtest').lower()

# ── Required Environment Variables ───────────────────────────
REQUIRED_VARS = [
    'KRAKEN_API_KEY',
    'KRAKEN_API_SECRET',
    'KRAKEN_CANCEL_KEY',
    'KRAKEN_CANCEL_SECRET',
    'TELEGRAM_BOT_TOKEN',
    'TELEGRAM_AUTHORISED_USER_ID',
    'ENVIRONMENT'
]

# ── Global State ──────────────────────────────────────────────
_running    = True
_scheduler  = None
_exchange   = None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Step 1: Environment Verification ─────────────────────────

def verify_environment() -> bool:
    """
    Verify all required environment variables are present.

    Returns:
        True if all present, False if any missing
    """
    missing = []
    for var in REQUIRED_VARS:
        if not os.getenv(var):
            missing.append(var)

    if missing:
        logger.error(
            f'Missing environment variables: {missing}'
        )
        return False

    logger.info(
        f'Environment verified: '
        f'ENVIRONMENT={ENVIRONMENT}'
    )
    return True


# ── Step 2: Database Initialisation ──────────────────────────

async def init_databases() -> bool:
    """
    Initialise all module databases.

    Returns:
        True if all succeed, False if any fail
    """
    try:
        logger.info('Initialising databases...')

        from data.ohlcv_fetcher import OHLCVFetcher
        from risk.drawdown_guard import init_db as dd_init
        from risk.strategy_silo import init_db as silo_init
        from risk.correlation_breaker import (
            init_db as corr_init
        )
        from sentinel.sentinel import init_sentinel_state

        fetcher = OHLCVFetcher()
        ok1     = await fetcher.init_database()
        await fetcher.close()

        ok2 = await dd_init()
        ok3 = await silo_init()
        ok4 = await corr_init()
        ok5 = await init_sentinel_state()

        all_ok = ok1 and ok2 and ok3 and ok4 and ok5

        if all_ok:
            logger.info('All databases initialised')
        else:
            logger.error(
                f'Database init failures: '
                f'ohlcv={ok1} dd={ok2} silo={ok3} '
                f'corr={ok4} sentinel={ok5}'
            )

        return all_ok

    except Exception as e:
        logger.error(f'init_databases failed: {e}')
        return False


# ── Step 3: Exchange Connection ───────────────────────────────

async def init_exchange() -> bool:
    """
    Initialise and test Kraken exchange connection.

    Returns:
        True if connection successful
    """
    global _exchange

    try:
        logger.info('Initialising exchange connection...')

        from execution.kraken_client import KrakenClient
        _exchange = KrakenClient()

        # Test with BTC/USD order book
        book = await _exchange.fetch_order_book(
            'BTC/USD', 5
        )

        if book is None:
            logger.error(
                'Exchange connection test failed — '
                'no order book returned'
            )
            return False

        btc_mid = (
            float(book['bids'][0][0]) +
            float(book['asks'][0][0])
        ) / 2

        logger.info(
            f'Exchange connected: BTC/USD mid=${btc_mid:,.2f}'
        )
        return True

    except Exception as e:
        logger.error(f'init_exchange failed: {e}')
        return False


# ── Step 4: Telegram Startup ──────────────────────────────────

async def send_startup_message() -> None:
    """Send startup notification to Telegram."""
    try:
        from telegram_bot.alerts import send_message
        from config import ASSETS

        asset_list = ' '.join(
            [a.split('/')[0] for a in ASSETS.keys()]
        )

        message = (
            f'TRADING SYSTEM ONLINE\n'
            f'{"─" * 22}\n'
            f'Environment: {ENVIRONMENT.upper()}\n'
            f'Assets: {asset_list}\n'
            f'Time: '
            f'{now_utc().strftime("%Y-%m-%d %H:%M UTC")}\n'
            f'All systems initialised successfully'
        )

        send_message(message)
        logger.info('Startup message sent to Telegram')

    except Exception as e:
        logger.warning(
            f'send_startup_message failed '
            f'(non-critical): {e}'
        )


# ── Main Trading Loop ─────────────────────────────────────────

async def run_asset_cycle(
    symbol: str,
    dry_run: bool = True
) -> dict:
    """
    Run one complete decision and execution cycle
    for one asset.

    Args:
        symbol: Trading pair
        dry_run: True for simulation

    Returns:
        Dictionary with cycle result details
    """
    try:
        import time
        start = time.time()

        from data.ohlcv_fetcher import OHLCVFetcher
        from core.edge_score import calculate as edge_calc
        from core.sentiment import calculate as sent_calc
        from risk.drawdown_guard import (
            is_trading_allowed as dd_allowed
        )
        from risk.strategy_silo import is_active
        from risk.correlation_breaker import (
            get_size_multiplier as corr_mult
        )
        from risk.time_filters import (
            is_trading_allowed as tf_allowed,
            get_size_multiplier as tf_mult,
            get_parameter_overrides
        )
        from sentinel.sentinel import check_all_filters
        from execution.order_manager import (
            get_open_positions, open_position
        )
        from strategies.trend_following import (
            run_strategy_iteration as tf_run
        )
        from strategies.mean_reversion import (
            run_strategy_iteration as mr_run
        )
        from strategies.scalper import (
            run_scalper_iteration as sc_run
        )
        from telegram_bot.commands import is_system_paused
        from config import ASSETS

        # Manual pause check
        if is_system_paused():
            return {
                'symbol':  symbol,
                'result':  'paused',
                'reason':  'System manually paused'
            }

        # Time filter check
        if not tf_allowed():
            return {
                'symbol': symbol,
                'result': 'skipped',
                'reason': 'News blackout active'
            }

        # Drawdown guard check
        trading = await dd_allowed()
        if not trading.get('allowed', True):
            return {
                'symbol': symbol,
                'result': 'skipped',
                'reason': trading.get(
                    'reason', 'Drawdown halt'
                )
            }

        # Load market data
        fetcher = OHLCVFetcher()
        df      = await fetcher.load_ohlcv(symbol, '1h', 500)
        await fetcher.close()

        if df is None or len(df) < 200:
            return {
                'symbol': symbol,
                'result': 'skipped',
                'reason': 'Insufficient data'
            }

        close = df['close']
        high  = df['high']
        low   = df['low']

        # Chaotic tripwire and edge score
        edge = edge_calc(close, high, low)

        if edge is None:
            return {
                'symbol': symbol,
                'result': 'skipped',
                'reason': 'Edge calculation failed'
            }

        if edge.get('chaotic', False):
            from telegram_bot.alerts import (
                send_chaotic_tripwire_alert
            )
            send_chaotic_tripwire_alert(
                symbol, edge.get('chaotic_ratio', 0)
            )
            return {
                'symbol': symbol,
                'result': 'blocked',
                'reason': 'Chaotic tripwire fired'
            }

        # Sentiment
        sentiment_result = sent_calc(close)
        sentiment        = (
            sentiment_result['sentiment']
            if sentiment_result else 'NEUTRAL'
        )

        # Correlation multiplier
        corr_multiplier = await corr_mult()
        if corr_multiplier == 0.0:
            return {
                'symbol': symbol,
                'result': 'blocked',
                'reason': 'Correlation breaker: all paused'
            }

        # Time filter size multiplier
        time_multiplier   = tf_mult()
        param_overrides   = get_parameter_overrides()

        # Sentinel check
        book = await _exchange.fetch_order_book(symbol, 20)
        sentinel = check_all_filters(symbol, book or {})

        # Skip if position already open
        positions = get_open_positions()
        if symbol in positions:
            return {
                'symbol': symbol,
                'result': 'skipped',
                'reason': 'Position already open'
            }

        # Get strategy and edge score
        strategy    = edge['primary_strategy']
        edge_score  = edge['position_size_factor']
        rvr_regime  = edge.get('rvr_regime', 'NORMAL')

        # Capital for this asset
        allocation    = ASSETS.get(symbol, 0.20)
        balance       = await _exchange.fetch_balance()
        total_capital = float(
            balance.get('USD', 1000.0)
        ) if balance else 1000.0
        asset_capital = total_capital * allocation

        # Run appropriate strategy
        trade_result = None

        if strategy == 'TREND_FOLLOWING':
            silo = await is_active(
                symbol, 'TREND_FOLLOWING'
            )
            if silo.get('active', True):
                trade_result = await tf_run(
                    symbol, asset_capital,
                    edge_score, sentiment, df,
                    _exchange, sentinel, dry_run
                )

        elif strategy == 'MEAN_REVERSION':
            silo = await is_active(
                symbol, 'MEAN_REVERSION'
            )
            if silo.get('active', True):
                trade_result = await mr_run(
                    symbol, asset_capital,
                    edge_score, sentiment, df,
                    _exchange, sentinel, dry_run
                )

        else:
            # Scalper
            silo = await is_active(symbol, 'SCALPER')
            dead_zone = (
                edge.get('hurst_regime', '') == 'DEAD_ZONE'
            )
            if silo.get('active', True):
                trade_result = await sc_run(
                    symbol, asset_capital,
                    sentiment, dead_zone, edge_score,
                    df, _exchange, sentinel, dry_run
                )

        elapsed = round((time.time() - start) * 1000, 1)

        # Send trade alert
        if (
            trade_result and
            trade_result.get('trade_executed')
        ):
            from telegram_bot.alerts import send_trade_opened
            send_trade_opened(trade_result)

        return {
            'symbol':        symbol,
            'result':        'completed',
            'strategy':      strategy,
            'edge_score':    edge_score,
            'sentiment':     sentiment,
            'trade_result':  trade_result,
            'elapsed_ms':    elapsed
        }

    except Exception as e:
        logger.error(
            f'run_asset_cycle failed for {symbol}: {e}'
        )
        return {
            'symbol': symbol,
            'result': 'error',
            'reason': str(e)
        }


async def run_main_loop(dry_run: bool = True) -> None:
    """
    Run one complete cycle across all 5 assets.

    Args:
        dry_run: True for simulation
    """
    try:
        import time
        from config import ASSETS

        start = time.time()
        logger.info(
            f'Main loop starting: '
            f'{len(ASSETS)} assets, dry_run={dry_run}'
        )

        for symbol in ASSETS.keys():
            try:
                result = await run_asset_cycle(
                    symbol, dry_run
                )
                logger.info(
                    f'{symbol}: {result["result"]} '
                    f'{result.get("strategy", "")} '
                    f'{result.get("elapsed_ms", "")}ms'
                )
            except Exception as e:
                logger.error(
                    f'run_main_loop: '
                    f'{symbol} error: {e}'
                )

        elapsed = round(time.time() - start, 2)
        logger.info(
            f'Main loop complete: {elapsed}s'
        )

    except Exception as e:
        logger.error(f'run_main_loop failed: {e}')


# ── System Lifecycle ──────────────────────────────────────────

async def initialise_system() -> bool:
    """
    Run full startup sequence.

    Steps:
        1. Verify environment variables
        2. Initialise databases
        3. Connect to exchange
        4. Send startup Telegram message

    Returns:
        True if all critical steps pass
    """
    logger.info(
        '=' * 50 + '\n'
        'TRADING SYSTEM STARTING\n' +
        '=' * 50
    )
    logger.info(f'Environment: {ENVIRONMENT.upper()}')

    # Step 1
    logger.info('Step 1/4: Verifying environment...')
    if not verify_environment():
        logger.critical(
            'STARTUP FAILED: Missing environment variables'
        )
        return False
    logger.info('Step 1/4: Environment OK')

    # Step 2
    logger.info('Step 2/4: Initialising databases...')
    if not await init_databases():
        logger.critical(
            'STARTUP FAILED: Database initialisation failed'
        )
        return False
    logger.info('Step 2/4: Databases OK')

    # Step 3
    logger.info('Step 3/4: Connecting to exchange...')
    if not await init_exchange():
        logger.critical(
            'STARTUP FAILED: Exchange connection failed'
        )
        return False
    logger.info('Step 3/4: Exchange OK')

    # Step 4 — Non critical
    logger.info('Step 4/4: Starting Telegram...')
    await send_startup_message()
    logger.info('Step 4/4: Telegram OK')

    logger.info('SYSTEM INITIALISATION COMPLETE')
    return True


async def shutdown_system(reason: str = 'Manual stop') -> None:
    """
    Graceful shutdown sequence.

    Args:
        reason: Why the system is shutting down
    """
    global _running, _scheduler

    logger.info(f'SHUTDOWN INITIATED: {reason}')
    _running = False

    # Stop scheduler
    if _scheduler:
        try:
            stop_scheduler(_scheduler)
        except Exception as e:
            logger.error(f'Scheduler stop error: {e}')

    # Close any open positions
    try:
        from execution.order_manager import (
            get_open_positions,
            emergency_close_all
        )
        positions = get_open_positions()
        if positions and ENVIRONMENT == 'live':
            logger.info(
                f'Closing {len(positions)} open positions...'
            )
            if _exchange:
                count = await emergency_close_all(
                    _exchange
                )
                logger.info(
                    f'{count} positions closed on shutdown'
                )
    except Exception as e:
        logger.error(f'Position close on shutdown: {e}')

    # Stop Telegram bot
    try:
        from telegram_bot.bot import stop_bot
        await stop_bot()
    except Exception as e:
        logger.error(f'Bot stop error: {e}')

    # Close exchange
    if _exchange:
        try:
            await _exchange.close()
        except Exception:
            pass

    # Send shutdown Telegram message
    try:
        from telegram_bot.alerts import send_message
        send_message(
            f'TRADING SYSTEM OFFLINE\n'
            f'{"─" * 22}\n'
            f'Reason: {reason}\n'
            f'Time: '
            f'{now_utc().strftime("%Y-%m-%d %H:%M UTC")}'
        )
    except Exception:
        pass

    logger.info('SHUTDOWN COMPLETE')


def handle_signal(signum, frame) -> None:
    """Handle OS shutdown signals."""
    logger.info(f'Signal received: {signum}')
    asyncio.create_task(
        shutdown_system('OS signal received')
    )


async def main() -> None:
    """
    Main entry point — runs the full trading system.

    In BACKTEST mode: runs backtest and exits.
    In LIVE mode: runs continuously until interrupted.
    """
    global _running, _scheduler

    # Register signal handlers
    signal.signal(signal.SIGINT,  handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # ── BACKTEST MODE ─────────────────────────────────────────
    if ENVIRONMENT == 'backtest':
        logger.info('Running in BACKTEST mode')

        # Verify environment
        if not verify_environment():
            logger.error(
                'Environment check failed'
            )
            return

        # Init databases
        if not await init_databases():
            logger.error('Database init failed')
            return

        print('\n' + '=' * 50)
        print('BACKTEST MODE — System Integration Test')
        print('=' * 50)

        # Test all imports
        print('\nTesting all module imports...')
        modules_ok = True

        import_tests = [
            ('config', 'ASSETS'),
            ('core.hurst', 'calculate'),
            ('core.autocorrelation', 'calculate'),
            ('core.pec', 'calculate'),
            ('core.rvr', 'calculate_atr'),
            ('core.edge_score', 'calculate'),
            ('core.sentiment', 'calculate'),
            ('risk.position_sizer', 'calculate'),
            ('risk.drawdown_guard', 'update'),
            ('risk.strategy_silo', 'is_active'),
            ('risk.correlation_breaker', 'check'),
            ('risk.time_filters', 'is_trading_allowed'),
            ('sentinel.spoof_detector', 'detect_spoof'),
            ('sentinel.liquidity_monitor',
             'check_liquidity_gaps'),
            ('sentinel.sentinel', 'check_all_filters'),
            ('strategies.trend_following',
             'run_strategy_iteration'),
            ('strategies.mean_reversion',
             'run_strategy_iteration'),
            ('strategies.scalper', 'run_scalper_iteration'),
            ('backtest.simulator', 'simulate_market_order'),
            ('backtest.metrics', 'calculate_all_metrics'),
            ('backtest.engine', 'run_backtest'),
            ('backtest.stress_test', 'run_all_stress_tests'),
            ('execution.stop_placer',
             'find_liquidity_void'),
            ('execution.order_manager', 'open_position'),
            ('telegram_bot.alerts', 'send_message'),
            ('telegram_bot.commands', 'is_system_paused'),
            ('dead_mans_switch.heartbeat_monitor',
             'write_heartbeat'),
            ('dead_mans_switch.emergency_cancel',
             'run_emergency_cancel'),
            ('scheduler', 'create_scheduler'),
        ]

        for module_name, attr in import_tests:
            try:
                mod = __import__(
                    module_name,
                    fromlist=[attr]
                )
                getattr(mod, attr)
                print(f'  {module_name}: OK')
            except Exception as e:
                print(f'  {module_name}: FAILED — {e}')
                modules_ok = False

        print(
            f'\nAll imports: '
            f'{"OK" if modules_ok else "FAILED"}'
        )

        # Run single asset cycle dry run
        print('\nRunning dry-run asset cycle for BTC/USD...')
        if await init_exchange():
            result = await run_asset_cycle(
                'BTC/USD', dry_run=True
            )
            print(f'  Result: {result["result"]}')
            print(
                f'  Strategy: '
                f'{result.get("strategy", "N/A")}'
            )
            print(
                f'  Edge: '
                f'{result.get("edge_score", "N/A")}'
            )
            print(
                f'  Elapsed: '
                f'{result.get("elapsed_ms", "N/A")}ms'
            )
            if _exchange:
                await _exchange.close()

        # Scheduler test
        print('\nTesting scheduler...')
        from scheduler import create_scheduler, stop_scheduler
        sched = create_scheduler()
        jobs  = sched.get_jobs()
        print(f'  Jobs registered: {len(jobs)}')
        for job in jobs:
            print(f'  {job.name}')
        stop_scheduler(sched)

        print('\n' + '=' * 50)
        print('BACKTEST MODE COMPLETE')
        if modules_ok:
            print(
                'All modules loaded successfully.\n'
                'Change ENVIRONMENT=live in .env '
                'to begin live trading.'
            )
        else:
            print(
                'Some imports failed. '
                'Fix before going live.'
            )
        print('=' * 50 + '\n')
        return

    # ── LIVE MODE ─────────────────────────────────────────────
    logger.info('Running in LIVE mode')

    # Full initialisation
    if not await initialise_system():
        logger.critical('System initialisation failed — exit')
        sys.exit(1)

    # Start Telegram bot in background
    try:
        from telegram_bot.bot import start_bot
        asyncio.create_task(start_bot())
        logger.info('Telegram bot started')
    except Exception as e:
        logger.warning(f'Telegram bot start failed: {e}')

    # Start scheduler
    from scheduler import (
        create_scheduler,
        start_scheduler,
        stop_scheduler
    )
    _scheduler = create_scheduler()
    start_scheduler(_scheduler)

    # Main continuous loop
    logger.info('Entering main trading loop...')
    logger.info(
        'Send /pause to Telegram to pause, '
        'Ctrl+C to stop'
    )

    try:
        while _running:
            await run_main_loop(dry_run=False)
            # Wait before next cycle
            await asyncio.sleep(60)

    except KeyboardInterrupt:
        logger.info('Keyboard interrupt received')
    finally:
        await shutdown_system('Manual shutdown')


# ── Entry Point ───────────────────────────────────────────────
if __name__ == '__main__':
    asyncio.run(main())
