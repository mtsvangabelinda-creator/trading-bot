# Autonomous Multi-Strategy Trading System
# Module 18c — Backtest Engine (Multi-Timeframe Walk-Forward)
# Iterates 4H candles using real Decision Engine (1D bias +
# 4H structure + 1H trigger) and risk management.
# No lookahead bias — decisions made on available data only.

import asyncio
import logging
import os
from typing import Optional

import numpy as np
import pandas as pd

from logging.handlers import RotatingFileHandler

from config import (
    ASSETS,
    ATR_MULTIPLIER,
    WALK_FORWARD_MONTHS,
    WALK_FORWARD_LOOKBACK_MONTHS
)
from core.edge_score import calculate as edge_calculate
from data.ohlcv_fetcher import OHLCVFetcher
from risk.position_sizer import calculate as size_calculate
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

# ── Constants ─────────────────────────────────────────────────
MIN_SIGNAL_LOOKBACK = 200   # 4H candles needed for structure calc
CANDLES_PER_DAY_4H  = 6
LOOKBACK_DAYS       = WALK_FORWARD_LOOKBACK_MONTHS * 30
LOOKBACK_4H_CANDLES = LOOKBACK_DAYS * CANDLES_PER_DAY_4H  # 540

DF_1D_TAIL = 60   # rows of 1D data passed to bias calc
DF_1H_TAIL = 30   # rows of 1H data passed to trigger calc

TP_MULTIPLIER       = 2.0
DRAWDOWN_HALT_PCT   = 0.15


# ════════════════════════════════════════════════════════════
# DATA FETCHING — full span needed for 18-month walk-forward
# ════════════════════════════════════════════════════════════
async def fetch_walk_forward_data(asset: str) -> Optional[dict]:
    """
    Fetch 1D, 4H, and 1H candles covering the full walk-forward
    span (lookback months + test months) for one asset.

    Args:
        asset: Trading pair e.g. BTC/USD

    Returns:
        Dict with 'df_1d', 'df_4h', 'df_1h' DataFrames,
        or None on failure
    """
    try:
        total_months  = WALK_FORWARD_MONTHS + WALK_FORWARD_LOOKBACK_MONTHS
        total_days    = total_months * 30

        candles_1d = total_days
        candles_4h = total_days * 6
        candles_1h = total_days * 24

        fetcher = OHLCVFetcher()
        await fetcher.init_database()

        logger.info(
            f'{asset}: fetching walk-forward data — '
            f'1d={candles_1d}, 4h={candles_4h}, 1h={candles_1h}'
        )

        await fetcher.fetch_historical(asset, '1d', candles_1d)
        await fetcher.fetch_historical(asset, '4h', candles_4h)
        await fetcher.fetch_historical(asset, '1h', candles_1h)

        df_1d = await fetcher.load_ohlcv(asset, '1d', candles_1d)
        df_4h = await fetcher.load_ohlcv(asset, '4h', candles_4h)
        df_1h = await fetcher.load_ohlcv(asset, '1h', candles_1h)

        await fetcher.close()

        for name, df in (('1d', df_1d), ('4h', df_4h), ('1h', df_1h)):
            if df is None or len(df) == 0:
                logger.error(f'{asset}: no {name} data loaded')
                return None
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.sort_values('timestamp', inplace=True)
            df.reset_index(drop=True, inplace=True)

        return {'df_1d': df_1d, 'df_4h': df_4h, 'df_1h': df_1h}

    except Exception as e:
        logger.error(f'fetch_walk_forward_data failed for {asset}: {e}')
        return None


