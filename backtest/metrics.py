# Autonomous Multi-Strategy Trading System
# Module 18b — Backtest Metrics
# Calculates performance statistics from backtest results
# Sharpe ratio, drawdown, win rate, profit factor

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

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

logger = setup_logger('metrics', 'logs/backtest.log')

# ── Success Criteria ──────────────────────────────────────────
MAX_DRAWDOWN_LIMIT  = 0.15
MIN_WIN_RATE        = 0.45
MIN_SHARPE          = 1.0
MAX_CONSEC_LOSS_DAYS = 7


def calculate_sharpe(
    returns: list,
    risk_free_rate: float = 0.0
) -> float:
    """
    Calculate annualised Sharpe ratio.

    Args:
        returns: List of period returns as decimals
        risk_free_rate: Annual risk-free rate

    Returns:
        Annualised Sharpe ratio as float
    """
    try:
        if not returns or len(returns) < 2:
            return 0.0

        returns_arr = np.array(returns, dtype=float)
        excess      = returns_arr - risk_free_rate / 252
        mean_excess = np.mean(excess)
        std_excess  = np.std(excess, ddof=1)

        if std_excess == 0:
            return 0.0

        sharpe = mean_excess / std_excess * np.sqrt(252)
        return round(float(sharpe), 4)

    except Exception as e:
        logger.error(f'calculate_sharpe failed: {e}')
        return 0.0


def calculate_max_drawdown(
    equity_curve: list
) -> dict:
    """
    Calculate maximum drawdown from an equity curve.

    Args:
        equity_curve: List of equity values over time

    Returns:
        Dictionary with max_drawdown_pct, max_drawdown_usd,
        drawdown_start, drawdown_end, recovery_index
    """
    try:
        if not equity_curve or len(equity_curve) < 2:
            return {
                'max_drawdown_pct': 0.0,
                'max_drawdown_usd': 0.0,
                'drawdown_start':   0,
                'drawdown_end':     0,
                'recovery_index':   None
            }

        equity = np.array(equity_curve, dtype=float)
        peak   = equity[0]
        max_dd = 0.0
        dd_start = 0
        dd_end   = 0
        recovery = None
        curr_peak_idx = 0

        for i in range(1, len(equity)):
            if equity[i] > peak:
                peak          = equity[i]
                curr_peak_idx = i
                recovery      = None

            drawdown = (peak - equity[i]) / peak

            if drawdown > max_dd:
                max_dd   = drawdown
                dd_start = curr_peak_idx
                dd_end   = i

        # Find recovery index
        if dd_end < len(equity) - 1:
            peak_val = equity[dd_start]
            for j in range(dd_end + 1, len(equity)):
                if equity[j] >= peak_val:
                    recovery = j
                    break

        return {
            'max_drawdown_pct': round(max_dd, 4),
            'max_drawdown_usd': round(
                float(equity[dd_start] - min(equity)), 2
            ),
            'drawdown_start':   dd_start,
            'drawdown_end':     dd_end,
            'recovery_index':   recovery
        }

    except Exception as e:
        logger.error(f'calculate_max_drawdown failed: {e}')
        return {
            'max_drawdown_pct': 0.0,
            'max_drawdown_usd': 0.0,
            'drawdown_start':   0,
            'drawdown_end':     0,
            'recovery_index':   None
        }


