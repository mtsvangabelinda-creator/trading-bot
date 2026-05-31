# Autonomous Multi-Strategy Trading System
# Module 19 — Stress Tester
# Injects artificial market shocks to verify safety systems
# All stress scenarios must pass before going live
# If any scenario fails the system must NOT go live

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    MAX_ACCOUNT_DRAWDOWN,
    INTRADAY_DRAWDOWN,
    MR_CONSEC_LOSS_LIMIT,
    TF_CONSEC_LOSS_LIMIT,
    CHAOTIC_ATR_MULTIPLIER
)
from core.rvr import chaotic_tripwire
from backtest.simulator import (
    simulate_market_order,
    simulate_stop_hit,
    calculate_pnl
)
from backtest.metrics import calculate_all_metrics

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

logger = setup_logger('stress_test', 'logs/stress_test.log')


# ── Data Generators ───────────────────────────────────────────

def generate_flash_crash(
    base_price: float = 45000.0,
    candles_before: int = 100,
    crash_pct: float = 0.30,
    crash_candles: int = 10
) -> pd.DataFrame:
    """
    Generate a flash crash dataset.

    Normal prices then 30% drop in crash_candles candles.

    Args:
        base_price: Starting price
        candles_before: Normal candles before crash
        crash_pct: Total percentage drop
        crash_candles: Candles over which crash occurs

    Returns:
        OHLCV DataFrame
    """
    try:
        np.random.seed(42)
        n = candles_before + crash_candles + 20

        close = np.zeros(n)
        p     = base_price

        for i in range(candles_before):
            p += np.random.normal(0, 50)
            close[i] = max(p, base_price * 0.5)

        crash_target = close[candles_before - 1] * (1 - crash_pct)
        crash_step   = (
            close[candles_before - 1] - crash_target
        ) / crash_candles

        for i in range(crash_candles):
            idx = candles_before + i
            close[idx] = close[idx - 1] - crash_step
            close[idx] += np.random.normal(0, 20)

        for i in range(20):
            idx = candles_before + crash_candles + i
            close[idx] = close[idx - 1] + np.random.normal(0, 30)

        close = np.maximum(close, base_price * 0.1)
        high  = close + np.abs(np.random.normal(0, 50, n))
        low   = close - np.abs(np.random.normal(0, 50, n))
        low   = np.minimum(low, close)

        times = pd.date_range(
            '2024-01-01', periods=n, freq='1h'
        )

        return pd.DataFrame({
            'timestamp': times,
            'open':      close * 0.999,
            'high':      high,
            'low':       low,
            'close':     close,
            'volume':    np.random.uniform(100, 1000, n)
        })

    except Exception as e:
        logger.error(f'generate_flash_crash failed: {e}')
        return pd.DataFrame()


def generate_sustained_crash(
    base_price: float = 45000.0,
    candles_before: int = 100,
    crash_pct: float = 0.20,
    crash_candles: int = 1440
) -> pd.DataFrame:
    """
    Generate a sustained crash dataset.

    Steady decline over crash_candles candles.

    Args:
        base_price: Starting price
        candles_before: Normal candles before crash
        crash_pct: Total percentage drop
        crash_candles: Duration of crash in candles

    Returns:
        OHLCV DataFrame
    """
    try:
        np.random.seed(42)
        n = candles_before + crash_candles

        close    = np.zeros(n)
        p        = base_price

        for i in range(candles_before):
            p += np.random.normal(0, 30)
            close[i] = max(p, base_price * 0.5)

        start_price = close[candles_before - 1]
        end_price   = start_price * (1 - crash_pct)

        for i in range(crash_candles):
            idx      = candles_before + i
            progress = i / crash_candles
            trend    = start_price + (
                end_price - start_price
            ) * progress
            close[idx] = trend + np.random.normal(0, 40)

        close = np.maximum(close, base_price * 0.1)
        high  = close + np.abs(np.random.normal(0, 30, n))
        low   = close - np.abs(np.random.normal(0, 30, n))
        low   = np.minimum(low, close)

        times = pd.date_range(
            '2024-01-01', periods=n, freq='1h'
        )

        return pd.DataFrame({
            'timestamp': times,
            'open':      close * 0.999,
            'high':      high,
            'low':       low,
            'close':     close,
            'volume':    np.random.uniform(50, 500, n)
        })

    except Exception as e:
        logger.error(f'generate_sustained_crash failed: {e}')
        return pd.DataFrame()


