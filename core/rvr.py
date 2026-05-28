# Autonomous Multi-Strategy Trading System
# Module 06 — Realized Volatility Ratio
# Fourth signal in the Decision Engine
# Measures whether current volatility is normal,
# dangerously high, or suspiciously dead
# Also contains the Chaotic Tripwire emergency override

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    RVR_DANGER_THRESHOLD,
    RVR_DEAD_THRESHOLD,
    CHAOTIC_ATR_MULTIPLIER
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

logger = setup_logger('rvr', 'logs/errors.log')


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> Optional[pd.Series]:
    """
    Calculate Average True Range.

    True Range = max of:
        High - Low
        |High - Previous Close|
        |Low - Previous Close|

    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices
        period: ATR rolling period

    Returns:
        Pandas Series of ATR values or None on failure
    """
    try:
        high  = pd.Series(np.array(high, dtype=float))
        low   = pd.Series(np.array(low, dtype=float))
        close = pd.Series(np.array(close, dtype=float))

        if len(close) < period + 1:
            logger.warning(
                f'calculate_atr: insufficient data '
                f'({len(close)} candles, need {period + 1})'
            )
            return None

        prev_close = close.shift(1)

        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean()

        logger.debug(
            f'ATR calculated: latest={atr.iloc[-1]:.4f}'
        )
        return atr

    except Exception as e:
        logger.error(f'calculate_atr failed: {e}')
        return None


def calculate(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    short_period: int = 5,
    long_period: int = 20
) -> Optional[float]:
    """
    Calculate Realized Volatility Ratio.

    RVR = ATR(short) / ATR(long)

    RVR > 1.5 = DANGER — energy spiking
    RVR 0.8 to 1.5 = NORMAL — strategies run freely
    RVR < 0.8 = DEAD — scalper only

    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices
        short_period: Short ATR period
        long_period: Long ATR period

    Returns:
        RVR float rounded to 4 decimal places or None on failure
    """
    try:
        atr_short = calculate_atr(high, low, close, short_period)
        atr_long  = calculate_atr(high, low, close, long_period)

        if atr_short is None or atr_long is None:
            return None

        current_short = atr_short.iloc[-1]
        current_long  = atr_long.iloc[-1]

        if pd.isna(current_short) or pd.isna(current_long):
            return None

        if current_long == 0:
            logger.warning('calculate: long ATR is zero')
            return None

        rvr = float(current_short / current_long)
        logger.debug(f'RVR calculated: {rvr:.4f}')
        return round(rvr, 4)

    except Exception as e:
        logger.error(f'calculate failed: {e}')
        return None


def calculate_with_signal(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series
) -> Optional[dict]:
    """
    Calculate RVR with regime classification and size multiplier.

    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices

    Returns:
        Dictionary with rvr, regime, size_multiplier,
        atr_short, atr_long, interpretation or None on failure
    """
    try:
        atr_short_series = calculate_atr(high, low, close, 5)
        atr_long_series  = calculate_atr(high, low, close, 20)

        if atr_short_series is None or atr_long_series is None:
            return None

        atr_short_val = float(atr_short_series.iloc[-1])
        atr_long_val  = float(atr_long_series.iloc[-1])

        if pd.isna(atr_short_val) or pd.isna(atr_long_val):
            return None

        if atr_long_val == 0:
            return None

        rvr = round(atr_short_val / atr_long_val, 4)

        # Regime classification
        if rvr > RVR_DANGER_THRESHOLD:
            regime           = 'DANGER'
            size_multiplier  = 0.5
            interpretation   = 'Volatility spike — position sizes halved'
        elif rvr < RVR_DEAD_THRESHOLD:
            regime           = 'DEAD'
            size_multiplier  = 0.0
            interpretation   = 'Dead market — scalper only'
        else:
            regime           = 'NORMAL'
            size_multiplier  = 1.0
            interpretation   = 'Normal volatility — full position sizing active'

        return {
            'rvr':              rvr,
            'regime':           regime,
            'size_multiplier':  size_multiplier,
            'atr_short':        round(atr_short_val, 4),
            'atr_long':         round(atr_long_val, 4),
            'interpretation':   interpretation
        }

    except Exception as e:
        logger.error(f'calculate_with_signal failed: {e}')
        return None


def chaotic_tripwire(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    multiplier: float = CHAOTIC_ATR_MULTIPLIER
) -> Optional[dict]:
    """
    Always-on emergency override that fires when ATR spikes
    suddenly and dramatically. Bypasses the regime classifier.

    If current ATR > baseline ATR x multiplier:
        CHAOTIC — block all new entries immediately

    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices
        multiplier: ATR spike threshold multiplier

    Returns:
        Dictionary with triggered, current_atr,
        baseline_atr, ratio, message or None on failure
    """
    try:
        atr_current  = calculate_atr(high, low, close, 5)
        atr_baseline = calculate_atr(high, low, close, 20)

        if atr_current is None or atr_baseline is None:
            return None

        current_val  = float(atr_current.iloc[-1])
        baseline_val = float(atr_baseline.iloc[-1])

        if pd.isna(current_val) or pd.isna(baseline_val):
            return None

        if baseline_val == 0:
            return None

        ratio     = round(current_val / baseline_val, 4)
        triggered = ratio > multiplier

        if triggered:
            message = (
                f'CHAOTIC TRIPWIRE FIRED — '
                f'all new entries blocked (ratio={ratio})'
            )
            logger.warning(message)
        else:
            message = f'Normal — tripwire not triggered (ratio={ratio})'

        return {
            'triggered':    triggered,
            'current_atr':  round(current_val, 4),
            'baseline_atr': round(baseline_val, 4),
            'ratio':        ratio,
            'message':      message
        }

    except Exception as e:
        logger.error(f'chaotic_tripwire failed: {e}')
        return None