# ════════════════════════════════════════════════════════════
# SLICING HELPERS — no-lookahead data windows
# ════════════════════════════════════════════════════════════
def slice_1d(df_1d: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Return the most recent 1D candles up to (but not
    including) the given timestamp."""
    sliced = df_1d[df_1d['timestamp'] < as_of]
    return sliced.tail(DF_1D_TAIL).reset_index(drop=True)


def slice_1h(df_1h: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Return the most recent 1H candles up to (but not
    including) the given timestamp."""
    sliced = df_1h[df_1h['timestamp'] < as_of]
    return sliced.tail(DF_1H_TAIL).reset_index(drop=True)


# ════════════════════════════════════════════════════════════
# MAIN BACKTEST — multi-timeframe walk-forward
# ════════════════════════════════════════════════════════════
async def run_backtest(
    asset: str,
    df_1d: pd.DataFrame,
    df_4h: pd.DataFrame,
    df_1h: pd.DataFrame,
    initial_capital: float = 10000.0
) -> Optional[dict]:
    """
    Run a multi-timeframe walk-forward backtest for one asset.

    Iterates 4H candles starting after the initial lookback
    period. At each candle, slices 1D/4H/1H data up to (but
    not including) that candle's timestamp, runs the multi-
    timeframe edge score, and simulates trades using real
    position sizing.

    Args:
        asset: Trading pair e.g. BTC/USD
        df_1d: Full 1D OHLCV DataFrame
        df_4h: Full 4H OHLCV DataFrame
        df_1h: Full 1H OHLCV DataFrame
        initial_capital: Starting capital in USD

    Returns:
        Dictionary with trades, equity_curve, monthly_results,
        metrics, or None on failure
    """
    try:
        start_index = max(LOOKBACK_4H_CANDLES, MIN_SIGNAL_LOOKBACK)

        if len(df_4h) < start_index + 30:
            logger.warning(
                f'{asset}: insufficient 4H data — '
                f'{len(df_4h)} candles, need {start_index + 30}'
            )
            return None

        equity        = initial_capital
        equity_curve  = [initial_capital]
        trades        = []
        open_position = None
        peak_equity   = initial_capital

        print(f'\n{"="*60}')
        print(f'WALK-FORWARD TRADE LOG — {asset}')
        print(f'{"="*60}')
        print(
            f'{"#":<4} {"Month":<8} {"Strategy":<16} {"Bias":<8} '
            f'{"Dir":<6} {"Score":<7} {"RVR":<7} {"Regime":<8} '
            f'{"PnL":>8} {"Exit"}'
        )
        print(f'{"-"*100}')

        trade_num = 0

        logger.info(
            f'{asset}: running walk-forward over '
            f'{len(df_4h) - start_index} test candles'
        )

        for i in range(start_index, len(df_4h)):
            candle        = df_4h.iloc[i]
            candle_ts     = candle['timestamp']
            current_price = float(candle['close'])
            candle_high   = float(candle['high'])
            candle_low    = float(candle['low'])
            month_label   = candle_ts.strftime('%Y-%m')

            # ── Manage open position first ────────────────
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

                    exit_reason = 'stop' if stop_hit else 'tp'

                    trade_record = {
                        'asset':        asset,
                        'month':        open_position['month'],
                        'strategy':     open_position['strategy'],
                        'bias':         open_position['bias'],
                        'direction':    open_position['direction'],
                        'entry_price':  open_position['entry_price'],
                        'exit_price':   round(exit_price, 4),
                        'size':         open_position['size'],
                        'pnl':          pnl,
                        'exit_reason':  exit_reason,
                        'entry_time':   open_position['entry_time'],
                        'exit_time':    str(candle_ts),
                        'edge_score':   open_position['edge_score'],
                        'hurst':        open_position['hurst'],
                        'autocorr':     open_position['autocorr'],
                        'pec':          open_position['pec'],
                        'rvr_ratio':    open_position['rvr_ratio'],
                        'rvr_regime':   open_position['rvr_regime']
                    }
                    trades.append(trade_record)

                    trade_num += 1
                    pnl_str = f'${pnl:+.2f}'
                    print(
                        f'{trade_num:<4} '
                        f'{open_position["month"]:<8} '
                        f'{open_position["strategy"]:<16} '
                        f'{open_position["bias"]:<8} '
                        f'{open_position["direction"]:<6} '
                        f'{open_position["edge_score"]:<7.3f} '
                        f'{open_position["rvr_ratio"]:<7.3f} '
                        f'{open_position["rvr_regime"]:<8} '
                        f'{pnl_str:>8} '
                        f'{exit_reason}'
                    )

                    open_position = None

                    if equity > peak_equity:
                        peak_equity = equity

                    if (peak_equity - equity) / peak_equity > DRAWDOWN_HALT_PCT:
                        logger.warning(
                            f'{asset}: Drawdown halt triggered '
                            f'at candle {i} ({candle_ts})'
                        )
                        break

                    continue

            # Skip if position still open (shouldn't happen
            # given continue above, but kept for safety)
            if open_position is not None:
                equity_curve.append(round(equity, 2))
                continue

            # ── Build no-lookahead data slices ─────────────
            window_4h = df_4h.iloc[i - MIN_SIGNAL_LOOKBACK:i]
            window_1d = slice_1d(df_1d, candle_ts)
            window_1h = slice_1h(df_1h, candle_ts)

            if len(window_1d) < 50 or len(window_1h) < 21:
                equity_curve.append(round(equity, 2))
                continue

            # ── Run multi-timeframe edge score ─────────────
            edge = edge_calculate(window_1d, window_4h, window_1h)

            if edge is None or edge.get('chaotic', False):
                equity_curve.append(round(equity, 2))
                continue

            if edge['primary_strategy'] == 'BLOCKED':
                equity_curve.append(round(equity, 2))
                continue

            direction = edge.get('direction')
            if direction is None:
                equity_curve.append(round(equity, 2))
                continue

            if not edge.get('trigger_confirmed', False):
                equity_curve.append(round(equity, 2))
                continue

            # ── Position sizing ─────────────────────────────
            edge_score = edge['position_size_factor']
            rvr_regime = edge.get('rvr_regime', 'NORMAL')
            rvr_m = (
                0.5 if rvr_regime == 'DANGER' else
                0.0 if rvr_regime == 'DEAD' else 1.0
            )

            asset_capital = equity * ASSETS.get(asset, 0.25)
            size_result = size_calculate(
                asset_capital,
                window_4h['close'], window_4h['high'], window_4h['low'],
                edge_score, rvr_m
            )

            if size_result is None:
                equity_curve.append(round(equity, 2))
                continue

            size = size_result['final_size']
            atr  = size_result['atr']

            # ── Entry simulation ────────────────────────────
            entry_sim = simulate_market_order(
                'buy' if direction == 'long' else 'sell',
                size, current_price
            )
            entry_price = entry_sim['filled_price']

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
                'strategy':    edge['primary_strategy'],
                'bias':        edge['bias'],
                'entry_fee':   entry_sim['fee_paid'],
                'entry_time':  str(candle_ts),
                'month':       month_label,
                'edge_score':  edge_score,
                'hurst':       edge.get('hurst', 0.0) or 0.0,
                'autocorr':    edge.get('autocorr', 0.0) or 0.0,
                'pec':         edge.get('pec', 0.0) or 0.0,
                'rvr_ratio':   edge.get('rvr', 0.0) or 0.0,
                'rvr_regime':  rvr_regime
            }

            equity_curve.append(round(equity, 2))

        # ── Close any remaining position at end of data ────
        if open_position is not None:
            final_candle = df_4h.iloc[-1]
            final_price  = float(final_candle['close'])
            exit_sim = simulate_market_order(
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
                'asset':        asset,
                'month':        open_position['month'],
                'strategy':     open_position['strategy'],
                'bias':         open_position['bias'],
                'direction':    open_position['direction'],
                'entry_price':  open_position['entry_price'],
                'exit_price':   round(final_price, 4),
                'size':         open_position['size'],
                'pnl':          pnl,
                'exit_reason':  'end_of_data',
                'entry_time':   open_position['entry_time'],
                'exit_time':    str(final_candle['timestamp']),
                'edge_score':   open_position['edge_score'],
                'hurst':        open_position['hurst'],
                'autocorr':     open_position['autocorr'],
                'pec':          open_position['pec'],
                'rvr_ratio':    open_position['rvr_ratio'],
                'rvr_regime':   open_position['rvr_regime']
            })

        print(f'{"-"*100}')
        print(f'Total trades: {len(trades)}')
        print(f'{"="*60}\n')

        # ── Monthly breakdown ───────────────────────────────
        monthly_results = aggregate_monthly(trades)
        print_monthly_breakdown(asset, monthly_results)

        # ── Overall metrics ─────────────────────────────────
        metrics = calculate_all_metrics(trades, equity_curve)

        logger.info(
            f'{asset} walk-forward complete: '
            f'{len(trades)} trades, '
            f'final equity=${round(equity, 2)}'
        )

        return {
            'asset':           asset,
            'trades':          trades,
            'equity_curve':    equity_curve,
            'monthly_results': monthly_results,
            'metrics':         metrics
        }

    except Exception as e:
        logger.error(f'run_backtest failed for {asset}: {e}')
        return None


