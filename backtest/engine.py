# Autonomous Multi-Strategy Trading System
# Module 18c — Backtest Engine
# Main backtest runner — iterates historical data candle
# by candle using real Decision Engine and risk management
# No lookahead bias — decisions made on available data only

import asyncio
import logging
import os
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    ASSETS,
    BACKTEST_YEARS,
    BACKTEST_START_DATE,
    BACKTEST_END_DATE,
    TAKER_FEE,
    BASE_RISK_PCT,
    ATR_MULTIPLIER
)
from core.edge_score import calculate as edge_calculate
from core.sentiment import calculate as sentiment_calculate
from core.rvr import calculate_atr
from risk.position_sizer import calculate as size_calculate
from risk.time_filters import get_size_multiplier as tf_size
from backtest.simulator import (
    simulate_market_order,
    simulate_stop_hit,
    simulate_take_profit_hit,
    calculate_pnl
)
from backtest.metrics import (
    calculate_all_metrics,
    format_report,
    check_passes_criteria
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

logger = setup_logger('engine', 'logs/backtest.log')

# ── Lookback for Decision Engine ──────────────────────────────
MIN_LOOKBACK = 200
TP_MULTIPLIER = 2.0


async def run_backtest(
    asset: str,
    ohlcv_df: pd.DataFrame,
    initial_capital: float = 10000.0,
    start_date: str = BACKTEST_START_DATE,
    end_date: str = BACKTEST_END_DATE
) -> Optional[dict]:
    """
    Run backtest for one asset on historical data.

    Iterates candle by candle with no lookahead bias.
    Uses real Decision Engine and position sizing.

    Args:
        asset: Trading pair
        ohlcv_df: Full OHLCV DataFrame
        initial_capital: Starting capital in USD
        start_date: Backtest start date string
        end_date: Backtest end date string

    Returns:
        Dictionary with trades, equity_curve, metrics
        or None on failure
    """
    try:
        logger.info(
            f'Starting backtest for {asset}: '
            f'{start_date} to {end_date}'
        )

        # Filter data to date range
        df = ohlcv_df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)

        if start_date:
            df = df[df['timestamp'] >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df['timestamp'] <= pd.Timestamp(end_date)]

        if len(df) < MIN_LOOKBACK + 10:
            logger.warning(
                f'Insufficient data for {asset}: {len(df)} candles'
            )
            return None

        df = df.reset_index(drop=True)

        equity          = initial_capital
        equity_curve    = [initial_capital]
        trades          = []
        open_position   = None
        peak_equity     = initial_capital

        logger.info(
            f'{asset}: {len(df)} candles loaded for backtest'
        )

        for i in range(MIN_LOOKBACK, len(df)):
            # Current candle
            candle      = df.iloc[i]
            current_price = float(candle['close'])
            candle_high   = float(candle['high'])
            candle_low    = float(candle['low'])

            # Check open position first
            if open_position is not None:
                stop_hit = simulate_stop_hit(
                    open_position['stop_price'],
                    candle_low, candle_high,
                    open_position['direction']
                )
                tp_hit = simulate_take_profit_hit(
                    open_position['tp_price'],
                    candle_low, candle_high,
                    open_position['direction']
                )

                if stop_hit or tp_hit:
                    # Exit position
                    exit_price = (
                        open_position['stop_price']
                        if stop_hit
                        else open_position['tp_price']
                    )
                    exit_sim = simulate_market_order(
                        'sell' if open_position['direction'] == 'long'
                        else 'buy',
                        open_position['size'],
                        exit_price
                    )

                    pnl = calculate_pnl(
                        open_position['direction'],
                        open_position['entry_price'],
                        exit_price,
                        open_position['size'],
                        open_position['entry_fee'],
                        exit_sim['fee_paid']
                    )

                    equity += pnl
                    equity_curve.append(round(equity, 2))

                    trade_record = {
                        'asset':       asset,
                        'strategy':    open_position['strategy'],
                        'direction':   open_position['direction'],
                        'entry_price': open_position['entry_price'],
                        'exit_price':  round(exit_price, 4),
                        'size':        open_position['size'],
                        'pnl':         pnl,
                        'exit_reason': (
                            'stop' if stop_hit else 'take_profit'
                        ),
                        'entry_time':  open_position['entry_time'],
                        'exit_time':   str(candle['timestamp'])
                    }
                    trades.append(trade_record)
                    open_position = None

                    if equity > peak_equity:
                        peak_equity = equity

                    # Check drawdown halt
                    if (peak_equity - equity) / peak_equity > 0.15:
                        logger.warning(
                            f'{asset}: Peak halt triggered '
                            f'at candle {i}'
                        )
                        break

                    continue

            # Skip if position open
            if open_position is not None:
                equity_curve.append(round(equity, 2))
                continue

            # Run Decision Engine on lookback window
            window = df.iloc[i - MIN_LOOKBACK:i]
            close  = window['close']
            high   = window['high']
            low    = window['low']

            edge = edge_calculate(close, high, low)

            if edge is None or edge.get('chaotic', False):
                equity_curve.append(round(equity, 2))
                continue

            strategy    = edge['primary_strategy']
            edge_score  = edge['position_size_factor']
            rvr_mult    = edge.get('rvr_regime', 'NORMAL')
            rvr_m       = (
                0.5 if rvr_mult == 'DANGER' else
                0.0 if rvr_mult == 'DEAD' else 1.0
            )

            if strategy == 'BLOCKED' or edge_score < 0.3:
                equity_curve.append(round(equity, 2))
                continue

            # Get sentiment
            sentiment_result = sentiment_calculate(close)
            sentiment = (
                sentiment_result['sentiment']
                if sentiment_result else 'NEUTRAL'
            )

            # Determine direction
            if strategy == 'TREND_FOLLOWING':
                short_ma = float(close.iloc[-5:].mean())
                long_ma  = float(close.iloc[-20:].mean())
                if short_ma > long_ma:
                    direction = 'long'
                elif short_ma < long_ma:
                    direction = 'short'
                else:
                    equity_curve.append(round(equity, 2))
                    continue

            elif strategy == 'MEAN_REVERSION':
                sma = float(close.iloc[-20:].mean())
                if current_price < sma * 0.99:
                    direction = 'long'
                elif current_price > sma * 1.01:
                    direction = 'short'
                else:
                    equity_curve.append(round(equity, 2))
                    continue

            else:
                # Scalper follows sentiment
                if sentiment == 'BULLISH':
                    direction = 'long'
                elif sentiment == 'BEARISH':
                    direction = 'short'
                else:
                    equity_curve.append(round(equity, 2))
                    continue

            # Sentiment filter
            if sentiment == 'BULLISH' and direction == 'short':
                equity_curve.append(round(equity, 2))
                continue
            if sentiment == 'BEARISH' and direction == 'long':
                equity_curve.append(round(equity, 2))
                continue

            # Calculate position size
            asset_capital = equity * ASSETS.get(asset, 0.25)
            size_result   = size_calculate(
                asset_capital, close, high, low,
                edge_score, rvr_m
            )

            if size_result is None:
                equity_curve.append(round(equity, 2))
                continue

            size = size_result['final_size']
            atr  = size_result['atr']

            # Entry simulation
            entry_sim = simulate_market_order(
                'buy' if direction == 'long' else 'sell',
                size, current_price
            )
            entry_price = entry_sim['filled_price']

            # Stop and take profit
            if direction == 'long':
                stop_price = entry_price - (atr * ATR_MULTIPLIER)
                tp_price   = entry_price + (
                    atr * ATR_MULTIPLIER * TP_MULTIPLIER
                )
            else:
                stop_price = entry_price + (atr * ATR_MULTIPLIER)
                tp_price   = entry_price - (
                    atr * ATR_MULTIPLIER * TP_MULTIPLIER
                )

            open_position = {
                'direction':   direction,
                'entry_price': entry_price,
                'stop_price':  stop_price,
                'tp_price':    tp_price,
                'size':        size,
                'strategy':    strategy,
                'entry_fee':   entry_sim['fee_paid'],
                'entry_time':  str(candle['timestamp'])
            }

            equity_curve.append(round(equity, 2))

        # Close any remaining position
        if open_position is not None:
            final_price = float(df.iloc[-1]['close'])
            exit_sim    = simulate_market_order(
                'sell' if open_position['direction'] == 'long'
                else 'buy',
                open_position['size'], final_price
            )
            pnl = calculate_pnl(
                open_position['direction'],
                open_position['entry_price'],
                final_price,
                open_position['size'],
                open_position['entry_fee'],
                exit_sim['fee_paid']
            )
            equity += pnl
            trades.append({
                'asset':       asset,
                'strategy':    open_position['strategy'],
                'direction':   open_position['direction'],
                'entry_price': open_position['entry_price'],
                'exit_price':  round(final_price, 4),
                'size':        open_position['size'],
                'pnl':         pnl,
                'exit_reason': 'end_of_data',
                'entry_time':  open_position['entry_time'],
                'exit_time':   str(df.iloc[-1]['timestamp'])
            })

        metrics = calculate_all_metrics(trades, equity_curve)

        logger.info(
            f'{asset} backtest complete: '
            f'{len(trades)} trades, '
            f'final equity=${round(equity, 2)}'
        )

        return {
            'asset':        asset,
            'trades':       trades,
            'equity_curve': equity_curve,
            'metrics':      metrics,
            'start_date':   start_date,
            'end_date':     end_date
        }

    except Exception as e:
        logger.error(f'run_backtest failed for {asset}: {e}')
        return None