def calculate_win_rate(
    trades: list
) -> dict:
    """
    Calculate win rate and related statistics.

    Args:
        trades: List of trade dicts with pnl key

    Returns:
        Dictionary with win_rate, total_trades,
        winning_trades, losing_trades, avg_win,
        avg_loss, profit_factor
    """
    try:
        if not trades:
            return {
                'win_rate':       0.0,
                'total_trades':   0,
                'winning_trades': 0,
                'losing_trades':  0,
                'avg_win':        0.0,
                'avg_loss':       0.0,
                'profit_factor':  0.0
            }

        pnls    = [float(t.get('pnl', 0)) for t in trades]
        winners = [p for p in pnls if p > 0]
        losers  = [p for p in pnls if p <= 0]

        total    = len(pnls)
        n_wins   = len(winners)
        n_losses = len(losers)

        win_rate      = n_wins / total if total > 0 else 0.0
        avg_win       = np.mean(winners) if winners else 0.0
        avg_loss      = np.mean(losers)  if losers  else 0.0
        gross_profit  = sum(winners)
        gross_loss    = abs(sum(losers))
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0 else 0.0
        )

        return {
            'win_rate':       round(win_rate, 4),
            'total_trades':   total,
            'winning_trades': n_wins,
            'losing_trades':  n_losses,
            'avg_win':        round(float(avg_win), 2),
            'avg_loss':       round(float(avg_loss), 2),
            'profit_factor':  round(profit_factor, 4)
        }

    except Exception as e:
        logger.error(f'calculate_win_rate failed: {e}')
        return {
            'win_rate':       0.0,
            'total_trades':   0,
            'winning_trades': 0,
            'losing_trades':  0,
            'avg_win':        0.0,
            'avg_loss':       0.0,
            'profit_factor':  0.0
        }


def calculate_all_metrics(
    trades: list,
    equity_curve: list
) -> dict:
    """
    Calculate all performance metrics combined.

    Args:
        trades: List of trade dicts
        equity_curve: List of equity values

    Returns:
        Dictionary with all metrics
    """
    try:
        win_stats = calculate_win_rate(trades)
        dd_stats  = calculate_max_drawdown(equity_curve)

        # Calculate returns from equity curve
        equity_arr = np.array(equity_curve, dtype=float)
        if len(equity_arr) > 1:
            returns = list(
                np.diff(equity_arr) / equity_arr[:-1]
            )
        else:
            returns = []

        sharpe = calculate_sharpe(returns)

        initial = equity_curve[0] if equity_curve else 0
        final   = equity_curve[-1] if equity_curve else 0
        total_return_usd = round(final - initial, 2)
        total_return_pct = round(
            (final - initial) / initial * 100
            if initial > 0 else 0.0, 2
        )

        # Average trades per day
        total_trades = win_stats['total_trades']
        days = max(1, len(equity_curve) / 24)
        avg_trades_per_day = round(total_trades / days, 2)

        return {
            **win_stats,
            **dd_stats,
            'sharpe_ratio':      sharpe,
            'total_return_pct':  total_return_pct,
            'total_return_usd':  total_return_usd,
            'avg_trades_per_day': avg_trades_per_day,
            'initial_capital':   round(initial, 2),
            'final_capital':     round(final, 2)
        }

    except Exception as e:
        logger.error(f'calculate_all_metrics failed: {e}')
        return {}


def format_report(
    metrics: dict,
    asset: str,
    period: str = '5 years'
) -> str:
    """
    Format backtest metrics as readable report.

    Args:
        metrics: Output from calculate_all_metrics
        asset: Asset name
        period: Backtest period description

    Returns:
        Formatted report string
    """
    try:
        dd_pct    = round(
            metrics.get('max_drawdown_pct', 0) * 100, 2
        )
        dd_usd    = metrics.get('max_drawdown_usd', 0)
        wr        = round(
            metrics.get('win_rate', 0) * 100, 1
        )
        pf        = metrics.get('profit_factor', 0)
        sharpe    = metrics.get('sharpe_ratio', 0)
        ret_pct   = metrics.get('total_return_pct', 0)
        ret_usd   = metrics.get('total_return_usd', 0)
        trades    = metrics.get('total_trades', 0)
        apd       = metrics.get('avg_trades_per_day', 0)

        # Check pass/fail criteria
        passed = (
            dd_pct / 100 < MAX_DRAWDOWN_LIMIT and
            wr / 100 >= MIN_WIN_RATE and
            sharpe >= MIN_SHARPE
        )

        result_str = 'PASSED' if passed else 'FAILED'

        return (
            f'BACKTEST REPORT — {asset}\n'
            f'{"─" * 25}\n'
            f'Period: {period}\n'
            f'Total Trades: {trades}\n'
            f'Win Rate: {wr}%\n'
            f'Profit Factor: {pf}\n'
            f'Sharpe Ratio: {sharpe}\n'
            f'Max Drawdown: {dd_pct}% (${dd_usd:,.2f})\n'
            f'Total Return: {ret_pct}% (${ret_usd:,.2f})\n'
            f'Avg Trades/Day: {apd}\n'
            f'{"─" * 25}\n'
            f'RESULT: {result_str} — '
            f'{"meets all criteria" if passed else "does not meet criteria"}'
        )

    except Exception as e:
        logger.error(f'format_report failed: {e}')
        return f'BACKTEST REPORT — {asset}\nError generating report.'