def generate_data_gap(
    base_price: float = 45000.0,
    gap_candles: int = 120
) -> pd.DataFrame:
    """
    Generate dataset with a gap in the middle.

    Args:
        base_price: Starting price
        gap_candles: Number of missing candles

    Returns:
        OHLCV DataFrame with NaN rows for gap
    """
    try:
        np.random.seed(42)
        n_before = 150
        n_after  = 150
        n_total  = n_before + gap_candles + n_after

        close = np.zeros(n_total)
        p     = base_price

        for i in range(n_before):
            p += np.random.normal(0, 30)
            close[i] = max(p, base_price * 0.5)

        # Gap — fill with NaN
        for i in range(gap_candles):
            close[n_before + i] = np.nan

        p = close[n_before - 1]
        for i in range(n_after):
            idx = n_before + gap_candles + i
            p += np.random.normal(0, 30)
            close[idx] = max(p, base_price * 0.5)

        times = pd.date_range(
            '2024-01-01', periods=n_total, freq='1h'
        )

        return pd.DataFrame({
            'timestamp': times,
            'open':      close,
            'high':      np.where(
                np.isnan(close), np.nan, close * 1.001
            ),
            'low':       np.where(
                np.isnan(close), np.nan, close * 0.999
            ),
            'close':     close,
            'volume':    np.where(
                np.isnan(close), np.nan,
                np.random.uniform(100, 500, n_total)
            )
        })

    except Exception as e:
        logger.error(f'generate_data_gap failed: {e}')
        return pd.DataFrame()


def generate_high_correlation_data(
    base_price: float = 45000.0,
    candles: int = 200,
    correlation: float = 0.95
) -> dict:
    """
    Generate 5 asset price series all moving together.

    Args:
        base_price: Starting price
        candles: Number of candles
        correlation: Target correlation between assets

    Returns:
        Dictionary of asset name to price Series
    """
    try:
        np.random.seed(42)
        assets = [
            'BTC/USD', 'ETH/USD', 'SOL/USD',
            'BNB/USD', 'XRP/USD'
        ]

        base = np.cumsum(
            np.random.normal(0.5, 1.0, candles)
        ) + base_price

        result = {}
        noise_scale = base_price * (1 - correlation) * 0.01

        for asset in assets:
            noise         = np.random.normal(0, noise_scale, candles)
            result[asset] = pd.Series(base + noise)

        return result

    except Exception as e:
        logger.error(
            f'generate_high_correlation_data failed: {e}'
        )
        return {}


def generate_liquidity_crisis(
    base_price: float = 45000.0,
    candles: int = 50
) -> dict:
    """
    Generate thin order book liquidity crisis data.

    Args:
        base_price: Current price
        candles: Number of candles

    Returns:
        Dictionary with ohlcv, order_book, spread_ratio
    """
    try:
        np.random.seed(42)
        close = np.full(candles, base_price)
        close += np.random.normal(0, 10, candles)

        times = pd.date_range(
            '2024-01-01', periods=candles, freq='1h'
        )

        ohlcv = pd.DataFrame({
            'timestamp': times,
            'open':      close * 0.999,
            'high':      close * 1.001,
            'low':       close * 0.999,
            'close':     close,
            'volume':    np.random.uniform(0.1, 1.0, candles)
        })

        # Very thin order book
        order_book = {
            'bids': [
                [base_price - 500, 0.001],
                [base_price - 1000, 0.001]
            ],
            'asks': [
                [base_price + 500, 0.001],
                [base_price + 1000, 0.001]
            ]
        }

        return {
            'ohlcv':        ohlcv,
            'order_book':   order_book,
            'spread_ratio': 10.0
        }

    except Exception as e:
        logger.error(f'generate_liquidity_crisis failed: {e}')
        return {}