# ════════════════════════════════════════════════════════════
# MONTHLY AGGREGATION
# ════════════════════════════════════════════════════════════
def aggregate_monthly(trades: list) -> pd.DataFrame:
    """
    Group trades by month and compute basic per-month stats.

    Args:
        trades: List of trade dicts

    Returns:
        DataFrame indexed by month with trades, wins,
        win_rate, total_pnl
    """
    if not trades:
        return pd.DataFrame(
            columns=['trades', 'wins', 'win_rate', 'total_pnl']
        )

    df = pd.DataFrame(trades)
    grouped = df.groupby('month').agg(
        trades=('pnl', 'count'),
        wins=('pnl', lambda x: int((x > 0).sum())),
        total_pnl=('pnl', 'sum')
    )
    grouped['win_rate'] = round(
        grouped['wins'] / grouped['trades'] * 100, 1
    )
    grouped['total_pnl'] = grouped['total_pnl'].round(2)
    return grouped


def print_monthly_breakdown(asset: str, monthly: pd.DataFrame) -> None:
    """Print a per-month summary table."""
    print(f'MONTHLY BREAKDOWN — {asset}')
    print(f'{"-"*50}')
    if monthly.empty:
        print('No trades recorded.')
        print(f'{"-"*50}\n')
        return

    print(f'{"Month":<10} {"Trades":<8} {"Win Rate":<10} {"PnL"}')
    for month, row in monthly.iterrows():
        print(
            f'{str(month):<10} '
            f'{int(row["trades"]):<8} '
            f'{row["win_rate"]:<10.1f} '
            f'${row["total_pnl"]:+.2f}'
        )
    print(f'{"-"*50}\n')


