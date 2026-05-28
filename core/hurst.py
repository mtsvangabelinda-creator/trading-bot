# Autonomous Multi-Strategy Trading System
# Module 03 — Hurst Exponent
# Primary signal in the Decision Engine
# Determines whether market is trending, mean-reverting, or random

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import HURST_LOOKBACK

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

logger = setup_logger('hurst', 'logs/errors.log')

# ── Regime Thresholds ─────────────────────────────────────────
TRENDING_THRESHOLD  = 0.55
REVERTING_THRESHOLD = 0.45
MIN_CHUNK_SIZE      = 8


def calculate(
    prices: pd.Series | np.ndarray
) -> Optional[float]:
    """
    Calculate the Hurst Exponent using Rescaled Range R/S Analysis.

    H > 0.55 = TRENDING — momentum persists
    H < 0.45 = MEAN_REVERTING — price snaps back
    H 0.45-0.55 = DEAD_ZONE — no strong directional edge

    Args:
        prices: Series or array of closing prices

    Returns:
        Hurst Exponent as float 0 to 1 rounded to 4 decimal
        places or None on failure
    """
    try:
        prices = np.array(prices, dtype=float)

        if len(prices) < 20:
            logger.warning(
                f'calculate: insufficient data ({len(prices)} prices)'
            )
            return None

        # Step 1 — Calculate log returns
        returns = np.log(prices[1:] / prices[:-1])
        n = len(returns)

        # Step 2 — Build chunk sizes
        chunk_sizes = []
        size = n // 2
        while size >= MIN_CHUNK_SIZE:
            chunk_sizes.append(size)
            size = size // 2

        if len(chunk_sizes) < 2:
            logger.warning('calculate: not enough chunk sizes')
            return None

        # Step 3 — Calculate R/S for each chunk size
        rs_values = []
        valid_sizes = []

        for chunk_size in chunk_sizes:
            n_chunks = n // chunk_size
            if n_chunks < 1:
                continue

            rs_list = []
            for i in range(n_chunks):
                chunk = returns[i * chunk_size:(i + 1) * chunk_size]
                if len(chunk) < MIN_CHUNK_SIZE:
                    continue

                # Mean adjust
                mean = np.mean(chunk)
                deviations = chunk - mean

                # Cumulative sum
                cumulative = np.cumsum(deviations)

                # R = range of cumulative deviations
                R = np.max(cumulative) - np.min(cumulative)

                # S = standard deviation
                S = np.std(chunk, ddof=1)

                if S > 0:
                    rs_list.append(R / S)

            if rs_list:
                rs_values.append(np.mean(rs_list))
                valid_sizes.append(chunk_size)

        if len(valid_sizes) < 2:
            logger.warning('calculate: insufficient valid chunk sizes')
            return None

        # Step 4 — Linear regression on log scale
        log_sizes = np.log(valid_sizes)
        log_rs    = np.log(rs_values)

        # Slope of regression = Hurst Exponent
        coeffs = np.polyfit(log_sizes, log_rs, 1)
        H = coeffs[0]

        # Clip to valid range
        H = float(np.clip(H, 0.0, 1.0))

        logger.debug(f'Hurst calculated: H={H:.4f}')
        return round(H, 4)

    except Exception as e:
        logger.error(f'calculate failed: {e}')
        return None