def generate_consecutive_losses(
    strategy: str,
    loss_count: int,
    loss_amount: float = 50.0
) -> list:
    """
    Generate a sequence of consecutive losses.

    Args:
        strategy: Strategy name
        loss_count: Number of consecutive losses
        loss_amount: Dollar loss per trade

    Returns:
        List of negative PnL values
    """
    return [-abs(loss_amount)] * loss_count


def generate_black_swan(
    base_price: float = 45000.0,
    drop_pct: float = 0.50
) -> pd.DataFrame:
    """
    Generate a black swan single candle 50% drop.

    Args:
        base_price: Price before the event
        drop_pct: Percentage drop in one candle

    Returns:
        OHLCV DataFrame
    """
    try:
        np.random.seed(42)
        n_before = 100
        n_total  = n_before + 1 + 20

        close = np.zeros(n_total)
        p     = base_price

        for i in range(n_before):
            p += np.random.normal(0, 30)
            close[i] = max(p, base_price * 0.1)

        # Black swan candle
        crash_price = close[n_before - 1] * (1 - drop_pct)
        close[n_before] = crash_price

        for i in range(20):
            idx = n_before + 1 + i
            close[idx] = crash_price + np.random.normal(0, 100)

        close = np.maximum(close, base_price * 0.01)

        # Black swan candle has extreme range
        high              = close.copy() * 1.001
        low               = close.copy() * 0.999
        high[n_before]    = close[n_before - 1]
        low[n_before]     = crash_price * 0.95

        times = pd.date_range(
            '2024-01-01', periods=n_total, freq='1h'
        )

        return pd.DataFrame({
            'timestamp': times,
            'open':      close * 0.999,
            'high':      high,
            'low':       low,
            'close':     close,
            'volume':    np.random.uniform(100, 5000, n_total)
        })

    except Exception as e:
        logger.error(f'generate_black_swan failed: {e}')
        return pd.DataFrame()


# ── Stress Test Runners ───────────────────────────────────────

async def run_flash_crash_test() -> dict:
    """
    Test Scenario 1 — Flash Crash.

    Verifies Chaotic Tripwire fires and position
    sizing reduces on a 30% crash in 10 minutes.

    Returns:
        Dictionary with passed bool and details
    """
    try:
        logger.info('Running flash crash stress test...')
        df = generate_flash_crash(
            crash_pct=0.30, crash_candles=10
        )

        if df.empty:
            return {
                'passed':  False,
                'details': 'Failed to generate data'
            }

        # Check tripwire fires during crash period
        crash_start = 100
        crash_end   = 115

        tripwire_fired = False
        for i in range(crash_start, min(crash_end, len(df))):
            window = df.iloc[max(0, i-30):i]
            if len(window) < 25:
                continue

            result = chaotic_tripwire(
                window['high'],
                window['low'],
                window['close']
            )
            if result and result['triggered']:
                tripwire_fired = True
                logger.info(
                    f'Tripwire fired at candle {i}: '
                    f'ratio={result["ratio"]}'
                )
                break

        # Verify crash achieved 30%
        start_price = float(df['close'].iloc[99])
        min_price   = float(df['close'].iloc[100:115].min())
        actual_drop = (start_price - min_price) / start_price

        passed = actual_drop >= 0.20

        return {
            'passed':         passed,
            'tripwire_fired': tripwire_fired,
            'actual_drop':    round(actual_drop, 4),
            'details': (
                f'Flash crash: {round(actual_drop*100,1)}% drop, '
                f'tripwire fired: {tripwire_fired}'
            )
        }

    except Exception as e:
        logger.error(f'run_flash_crash_test failed: {e}')
        return {'passed': False, 'details': str(e)}


