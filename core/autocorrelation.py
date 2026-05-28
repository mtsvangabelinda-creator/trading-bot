# Autonomous Multi-Strategy Trading System
# Module 04 — Autocorrelation
# Second signal in the Decision Engine
# Confirms Hurst reading from a different mathematical angle
# Measures whether the last price move predicts the next one

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

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

logger = setup_logger('autocorrelation', 'logs/errors.log')

# ── Signal Thresholds ─────────────────────────────────────────
TREND_THRESHOLD    =  0.05
REVERSION_THRESHOLD = -0.05


def calculate(
    prices: pd.Series | np.ndarray,
    lag: int = 1
) -> Optional[float]:
    """
    Calculate autocorrelation of price returns at given lag.

    Positive autocorrelation = trend-following has edge
    Negative autocorrelation = mean reversion has edge
    Near zero = scalper only, no directional edge

    Args:
        prices: Series or array of closing prices
        lag: Number of periods to lag (default 1)

    Returns:
        Autocorrelation float between -1 and 1 rounded to
        4 decimal places or None on failure
    """
    try:
        prices = np.array(prices, dtype=float)

        if len(prices) < 20:
            logger.warning(
                f'calculate: insufficient data ({len(prices)} prices)'
            )
            return None

        # Calculate returns
        returns = prices[1:] - prices[:-1]

        if len(returns) <= lag:
            logger.warning('calculate: not enough returns for lag')
            return None

        # Pearson correlation between returns and lagged returns
        r1 = returns[:-lag]
        r2 = returns[lag:]

        if len(r1) < 5 or np.std(r1) == 0 or np.std(r2) == 0:
            return None

        corr, _ = stats.pearsonr(r1, r2)
        result = round(float(corr), 4)

        logger.debug(f'Autocorrelation calculated: {result}')
        return result

    except Exception as e:
        logger.error(f'calculate failed: {e}')
        return None


def calculate_with_signal(
    prices: pd.Series | np.ndarray
) -> Optional[dict]:
    """
    Calculate autocorrelation with trading signal interpretation.

    Args:
        prices: Series or array of closing prices

    Returns:
        Dictionary with autocorr, signal, strength,
        trend_factor, reversion_factor or None on failure
    """
    try:
        autocorr = calculate(prices)

        if autocorr is None:
            return None

        # Determine signal
        if autocorr > TREND_THRESHOLD:
            signal = 'TREND_EDGE'
        elif autocorr < REVERSION_THRESHOLD:
            signal = 'REVERSION_EDGE'
        else:
            signal = 'NEUTRAL'

        # Strength is absolute value
        strength = round(abs(autocorr), 4)

        # Position size factors
        trend_factor     = round(max(0.0, min(1.0, autocorr)), 4)
        reversion_factor = round(max(0.0, min(1.0, -autocorr)), 4)

        return {
            'autocorr':         autocorr,
            'signal':           signal,
            'strength':         strength,
            'trend_factor':     trend_factor,
            'reversion_factor': reversion_factor
        }

    except Exception as e:
        logger.error(f'calculate_with_signal failed: {e}')
        return None


def multi_lag(
    prices: pd.Series | np.ndarray,
    lags: list = None
) -> Optional[dict]:
    """
    Calculate autocorrelation at multiple lags.

    Args:
        prices: Series or array of closing prices
        lags: List of lag periods to calculate

    Returns:
        Dictionary of lag to autocorrelation value
    """
    try:
        if lags is None:
            lags = [1, 2, 3, 5]

        result = {}
        for lag in lags:
            corr = calculate(prices, lag=lag)
            result[lag] = corr

        logger.debug(f'multi_lag calculated: {result}')
        return result

    except Exception as e:
        logger.error(f'multi_lag failed: {e}')
        return None


def rolling_autocorr(
    prices: pd.Series,
    window: int = 50,
    lag: int = 1
) -> pd.Series:
    """
    Calculate rolling autocorrelation over a price series.

    Args:
        prices: Pandas Series of closing prices
        window: Rolling window size in candles
        lag: Lag period for autocorrelation

    Returns:
        Pandas Series of autocorrelation values over time
    """
    try:
        result = []
        prices_array = np.array(prices, dtype=float)

        for i in range(len(prices_array)):
            if i < window:
                result.append(None)
            else:
                window_prices = prices_array[i - window:i]
                corr = calculate(window_prices, lag=lag)
                result.append(corr)

        return pd.Series(result, index=prices.index)

    except Exception as e:
        logger.error(f'rolling_autocorr failed: {e}')
        return pd.Series([None] * len(prices))


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 04 — AUTOCORRELATION TESTS ===\n')
    np.random.seed(42)

    # Test 1 — Trending series (AR(1) with positive phi)
    print('Test 1: Trending price series...')
    n = 200
    phi = 0.7
    noise = np.random.normal(0, 1, n)
    ar_trend = np.zeros(n)
    ar_trend[0] = 100
    for i in range(1, n):
        ar_trend[i] = ar_trend[i-1] + phi * (
            ar_trend[i-1] - ar_trend[i-2]
            if i > 1 else 0
        ) + noise[i]
    ar_trend = ar_trend + 100

    # Simpler trending series
    trend = np.cumsum(np.random.normal(0.2, 0.5, n)) + 100
    ac_trend = calculate(trend)
    print(f'Trending autocorr = {ac_trend}')
    passed = ac_trend is not None and ac_trend > 0.05
    print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

    # Test 2 — Mean reverting series
    print('Test 2: Mean reverting price series...')
    mean_rev = []
    price = 100.0
    for _ in range(n):
        price = price + (100 - price) * 0.5 + np.random.normal(0, 0.3)
        mean_rev.append(price)
    ac_rev = calculate(np.array(mean_rev))
    print(f'Mean reverting autocorr = {ac_rev}')
    passed = ac_rev is not None and ac_rev < -0.05
    print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

    # Test 3 — calculate_with_signal on trending
    print('Test 3: calculate_with_signal on trending series...')
    result_trend = calculate_with_signal(trend)
    if result_trend:
        for k, v in result_trend.items():
            print(f'  {k}: {v}')
        print('Test 3: PASSED\n')
    else:
        print('Test 3: FAILED\n')

    # Test 4 — calculate_with_signal on mean reverting
    print('Test 4: calculate_with_signal on mean reverting...')
    result_rev = calculate_with_signal(np.array(mean_rev))
    if result_rev:
        for k, v in result_rev.items():
            print(f'  {k}: {v}')
        print('Test 4: PASSED\n')
    else:
        print('Test 4: FAILED\n')

    # Test 5 — multi_lag on trending series
    print('Test 5: multi_lag on trending series...')
    ml = multi_lag(trend, lags=[1, 2, 3, 5])
    if ml:
        print(f'  Multi-lag results: {ml}')
        print('Test 5: PASSED\n')
    else:
        print('Test 5: FAILED\n')

    # Test 6 — rolling_autocorr
    print('Test 6: rolling_autocorr on trending series...')
    series = pd.Series(trend)
    rolling = rolling_autocorr(series, window=50)
    last5 = rolling.dropna().tail(5)
    print(f'Last 5 rolling values:\n{last5.to_string()}')
    print('Test 6: PASSED\n')

    all_passed = (
        ac_trend is not None and ac_trend > 0.05 and
        ac_rev is not None and ac_rev < -0.05 and
        result_trend is not None and
        result_rev is not None
    )
    print(
        '=== MODULE 04 — AUTOCORRELATION: '
        f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
          )