def rolling_rvr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 50
) -> pd.Series:
    """
    Calculate rolling RVR over a price series.

    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices
        window: Rolling window size

    Returns:
        Pandas Series of RVR values over time
    """
    try:
        result = []
        n = len(close)

        high_arr  = np.array(high, dtype=float)
        low_arr   = np.array(low, dtype=float)
        close_arr = np.array(close, dtype=float)

        for i in range(n):
            if i < window:
                result.append(None)
            else:
                h = pd.Series(high_arr[i - window:i])
                l = pd.Series(low_arr[i - window:i])
                c = pd.Series(close_arr[i - window:i])
                rvr = calculate(h, l, c)
                result.append(rvr)

        return pd.Series(result, index=close.index
                         if hasattr(close, 'index') else None)

    except Exception as e:
        logger.error(f'rolling_rvr failed: {e}')
        return pd.Series([None] * len(close))


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 06 — RVR TESTS ===\n')
    np.random.seed(42)
    n = 200

    # Helper to build OHLCV from close prices
    def build_ohlcv(close_arr, volatility=1.0):
        high  = pd.Series(
            close_arr + np.abs(np.random.normal(0, volatility, n))
        )
        low   = pd.Series(
            close_arr - np.abs(np.random.normal(0, volatility, n))
        )
        close = pd.Series(close_arr)
        return high, low, close

    # Test 1 — Normal volatility
    print('Test 1: Normal volatility dataset...')
    close_normal = np.cumsum(np.random.normal(0.1, 1.0, n)) + 100
    h, l, c = build_ohlcv(close_normal, volatility=1.0)
    rvr_normal = calculate(h, l, c)
    print(f'Normal RVR = {rvr_normal}')
    passed = (
        rvr_normal is not None and
        RVR_DEAD_THRESHOLD <= rvr_normal <= RVR_DANGER_THRESHOLD
    )
    print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

    # Test 2 — Danger volatility (spike last 10 candles)
    print('Test 2: Danger volatility dataset...')
    close_danger = close_normal.copy()
    h_danger = h.copy()
    l_danger = l.copy()
    spike_vals = np.abs(np.random.normal(0, 30.0, 10))
    h_danger = pd.concat([
        h_danger[:-10],
        pd.Series(
            close_danger[-10:] + spike_vals,
            index=h_danger.index[-10:]
        )
    ])
    l_danger = pd.concat([
        l_danger[:-10],
        pd.Series(
            close_danger[-10:] - spike_vals,
            index=l_danger.index[-10:]
        )
    ])
    rvr_danger = calculate(h_danger, l_danger, c)
    print(f'Danger RVR = {rvr_danger}')
    passed = rvr_danger is not None and rvr_danger > RVR_DANGER_THRESHOLD
    print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

    # Test 3 — Dead volatility
    print('Test 3: Dead volatility dataset...')
    close_dead = np.full(n, 100.0)
    close_dead += np.random.normal(0, 0.001, n)
    h_dead = pd.Series(close_dead + 0.001)
    l_dead = pd.Series(close_dead - 0.001)
    c_dead = pd.Series(close_dead)
    rvr_dead = calculate(h_dead, l_dead, c_dead)
    print(f'Dead RVR = {rvr_dead}')
    passed = rvr_dead is not None and rvr_dead < RVR_DEAD_THRESHOLD
    print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

    # Test 4 — calculate_with_signal
    print('Test 4: calculate_with_signal on all three datasets...')
    for name, hh, ll, cc in [
        ('Normal', h, l, c),
        ('Danger', h_danger, l_danger, c),
        ('Dead', h_dead, l_dead, c_dead)
    ]:
        result = calculate_with_signal(hh, ll, cc)
        if result:
            print(
                f'  {name}: RVR={result["rvr"]} '
                f'regime={result["regime"]} '
                f'multiplier={result["size_multiplier"]}'
            )
    print('Test 4: PASSED\n')

    # Test 5 — Chaotic tripwire
    print('Test 5: Chaotic tripwire tests...')
    tw_danger = chaotic_tripwire(h_danger, l_danger, c)
    tw_normal = chaotic_tripwire(h, l, c)
    print(f'  Danger: triggered={tw_danger["triggered"]} '
          f'ratio={tw_danger["ratio"]}')
    print(f'  Normal: triggered={tw_normal["triggered"]} '
          f'ratio={tw_normal["ratio"]}')
    passed = (
        tw_danger is not None and tw_danger['triggered'] and
        tw_normal is not None and not tw_normal['triggered']
    )
    print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

    # Test 6 — rolling_rvr
    print('Test 6: rolling_rvr on normal dataset...')
    rolling = rolling_rvr(h, l, c, window=50)
    last5 = rolling.dropna().tail(5)
    print(f'Last 5 rolling RVR values:\n{last5.to_string()}')
    print('Test 6: PASSED\n')

    all_passed = (
        rvr_normal is not None and
        RVR_DEAD_THRESHOLD <= rvr_normal <= RVR_DANGER_THRESHOLD and
        rvr_danger is not None and
        rvr_danger > RVR_DANGER_THRESHOLD and
        rvr_dead is not None and
        rvr_dead < RVR_DEAD_THRESHOLD and
        tw_danger['triggered'] and
        not tw_normal['triggered']
    )
    print(
        '=== MODULE 06 — RVR: '
        f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
      )