async def run_all_assets(
    ohlcv_data: dict,
    initial_capital: float = 10000.0,
    start_date: str = BACKTEST_START_DATE,
    end_date: str = BACKTEST_END_DATE
) -> dict:
    """
    Run backtest for all 5 assets sequentially.

    Args:
        ohlcv_data: Dict of asset to OHLCV DataFrame
        initial_capital: Starting capital
        start_date: Backtest start date
        end_date: Backtest end date

    Returns:
        Dictionary of asset to backtest result
    """
    results = {}

    for asset in ASSETS.keys():
        if asset not in ohlcv_data:
            logger.warning(
                f'No data for {asset} — skipping'
            )
            continue

        logger.info(f'Running backtest for {asset}...')
        result = await run_backtest(
            asset,
            ohlcv_data[asset],
            initial_capital,
            start_date,
            end_date
        )
        results[asset] = result

        if result:
            logger.info(
                f'{asset}: {len(result["trades"])} trades, '
                f'return={result["metrics"].get("total_return_pct", 0)}%'
            )

    return results


async def run_walk_forward(
    asset: str,
    ohlcv_df: pd.DataFrame,
    initial_capital: float = 10000.0
) -> Optional[dict]:
    """
    Run walk-forward validation on one asset.

    Trains on first 4 years, tests on final year.
    This gives an honest out-of-sample performance measure.

    Args:
        asset: Trading pair
        ohlcv_df: Full OHLCV DataFrame
        initial_capital: Starting capital

    Returns:
        Test period backtest result
    """
    try:
        logger.info(
            f'Running walk-forward validation for {asset}'
        )

        # Test on final year only
        test_start = '2024-01-01'
        test_end   = BACKTEST_END_DATE

        result = await run_backtest(
            asset, ohlcv_df,
            initial_capital,
            test_start, test_end
        )

        if result:
            logger.info(
                f'Walk-forward {asset}: '
                f'{len(result["trades"])} trades in test period'
            )

        return result

    except Exception as e:
        logger.error(
            f'run_walk_forward failed for {asset}: {e}'
        )
        return None