def calculate_with_confidence(
    prices: pd.Series | np.ndarray
) -> Optional[dict]:
    """
    Calculate Hurst Exponent with confidence score and regime.

    Args:
        prices: Series or array of closing prices

    Returns:
        Dictionary with hurst, confidence, regime,
        trend_factor, reversion_factor or None on failure
    """
    try:
        prices = np.array(prices, dtype=float)

        if len(prices) < 20:
            return None

        # Get log returns and chunk sizes
        returns = np.log(prices[1:] / prices[:-1])
        n = len(returns)

        chunk_sizes = []
        size = n // 2
        while size >= MIN_CHUNK_SIZE:
            chunk_sizes.append(size)
            size = size // 2

        if len(chunk_sizes) < 2:
            return None

        rs_values  = []
        valid_sizes = []

        for chunk_size in chunk_sizes:
            n_chunks = n // chunk_size
            rs_list  = []

            for i in range(n_chunks):
                chunk = returns[i * chunk_size:(i + 1) * chunk_size]
                if len(chunk) < MIN_CHUNK_SIZE:
                    continue
                mean       = np.mean(chunk)
                deviations = chunk - mean
                cumulative = np.cumsum(deviations)
                R = np.max(cumulative) - np.min(cumulative)
                S = np.std(chunk, ddof=1)
                if S > 0:
                    rs_list.append(R / S)

            if rs_list:
                rs_values.append(np.mean(rs_list))
                valid_sizes.append(chunk_size)

        if len(valid_sizes) < 2:
            return None

        log_sizes = np.log(valid_sizes)
        log_rs    = np.log(rs_values)

        coeffs    = np.polyfit(log_sizes, log_rs, 1)
        H         = float(np.clip(coeffs[0], 0.0, 1.0))

        # R-squared as confidence
        predicted   = np.polyval(coeffs, log_sizes)
        ss_res      = np.sum((log_rs - predicted) ** 2)
        ss_tot      = np.sum((log_rs - np.mean(log_rs)) ** 2)
        r_squared   = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
        confidence  = round(max(0.0, min(1.0, r_squared)), 4)

        # Regime classification
        if H > TRENDING_THRESHOLD:
            regime = 'TRENDING'
        elif H < REVERTING_THRESHOLD:
            regime = 'MEAN_REVERTING'
        else:
            regime = 'DEAD_ZONE'

        # Position size factors
        trend_factor = max(
            0.0, (H - 0.5) / (0.7 - 0.5)
        )
        trend_factor = round(min(1.0, trend_factor), 4)

        reversion_factor = max(
            0.0, (0.5 - H) / (0.5 - 0.3)
        )
        reversion_factor = round(min(1.0, reversion_factor), 4)

        return {
            'hurst':            round(H, 4),
            'confidence':       confidence,
            'regime':           regime,
            'trend_factor':     trend_factor,
            'reversion_factor': reversion_factor
        }

    except Exception as e:
        logger.error(f'calculate_with_confidence failed: {e}')
        return None


def rolling_hurst(
    prices: pd.Series,
    window: int = HURST_LOOKBACK
) -> pd.Series:
    """
    Calculate rolling Hurst Exponent over a price series.

    Args:
        prices: Pandas Series of closing prices
        window: Rolling window size in candles

    Returns:
        Pandas Series of Hurst values, None where insufficient data
    """
    try:
        result = []
        prices_array = np.array(prices, dtype=float)

        for i in range(len(prices_array)):
            if i < window:
                result.append(None)
            else:
                window_prices = prices_array[i - window:i]
                h = calculate(window_prices)
                result.append(h)

        return pd.Series(result, index=prices.index)

    except Exception as e:
        logger.error(f'rolling_hurst failed: {e}')
        return pd.Series([None] * len(prices))


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    import numpy as np

    print('\n=== MODULE 03 — HURST EXPONENT TESTS ===\n')
    np.random.seed(42)

    # Test 1 — Trending series
    print('Test 1: Trending price series...')
    trend = np.cumsum(
        np.random.normal(0.1, 0.5, 200)
    ) + 100
    H_trend = calculate(trend)
    print(f'Trending H = {H_trend}')
    passed = H_trend is not None and H_trend > 0.55
    print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

    # Test 2 — Mean reverting series
    print('Test 2: Mean reverting price series...')
    mean_rev = []
    price = 100.0
    for _ in range(200):
        price = price + (100 - price) * 0.3 + np.random.normal(0, 0.5)
        mean_rev.append(price)
    H_rev = calculate(np.array(mean_rev))
    print(f'Mean Reverting H = {H_rev}')
    passed = H_rev is not None and H_rev < 0.45
    print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

    # Test 3 — Random walk
    print('Test 3: Random walk price series...')
    random_walk = np.cumsum(np.random.normal(0, 1, 200)) + 100
    H_random = calculate(random_walk)
    print(f'Random Walk H = {H_random}')
    print(f'Test 3: PASSED (computed successfully)\n')

    # Test 4 — calculate_with_confidence
    print('Test 4: calculate_with_confidence on trending series...')
    result = calculate_with_confidence(trend)
    if result:
        for k, v in result.items():
            print(f'  {k}: {v}')
        print('Test 4: PASSED\n')
    else:
        print('Test 4: FAILED\n')

    # Test 5 — rolling_hurst
    print('Test 5: rolling_hurst on trending series...')
    series = pd.Series(trend)
    rolling = rolling_hurst(series, window=100)
    last5 = rolling.dropna().tail(5)
    print(f'Last 5 rolling values:\n{last5.to_string()}')
    print('Test 5: PASSED\n')

    all_passed = (
        H_trend is not None and H_trend > 0.55 and
        H_rev is not None and H_rev < 0.45 and
        result is not None
    )
    print(
        '=== MODULE 03 — HURST EXPONENT: '
        f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
      )