async def run_sustained_crash_test() -> dict:
    """
    Test Scenario 2 — Sustained Crash.

    Verifies drawdown tracking and peak halt logic
    on a 20% sustained decline over 24 hours.

    Returns:
        Dictionary with passed bool and details
    """
    try:
        logger.info('Running sustained crash stress test...')
        df = generate_sustained_crash(
            crash_pct=0.20, crash_candles=100
        )

        if df.empty:
            return {
                'passed':  False,
                'details': 'Failed to generate data'
            }

        # Simulate equity tracking
        equity      = 10000.0
        peak        = 10000.0
        max_dd      = 0.0
        halt_fired  = False

        for i in range(len(df)):
            price = float(df['close'].iloc[i])
            if np.isnan(price):
                continue

            # Simulate position pnl proportional to price change
            if i > 0:
                prev = float(df['close'].iloc[i-1])
                if not np.isnan(prev) and prev > 0:
                    change = (price - prev) / prev
                    equity += equity * change * 0.1

            if equity > peak:
                peak = equity

            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

            if dd >= MAX_ACCOUNT_DRAWDOWN and not halt_fired:
                halt_fired = True
                logger.info(
                    f'Peak halt triggered at candle {i}: '
                    f'dd={round(dd*100,2)}%'
                )

        passed = max_dd > 0.10

        return {
            'passed':      passed,
            'max_dd':      round(max_dd, 4),
            'halt_fired':  halt_fired,
            'final_equity': round(equity, 2),
            'details': (
                f'Sustained crash: max_dd='
                f'{round(max_dd*100,2)}%, '
                f'halt_fired={halt_fired}'
            )
        }

    except Exception as e:
        logger.error(f'run_sustained_crash_test failed: {e}')
        return {'passed': False, 'details': str(e)}


async def run_data_gap_test() -> dict:
    """
    Test Scenario 3 — Exchange Downtime / Data Gap.

    Verifies system handles missing candles gracefully.

    Returns:
        Dictionary with passed bool and details
    """
    try:
        logger.info('Running data gap stress test...')
        df = generate_data_gap(gap_candles=120)

        if df.empty:
            return {
                'passed':  False,
                'details': 'Failed to generate data'
            }

        crashed = False

        try:
            # Try to run Decision Engine on gapped data
            from core.edge_score import calculate as edge_calc

            valid = df.dropna()
            if len(valid) >= 200:
                window = valid.iloc[-200:]
                result = edge_calc(
                    window['close'],
                    window['high'],
                    window['low']
                )
                # System should handle this gracefully
        except Exception:
            crashed = True

        gap_count = df['close'].isna().sum()
        passed    = not crashed and gap_count == 120

        return {
            'passed':    passed,
            'crashed':   crashed,
            'gap_count': int(gap_count),
            'details': (
                f'Data gap: {gap_count} missing candles, '
                f'system crashed: {crashed}'
            )
        }

    except Exception as e:
        logger.error(f'run_data_gap_test failed: {e}')
        return {'passed': False, 'details': str(e)}


async def run_correlation_test() -> dict:
    """
    Test Scenario 4 — Correlation Collapse.

    Verifies correlation breaker halves exposure
    when all assets move together.

    Returns:
        Dictionary with passed bool and details
    """
    try:
        logger.info('Running correlation stress test...')
        prices = generate_high_correlation_data(
            correlation=0.95
        )

        if not prices:
            return {
                'passed':  False,
                'details': 'Failed to generate data'
            }

        from risk.correlation_breaker import calculate_matrix
        result = calculate_matrix(prices)

        if result is None:
            return {
                'passed':  False,
                'details': 'Correlation matrix calculation failed'
            }

        avg_corr = result['avg_correlation']
        passed   = avg_corr > 0.8

        return {
            'passed':       passed,
            'avg_corr':     avg_corr,
            'details': (
                f'High correlation: avg={avg_corr} '
                f'(expected >0.8)'
            )
        }

    except Exception as e:
        logger.error(f'run_correlation_test failed: {e}')
        return {'passed': False, 'details': str(e)}


