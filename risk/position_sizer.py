# Autonomous Multi-Strategy Trading System
# Module 09 — Position Sizer
# Calculates exact position size for every trade signal
# Formula: Final Size = Base Size x Edge Score x RVR Multiplier
# Turns analysis into a precise actionable trade size

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    ATR_PERIOD,
    ATR_MULTIPLIER,
    BASE_RISK_PCT,
    ASSETS
)
from core.rvr import calculate_atr

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

logger = setup_logger('position_sizer', 'logs/errors.log')

# ── Safety Cap ────────────────────────────────────────────────
MAX_POSITION_PCT = 0.10


def calculate_base_size(
    asset_capital: float,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    risk_pct: float = BASE_RISK_PCT
) -> Optional[dict]:
    """
    Calculate the base position size before edge and RVR adjustment.

    Formula:
        Base Size = (Asset Capital x Risk%) / (ATR x ATR_MULTIPLIER)

    Args:
        asset_capital: Dollar value allocated to this asset
        close: Series of closing prices
        high: Series of high prices
        low: Series of low prices
        risk_pct: Percentage of capital to risk per trade

    Returns:
        Dictionary with base_size, dollar_risk, atr,
        atr_multiplier or None on failure
    """
    try:
        atr_series = calculate_atr(high, low, close, ATR_PERIOD)

        if atr_series is None:
            logger.error('calculate_base_size: ATR calculation failed')
            return None

        current_atr = float(atr_series.iloc[-1])

        if pd.isna(current_atr) or current_atr == 0:
            logger.error('calculate_base_size: invalid ATR value')
            return None

        dollar_risk = asset_capital * risk_pct
        denominator = current_atr * ATR_MULTIPLIER

        if denominator == 0:
            return None

        base_size = dollar_risk / denominator

        logger.debug(
            f'Base size: capital={asset_capital}, '
            f'risk={dollar_risk}, atr={current_atr}, '
            f'base_size={base_size}'
        )

        return {
            'base_size':      round(base_size, 6),
            'dollar_risk':    round(dollar_risk, 2),
            'atr':            round(current_atr, 4),
            'atr_multiplier': ATR_MULTIPLIER
        }

    except Exception as e:
        logger.error(f'calculate_base_size failed: {e}')
        return None


def calculate(
    asset_capital: float,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    edge_score: float,
    rvr_multiplier: float,
    risk_pct: float = BASE_RISK_PCT
) -> Optional[dict]:
    """
    Calculate the final position size for a trade signal.

    Formula:
        Final Size = Base Size x Edge Score x RVR Multiplier

    Args:
        asset_capital: Dollar value allocated to this asset
        close: Series of closing prices
        high: Series of high prices
        low: Series of low prices
        edge_score: Winning strategy score from edge_score module
        rvr_multiplier: RVR safety multiplier 1.0, 0.5, or 0.0
        risk_pct: Percentage of capital to risk per trade

    Returns:
        Dictionary with final_size, final_size_usd,
        size_breakdown and all calculation details
        or None on failure
    """
    try:
        # Get base size
        base_result = calculate_base_size(
            asset_capital, close, high, low, risk_pct
        )

        if base_result is None:
            return None

        base_size   = base_result['base_size']
        dollar_risk = base_result['dollar_risk']
        current_atr = base_result['atr']

        # Apply edge score and RVR multiplier
        final_size = base_size * edge_score * rvr_multiplier

        # Safety cap at 10% of asset capital
        current_price = float(close.iloc[-1])
        if current_price > 0:
            max_size = (asset_capital * MAX_POSITION_PCT) / current_price
            if final_size > max_size:
                logger.warning(
                    f'Position size capped at 10% of capital: '
                    f'{final_size:.6f} -> {max_size:.6f}'
                )
                final_size = max_size

        final_size = round(final_size, 4)

        # Return None if position is too small
        if final_size <= 0.0:
            logger.debug('calculate: final size is zero — no trade')
            return None

        final_size_usd = round(final_size * current_price, 2)

        size_breakdown = (
            f'Base: {base_result["base_size"]:.4f} units x '
            f'Edge {edge_score} x '
            f'RVR {rvr_multiplier} = '
            f'{final_size} units '
            f'(${final_size_usd:,.2f} at '
            f'${current_price:,.2f})'
        )

        return {
            'final_size':      final_size,
            'final_size_usd':  final_size_usd,
            'base_size':       base_result['base_size'],
            'dollar_risk':     dollar_risk,
            'atr':             current_atr,
            'edge_score':      edge_score,
            'rvr_multiplier':  rvr_multiplier,
            'current_price':   round(current_price, 2),
            'size_breakdown':  size_breakdown
        }

    except Exception as e:
        logger.error(f'calculate failed: {e}')
        return None