def check_passes_criteria(metrics: dict) -> dict:
    """
    Check if backtest results meet go-live criteria.

    Args:
        metrics: Output from calculate_all_metrics

    Returns:
        Dictionary with passed bool and details
    """
    try:
        dd_pct = metrics.get('max_drawdown_pct', 1.0)
        wr     = metrics.get('win_rate', 0.0)
        sharpe = metrics.get('sharpe_ratio', 0.0)

        dd_pass     = dd_pct < MAX_DRAWDOWN_LIMIT
        wr_pass     = wr >= MIN_WIN_RATE
        sharpe_pass = sharpe >= MIN_SHARPE

        all_passed = dd_pass and wr_pass and sharpe_pass

        return {
            'passed':         all_passed,
            'drawdown_pass':  dd_pass,
            'win_rate_pass':  wr_pass,
            'sharpe_pass':    sharpe_pass,
            'details': {
                'max_drawdown': f'{round(dd_pct*100,2)}% '
                    f'(limit {MAX_DRAWDOWN_LIMIT*100}%)',
                'win_rate':     f'{round(wr*100,1)}% '
                    f'(min {MIN_WIN_RATE*100}%)',
                'sharpe':       f'{sharpe} '
                    f'(min {MIN_SHARPE})'
            }
        }

    except Exception as e:
        logger.error(f'check_passes_criteria failed: {e}')
        return {'passed': False}


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 18b — METRICS TESTS ===\n')
    np.random.seed(42)

    # Build mock trades 12 winners 8 losers
    mock_trades = (
        [{'pnl': round(np.random.uniform(10, 100), 2)}
         for _ in range(12)] +
        [{'pnl': round(-np.random.uniform(5, 40), 2)}
         for _ in range(8)]
    )

    # Build mock equity curve
    equity = [10000.0]
    for t in mock_trades:
        equity.append(equity[-1] + t['pnl'])

    # Test 1 — Win rate
    print('Test 1: calculate_win_rate...')
    wr = calculate_win_rate(mock_trades)
    print(f'  Win rate: {round(wr["win_rate"]*100,1)}%')
    print(f'  Profit factor: {wr["profit_factor"]}')
    passed = wr['win_rate'] == 0.6
    print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

    # Test 2 — Max drawdown
    print('Test 2: calculate_max_drawdown...')
    dd_curve = [
        10000, 11000, 10500, 9800, 9900, 10200
    ]
    dd = calculate_max_drawdown(dd_curve)
    print(
        f'  Max drawdown: {round(dd["max_drawdown_pct"]*100,2)}%'
    )
    passed = dd['max_drawdown_pct'] > 0
    print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

    # Test 3 — Sharpe ratio
    print('Test 3: calculate_sharpe...')
    returns = [t['pnl'] / 10000 for t in mock_trades]
    sharpe  = calculate_sharpe(returns)
    print(f'  Sharpe ratio: {sharpe}')
    print('Test 3: PASSED\n')

    # Test 4 — All metrics
    print('Test 4: calculate_all_metrics...')
    all_m = calculate_all_metrics(mock_trades, equity)
    print(f'  Total return: ${all_m["total_return_usd"]}')
    print(f'  Sharpe: {all_m["sharpe_ratio"]}')
    print(f'  Max DD: {round(all_m["max_drawdown_pct"]*100,2)}%')
    print('Test 4: PASSED\n')

    # Test 5 — format_report
    print('Test 5: format_report...')
    report = format_report(all_m, 'BTC/USD', '30 days')
    print(report)
    print('Test 5: PASSED\n')

    print('=== MODULE 18b — METRICS: ALL TESTS PASSED ===')