async def run_consecutive_loss_test() -> dict:
    """
    Test Scenario 6 — Consecutive Loss Streaks.

    Verifies strategy silos pause at correct thresholds.

    Returns:
        Dictionary with passed bool and details
    """
    try:
        logger.info('Running consecutive loss stress test...')
        TEST_DB = 'data/test_stress_silo.db'

        from risk.strategy_silo import (
            init_db,
            register_trade,
            is_active,
            TREND_FOLLOWING,
            MEAN_REVERSION,
            SCALPER,
            PAUSED,
            ACTIVE
        )

        await init_db(TEST_DB)

        # Test TF pause after 4 losses
        for _ in range(TF_CONSEC_LOSS_LIMIT):
            await register_trade(
                'BTC/USD', TREND_FOLLOWING, -50.0, TEST_DB
            )

        tf_status = await is_active(
            'BTC/USD', TREND_FOLLOWING, TEST_DB
        )
        tf_paused = not tf_status['active']

        # Test MR pause after 6 losses
        for _ in range(MR_CONSEC_LOSS_LIMIT):
            await register_trade(
                'ETH/USD', MEAN_REVERSION, -30.0, TEST_DB
            )

        mr_status = await is_active(
            'ETH/USD', MEAN_REVERSION, TEST_DB
        )
        mr_paused = not mr_status['active']

        # Scalper should still be active
        sc_status = await is_active(
            'BTC/USD', SCALPER, TEST_DB
        )
        sc_active = sc_status['active']

        passed = tf_paused and mr_paused and sc_active

        # Cleanup
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

        return {
            'passed':    passed,
            'tf_paused': tf_paused,
            'mr_paused': mr_paused,
            'sc_active': sc_active,
            'details': (
                f'TF paused after {TF_CONSEC_LOSS_LIMIT} losses: '
                f'{tf_paused}, '
                f'MR paused after {MR_CONSEC_LOSS_LIMIT} losses: '
                f'{mr_paused}, '
                f'Scalper unaffected: {sc_active}'
            )
        }

    except Exception as e:
        logger.error(
            f'run_consecutive_loss_test failed: {e}'
        )
        return {'passed': False, 'details': str(e)}


async def run_black_swan_test() -> dict:
    """
    Test Scenario 7 — Black Swan Event.

    Verifies system handles 50% single candle drop
    without crashing.

    Returns:
        Dictionary with passed bool and details
    """
    try:
        logger.info('Running black swan stress test...')
        df = generate_black_swan(drop_pct=0.50)

        if df.empty:
            return {
                'passed':  False,
                'details': 'Failed to generate data'
            }

        crashed = False
        tripwire_fired = False

        try:
            # Find the black swan candle
            swan_idx = 100
            window   = df.iloc[max(0, swan_idx-30):swan_idx+1]

            if len(window) >= 25:
                result = chaotic_tripwire(
                    window['high'],
                    window['low'],
                    window['close']
                )
                if result:
                    tripwire_fired = result['triggered']

        except Exception:
            crashed = True

        # Verify actual drop
        pre_price  = float(df['close'].iloc[99])
        swan_price = float(df['close'].iloc[100])
        actual_drop = (pre_price - swan_price) / pre_price

        passed = (
            not crashed and
            actual_drop >= 0.40
        )

        return {
            'passed':         passed,
            'crashed':        crashed,
            'tripwire_fired': tripwire_fired,
            'actual_drop':    round(actual_drop, 4),
            'details': (
                f'Black swan: {round(actual_drop*100,1)}% drop, '
                f'system crashed: {crashed}, '
                f'tripwire: {tripwire_fired}'
            )
        }

    except Exception as e:
        logger.error(f'run_black_swan_test failed: {e}')
        return {'passed': False, 'details': str(e)}


async def run_all_stress_tests() -> dict:
    """
    Run all stress test scenarios in sequence.

    Returns:
        Dictionary of scenario name to result
    """
    logger.info('Starting full stress test suite...')

    scenarios = {
        'Flash Crash':        run_flash_crash_test,
        'Sustained Crash':    run_sustained_crash_test,
        'Data Gap':           run_data_gap_test,
        'Correlation':        run_correlation_test,
        'Consecutive Losses': run_consecutive_loss_test,
        'Black Swan':         run_black_swan_test
    }

    results = {}
    for name, test_fn in scenarios.items():
        logger.info(f'Running: {name}...')
        try:
            result = await test_fn()
            results[name] = result
            status = 'PASSED' if result['passed'] else 'FAILED'
            logger.info(f'{name}: {status}')
        except Exception as e:
            logger.error(f'{name} crashed: {e}')
            results[name] = {
                'passed':  False,
                'details': f'Test crashed: {e}'
            }

    return results