# ════════════════════════════════════════════════════════════
# RUN ALL ASSETS
# ════════════════════════════════════════════════════════════
async def run_all_assets(
    initial_capital: float = 10000.0
) -> dict:
    """
    Fetch data and run walk-forward backtest for all assets
    in config.ASSETS.

    Args:
        initial_capital: Starting capital per asset test

    Returns:
        Dictionary of asset to backtest result
    """
    results = {}

    for asset in ASSETS.keys():
        logger.info(f'Fetching walk-forward data for {asset}...')
        data = await fetch_walk_forward_data(asset)

        if data is None:
            logger.warning(f'{asset}: no data — skipping')
            results[asset] = None
            continue

        logger.info(f'Running walk-forward backtest for {asset}...')
        result = await run_backtest(
            asset,
            data['df_1d'], data['df_4h'], data['df_1h'],
            initial_capital
        )
        results[asset] = result

        if result:
            logger.info(
                f'{asset}: {len(result["trades"])} trades, '
                f'return={result["metrics"].get("total_return_pct", 0)}%'
            )

    return results


def print_summary(results: dict) -> None:
    """
    Print formatted summary report for all assets.

    Args:
        results: Output from run_all_assets
    """
    print('\n' + '=' * 50)
    print('WALK-FORWARD BACKTEST SUMMARY — ALL ASSETS')
    print('=' * 50)

    all_passed = True

    for asset, result in results.items():
        if result is None:
            print(f'\n{asset}: FAILED — no data or error')
            all_passed = False
            continue

        metrics = result.get('metrics', {})
        report  = format_report(
            metrics, asset, f'{WALK_FORWARD_MONTHS} months (walk-forward)'
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
        print('\n=== MODULE 18c — WALK-FORWARD ENGINE TESTS ===\n')
        np.random.seed(42)

        def build_ohlcv(n, freq, start='2024-01-01', drift=0.05, vol=20):
            close = np.cumsum(np.random.normal(drift, vol, n)) + 45000
            high  = close + np.abs(np.random.normal(0, vol * 0.3, n))
            low   = close - np.abs(np.random.normal(0, vol * 0.3, n))
            open_ = close - np.random.normal(0, vol * 0.2, n)
            times = pd.date_range(start, periods=n, freq=freq)
            return pd.DataFrame({
                'timestamp': times,
                'open': open_, 'high': high, 'low': low,
                'close': close,
                'volume': np.random.uniform(100, 500, n)
            })

        # Build enough data for ~4 months of 4H candles
        n_4h = 700   # > start_index (540) + 30
        n_1d = 130   # covers the 4H span at 6 candles/day
        n_1h = 2800

        df_4h = build_ohlcv(n_4h, '4h')
        df_1d = build_ohlcv(n_1d, '1d')
        df_1h = build_ohlcv(n_1h, '1h')

        print('Test 1: Running walk-forward backtest on synthetic data...')
        result = await run_backtest(
            'BTC/USD', df_1d, df_4h, df_1h,
            initial_capital=10000.0
        )

        if result:
            print(f'  Trades generated: {len(result["trades"])}')
            print(
                f'  Final equity: '
                f'${result["equity_curve"][-1]:,.2f}'
            )
            print('Test 1: PASSED\n')
        else:
            print('Test 1: FAILED\n')

        print('Test 2: Metrics calculation...')
        if result and result['metrics']:
            m = result['metrics']
            print(f'  Total trades: {m.get("total_trades")}')
            print(
                f'  Win rate: '
                f'{round(m.get("win_rate",0)*100,1)}%'
            )
            print(f'  Sharpe: {m.get("sharpe_ratio")}')
            print('Test 2: PASSED\n')
        else:
            print('Test 2: FAILED\n')

        print(
            '=== MODULE 18c — WALK-FORWARD ENGINE: '
            'TESTS COMPLETE ==='
        )

    asyncio.run(run_tests())