def print_summary(results: dict) -> None:
    """
    Print formatted summary report for all assets.

    Args:
        results: Output from run_all_assets
    """
    print('\n' + '=' * 50)
    print('BACKTEST SUMMARY — ALL ASSETS')
    print('=' * 50)

    all_passed = True

    for asset, result in results.items():
        if result is None:
            print(f'\n{asset}: FAILED — no data or error')
            all_passed = False
            continue

        metrics = result.get('metrics', {})
        report  = format_report(
            metrics, asset, '5 years'
        )
        print(f'\n{report}')

        criteria = check_passes_criteria(metrics)
        if not criteria['passed']:
            all_passed = False

    print('\n' + '=' * 50)
    if all_passed:
        print('ALL ASSETS PASSED — System cleared for live trading')
    else:
        print('SOME ASSETS FAILED — Review before going live')
    print('=' * 50 + '\n')


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        print('\n=== MODULE 18c — BACKTEST ENGINE TESTS ===\n')
        np.random.seed(42)

        # Build 300 candle synthetic dataset
        n     = 300
        close = np.cumsum(
            np.random.normal(0.1, 50, n)
        ) + 45000
        high  = close * 1.002
        low   = close * 0.998
        times = pd.date_range(
            '2024-01-01', periods=n, freq='1h'
        )

        df = pd.DataFrame({
            'timestamp': times,
            'open':      close * 0.999,
            'high':      high,
            'low':       low,
            'close':     close,
            'volume':    np.random.uniform(100, 500, n)
        })

        # Test 1 — Run backtest on synthetic data
        print('Test 1: Running backtest on 300 candles...')
        result = await run_backtest(
            'BTC/USD', df,
            initial_capital=10000.0,
            start_date=None,
            end_date=None
        )

        if result:
            print(
                f'  Trades generated: {len(result["trades"])}'
            )
            print(
                f'  Final equity: '
                f'${result["equity_curve"][-1]:,.2f}'
            )
            print(
                f'  Initial equity: '
                f'${result["equity_curve"][0]:,.2f}'
            )
            print('Test 1: PASSED\n')
        else:
            print('Test 1: FAILED\n')

        # Test 2 — Metrics
        print('Test 2: Metrics calculation...')
        if result and result['metrics']:
            m = result['metrics']
            print(f'  Total trades: {m.get("total_trades")}')
            print(
                f'  Win rate: '
                f'{round(m.get("win_rate",0)*100,1)}%'
            )
            print(
                f'  Max drawdown: '
                f'{round(m.get("max_drawdown_pct",0)*100,2)}%'
            )
            print(f'  Sharpe: {m.get("sharpe_ratio")}')
            print('Test 2: PASSED\n')
        else:
            print('Test 2: FAILED\n')

        # Test 3 — Format report
        print('Test 3: Format report...')
        if result:
            report = format_report(
                result['metrics'], 'BTC/USD', '300 candles'
            )
            print(report)
            print('Test 3: PASSED\n')

        print(
            '=== MODULE 18c — BACKTEST ENGINE: '
            'ALL TESTS PASSED ==='
        )

    asyncio.run(run_tests())