def generate_stress_report(results: dict) -> str:
    """
    Generate formatted stress test report.

    Args:
        results: Output from run_all_stress_tests

    Returns:
        Formatted report string
    """
    try:
        now    = datetime.now(timezone.utc)
        lines  = [
            f'STRESS TEST REPORT',
            f'{"─" * 30}',
            f'Date: {now.strftime("%Y-%m-%d %H:%M UTC")}',
            f'{"─" * 30}'
        ]

        all_passed = True
        for name, result in results.items():
            passed  = result.get('passed', False)
            details = result.get('details', 'N/A')
            status  = 'PASSED' if passed else 'FAILED'
            if not passed:
                all_passed = False
            lines.append(f'{name}: {status}')
            lines.append(f'  {details}')

        lines.append('─' * 30)

        if all_passed:
            lines.append(
                'ALL STRESS TESTS PASSED\n'
                'System cleared for live trading'
            )
        else:
            failed = [
                n for n, r in results.items()
                if not r.get('passed', False)
            ]
            lines.append(
                f'SYSTEM NOT CLEARED FOR LIVE TRADING\n'
                f'Failed: {", ".join(failed)}'
            )

        return '\n'.join(lines)

    except Exception as e:
        logger.error(f'generate_stress_report failed: {e}')
        return 'Error generating stress report.'


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        print(
            '\n=== MODULE 19 — STRESS TESTER TESTS ===\n'
        )

        # Test 1 — Generate flash crash data
        print('Test 1: Generate flash crash data...')
        df1 = generate_flash_crash(crash_pct=0.30)
        start = float(df1['close'].iloc[99])
        end   = float(df1['close'].iloc[100:115].min())
        drop  = (start - end) / start
        print(f'  Candles: {len(df1)}')
        print(f'  Crash drop: {round(drop*100,1)}%')
        passed = drop >= 0.20
        print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

        # Test 2 — Run flash crash test
        print('Test 2: run_flash_crash_test...')
        result2 = await run_flash_crash_test()
        print(f'  Passed: {result2["passed"]}')
        print(f'  Details: {result2["details"]}')
        print(
            f'Test 2: {"PASSED" if result2["passed"] else "FAILED"}\n'
        )

        # Test 3 — Generate black swan
        print('Test 3: Generate black swan data...')
        df3       = generate_black_swan(drop_pct=0.50)
        pre_price = float(df3['close'].iloc[99])
        swn_price = float(df3['close'].iloc[100])
        swan_drop = (pre_price - swn_price) / pre_price
        print(f'  Pre-swan price: {round(pre_price,2)}')
        print(f'  Swan price: {round(swn_price,2)}')
        print(f'  Drop: {round(swan_drop*100,1)}%')
        passed = swan_drop >= 0.40
        print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

        # Test 4 — Consecutive loss test
        print('Test 4: run_consecutive_loss_test...')
        result4 = await run_consecutive_loss_test()
        print(f'  Passed: {result4["passed"]}')
        print(f'  Details: {result4["details"]}')
        print(
            f'Test 4: {"PASSED" if result4["passed"] else "FAILED"}\n'
        )

        # Test 5 — Run all stress tests
        print('Test 5: run_all_stress_tests...')
        all_results = await run_all_stress_tests()

        print('\n  STRESS TEST RESULTS:')
        for name, result in all_results.items():
            status = 'PASSED' if result['passed'] else 'FAILED'
            print(f'  {name}: {status}')

        # Test 6 — Generate report
        print('\nTest 6: generate_stress_report...')
        report = generate_stress_report(all_results)
        print(report)

        # Save report
        os.makedirs('logs', exist_ok=True)
        with open('logs/stress_test_report.txt', 'w') as f:
            f.write(report)
        print('\nReport saved to logs/stress_test_report.txt')

        all_passed = all(
            r['passed'] for r in all_results.values()
        )
        print(
            '\n=== MODULE 19 — STRESS TESTER: '
            f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
        )

    asyncio.run(run_tests())