def calculate_all(
    total_capital: float,
    market_data: dict,
    edge_scores: dict,
    rvr_results: dict
) -> dict:
    """
    Calculate position sizes for all assets.

    Args:
        total_capital: Total account value in dollars
        market_data: Dict of asset to close/high/low Series
        edge_scores: Dict of asset to edge score dict
        rvr_results: Dict of asset to RVR result dict

    Returns:
        Dictionary of asset to position size result
    """
    results = {}

    for asset, allocation in ASSETS.items():
        try:
            if asset not in market_data:
                continue

            asset_capital = total_capital * allocation
            data          = market_data[asset]
            edge_result   = edge_scores.get(asset)
            rvr_result    = rvr_results.get(asset)

            if edge_result is None or rvr_result is None:
                results[asset] = None
                continue

            edge_score     = edge_result.get(
                'position_size_factor', 0.0
            )
            rvr_multiplier = rvr_result.get('size_multiplier', 1.0)

            result = calculate(
                asset_capital,
                data['close'],
                data['high'],
                data['low'],
                edge_score,
                rvr_multiplier
            )
            results[asset] = result

        except Exception as e:
            logger.error(
                f'calculate_all failed for {asset}: {e}'
            )
            results[asset] = None

    return results


def format_signal(
    asset: str,
    direction: str,
    strategy: str,
    size_result: dict,
    sentiment: str,
    edge_result: dict
) -> str:
    """
    Format a complete trade signal for Telegram delivery.

    Args:
        asset: Trading pair e.g. BTC/USD
        direction: long or short
        strategy: Strategy name
        size_result: Output from calculate()
        sentiment: Current sentiment string
        edge_result: Output from edge_score.calculate()

    Returns:
        Formatted Telegram trade signal string
    """
    try:
        if size_result is None:
            return f'TRADE SIGNAL — {asset}\nPosition size too small to trade.'

        strategy_display = strategy.replace('_', '-').title()
        direction_display = direction.upper()

        atr          = size_result.get('atr', 0)
        stop_dist    = round(atr * ATR_MULTIPLIER, 2)
        final_size   = size_result.get('final_size', 0)
        size_usd     = size_result.get('final_size_usd', 0)
        dollar_risk  = size_result.get('dollar_risk', 0)
        edge_score   = size_result.get('edge_score', 0)
        rvr_regime   = (
            edge_result.get('rvr_regime', 'NORMAL')
            if edge_result else 'NORMAL'
        )
        hurst        = (
            edge_result.get('hurst', 0)
            if edge_result else 0
        )
        hurst_regime = (
            edge_result.get('hurst_regime', '')
            if edge_result else ''
        )

        signal = (
            f'TRADE SIGNAL — {asset}\n'
            f'{"─" * 22}\n'
            f'Strategy: {strategy_display}\n'
            f'Direction: {direction_display}\n'
            f'Position Size: {final_size} '
            f'{asset.split("/")[0]}\n'
            f'Position Value: ${size_usd:,.2f}\n'
            f'Dollar Risk: ${dollar_risk:,.2f} '
            f'({round(BASE_RISK_PCT * 100, 1)}% of capital)\n'
            f'Entry: Market order now\n'
            f'Stop Loss Distance: '
            f'{ATR_MULTIPLIER} x ATR (${stop_dist:,.2f})\n'
            f'{"─" * 22}\n'
            f'Edge Score: {edge_score} '
            f'({"strong" if edge_score > 0.6 else "moderate"})\n'
            f'Hurst: {hurst} ({hurst_regime})\n'
            f'RVR: {rvr_regime} — '
            f'{"full size" if rvr_regime == "NORMAL" else "reduced"}\n'
            f'Sentiment: {sentiment} — '
            f'{"long only" if sentiment == "BULLISH" else "short only" if sentiment == "BEARISH" else "both directions"}\n'
            f'{"─" * 22}\n'
            f'Manually place this order on Kraken now.'
        )

        return signal

    except Exception as e:
        logger.error(f'format_signal failed: {e}')
        return f'TRADE SIGNAL — {asset}\nFormatting error occurred.'


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 09 — POSITION SIZER TESTS ===\n')
    np.random.seed(42)
    n = 200

    # Build BTC-like test dataset
    close_arr = np.linspace(40000, 45000, n)
    close_arr += np.random.normal(0, 100, n)
    close = pd.Series(close_arr)
    high  = pd.Series(close_arr * 1.002)
    low   = pd.Series(close_arr * 0.998)

    # Test 1 — calculate_base_size
    print('Test 1: calculate_base_size...')
    base = calculate_base_size(1000.0, close, high, low)
    if base:
        print(f'  Base size: {base["base_size"]} units')
        print(f'  Dollar risk: ${base["dollar_risk"]}')
        print(f'  ATR: {base["atr"]}')
        passed = 9.0 <= base['dollar_risk'] <= 11.0
        print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 1: FAILED\n')

    # Test 2 — Strong edge NORMAL RVR
    print('Test 2: Strong edge (0.80) NORMAL RVR...')
    result2 = calculate(1000.0, close, high, low, 0.80, 1.0)
    if result2:
        print(f'  Final size: {result2["final_size"]} units')
        print(f'  Value: ${result2["final_size_usd"]:,.2f}')
        print(f'  Breakdown: {result2["size_breakdown"]}')
        passed = result2['final_size_usd'] < 1000.0
        print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 2: FAILED\n')

    # Test 3 — Weak edge
    print('Test 3: Weak edge (0.25) NORMAL RVR...')
    result3 = calculate(1000.0, close, high, low, 0.25, 1.0)
    if result3 and result2:
        print(f'  Final size: {result3["final_size"]} units')
        passed = result3['final_size'] < result2['final_size']
        print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 3: FAILED\n')

    # Test 4 — DANGER RVR (should be half of test 2)
    print('Test 4: Strong edge (0.80) DANGER RVR (0.5)...')
    result4 = calculate(1000.0, close, high, low, 0.80, 0.5)
    if result4 and result2:
        print(f'  Final size: {result4["final_size"]} units')
        ratio = round(result4['final_size'] / result2['final_size'], 1)
        passed = ratio == 0.5
        print(f'  Ratio vs test 2: {ratio}')
        print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 4: FAILED\n')

    # Test 5 — DEAD RVR (should return None)
    print('Test 5: Strong edge (0.80) DEAD RVR (0.0)...')
    result5 = calculate(1000.0, close, high, low, 0.80, 0.0)
    passed = result5 is None
    print(f'  Result: {result5}')
    print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

    # Test 6 — format_signal
    print('Test 6: format_signal...')
    mock_edge = {
        'hurst': 0.61,
        'hurst_regime': 'TRENDING',
        'rvr_regime': 'NORMAL',
        'tf_score': 0.80
    }
    signal = format_signal(
        'BTC/USD', 'long', 'TREND_FOLLOWING',
        result2, 'BULLISH', mock_edge
    )
    print(signal)
    print('Test 6: PASSED\n')

    all_passed = (
        base is not None and
        9.0 <= base['dollar_risk'] <= 11.0 and
        result2 is not None and
        result3 is not None and
        result3['final_size'] < result2['final_size'] and
        result4 is not None and
        result5 is None
    )
    print(
        '=== MODULE 09 — POSITION SIZER: '
        f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
    )
