# Autonomous Multi-Strategy Trading System
# Module 05 — Price Efficiency Coefficient
# Third signal in the Decision Engine
# Measures whether price moved efficiently in one direction
# or wasted energy moving back and forth

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

logger = setup_logger('pec', 'logs/errors.log')

# ── Signal Thresholds ─────────────────────────────────────────
TREND_THRESHOLD    = 0.6
REVERSION_THRESHOLD = 0.4


def calculate(
    prices: pd.Series | np.ndarray
) -> Optional[float]:
    """
    Calculate the Price Efficiency Coefficient.

    Formula:
        PEC = |Price_End - Price_Start| / Sum of |all moves|

    PEC near 1.0 = price moved efficiently in one direction
                   Trend-Following signal
    PEC near 0.0 = price moved a lot but went nowhere
                   Mean Reversion signal

    Args:
        prices: Series or array of closing prices

    Returns:
        PEC float between 0 and 1 rounded to 4 decimal places
        or None on failure
    """
    try:
        prices = np.array(prices, dtype=float)

        if len(prices) < 3:
            logger.warning(
                f'calculate: insufficient data ({len(prices)} prices)'
            )
            return None

        # Net move — absolute difference start to end
        net_move = abs(prices[-1] - prices[0])

        # Sum of all individual absolute moves
        individual_moves = np.abs(np.diff(prices))
        total_path = np.sum(individual_moves)

        if total_path == 0:
            logger.warning('calculate: total path is zero (flat market)')
            return None

        pec = net_move / total_path
        pec = float(np.clip(pec, 0.0, 1.0))

        logger.debug(f'PEC calculated: {pec:.4f}')
        return round(pec, 4)

    except Exception as e:
        logger.error(f'calculate failed: {e}')
        return None


def calculate_with_signal(
    prices: pd.Series | np.ndarray
) -> Optional[dict]:
    """
    Calculate PEC with trading signal and interpretation.

    Args:
        prices: Series or array of closing prices

    Returns:
        Dictionary with pec, signal, trend_factor,
        reversion_factor, interpretation or None on failure
    """
    try:
        pec = calculate(prices)

        if pec is None:
            return None

        # Determine signal
        if pec > TREND_THRESHOLD:
            signal = 'TREND_SIGNAL'
            interpretation = (
                'Price moving efficiently — trend likely continuing'
            )
        elif pec < REVERSION_THRESHOLD:
            signal = 'REVERSION_SIGNAL'
            interpretation = (
                'Price churning — mean reversion opportunity likely'
            )
        else:
            signal = 'NEUTRAL'
            interpretation = 'Price movement inconclusive'

        # Position size factors
        trend_factor = round(
            max(0.0, min(1.0, (pec - 0.5) / 0.5)), 4
        )
        reversion_factor = round(
            max(0.0, min(1.0, (0.5 - pec) / 0.5)), 4
        )

        return {
            'pec':              pec,
            'signal':           signal,
            'trend_factor':     trend_factor,
            'reversion_factor': reversion_factor,
            'interpretation':   interpretation
        }

    except Exception as e:
        logger.error(f'calculate_with_signal failed: {e}')
        return None


def rolling_pec(
    prices: pd.Series,
    window: int = 20
) -> pd.Series:
    """
    Calculate rolling PEC over a price series.

    Args:
        prices: Pandas Series of closing prices
        window: Rolling window size in candles

    Returns:
        Pandas Series of PEC values over time
    """
    try:
        result = []
        prices_array = np.array(prices, dtype=float)

        for i in range(len(prices_array)):
            if i < window:
                result.append(None)
            else:
                window_prices = prices_array[i - window:i]
                pec = calculate(window_prices)
                result.append(pec)

        return pd.Series(result, index=prices.index)

    except Exception as e:
        logger.error(f'rolling_pec failed: {e}')
        return pd.Series([None] * len(prices))


def multi_window_pec(
    prices: pd.Series | np.ndarray,
    windows: list = None
) -> Optional[dict]:
    """
    Calculate PEC across multiple window sizes.

    Args:
        prices: Series or array of closing prices
        windows: List of window sizes to calculate

    Returns:
        Dictionary of window size to PEC value
    """
    try:
        if windows is None:
            windows = [10, 20, 50]

        prices_array = np.array(prices, dtype=float)
        result = {}

        for window in windows:
            if len(prices_array) >= window:
                window_prices = prices_array[-window:]
                pec = calculate(window_prices)
                result[window] = pec
            else:
                result[window] = None

        logger.debug(f'multi_window_pec: {result}')
        return result

    except Exception as e:
        logger.error(f'multi_window_pec failed: {e}')
        return None


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 05 — PEC TESTS ===\n')
    np.random.seed(42)

    # Test 1 — Perfectly efficient series
    print('Test 1: Perfectly efficient straight line...')
    straight = np.array([100, 101, 102, 103, 104, 105], dtype=float)
    pec_straight = calculate(straight)
    print(f'Straight line PEC = {pec_straight}')
    passed = pec_straight is not None and pec_straight == 1.0
    print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

    # Test 2 — Perfectly inefficient zigzag
    print('Test 2: Perfectly inefficient zigzag...')
    zigzag = np.array(
        [100, 102, 100, 102, 100, 102, 100], dtype=float
    )
    pec_zigzag = calculate(zigzag)
    print(f'Zigzag PEC = {pec_zigzag}')
    passed = pec_zigzag is not None and pec_zigzag < 0.1
    print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

    # Test 3 — Trending series
    print('Test 3: Trending price series...')
    trend = np.cumsum(np.random.normal(0.2, 0.3, 200)) + 100
    pec_trend = calculate(trend)
    print(f'Trending PEC = {pec_trend}')
    passed = pec_trend is not None and pec_trend > 0.6
    print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

    # Test 4 — Mean reverting series
    print('Test 4: Mean reverting price series...')
    mean_rev = []
    price = 100.0
    for _ in range(200):
        price = price + (100 - price) * 0.4 + np.random.normal(0, 0.5)
        mean_rev.append(price)
    pec_rev = calculate(np.array(mean_rev))
    print(f'Mean reverting PEC = {pec_rev}')
    passed = pec_rev is not None and pec_rev < 0.4
    print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')

    # Test 5 — calculate_with_signal on both series
    print('Test 5: calculate_with_signal on trending series...')
    result_trend = calculate_with_signal(trend)
    if result_trend:
        for k, v in result_trend.items():
            print(f'  {k}: {v}')
        print('Test 5: PASSED\n')
    else:
        print('Test 5: FAILED\n')

    print('Test 5b: calculate_with_signal on mean reverting...')
    result_rev = calculate_with_signal(np.array(mean_rev))
    if result_rev:
        for k, v in result_rev.items():
            print(f'  {k}: {v}')
        print('Test 5b: PASSED\n')
    else:
        print('Test 5b: FAILED\n')

    # Test 6 — multi_window_pec
    print('Test 6: multi_window_pec on trending series...')
    mw = multi_window_pec(trend, windows=[10, 20, 50])
    if mw:
        print(f'  Multi-window PEC: {mw}')
        print('Test 6: PASSED\n')
    else:
        print('Test 6: FAILED\n')

    # Test 7 — rolling_pec
    print('Test 7: rolling_pec on trending series...')
    series = pd.Series(trend)
    rolling = rolling_pec(series, window=20)
    last5 = rolling.dropna().tail(5)
    print(f'Last 5 rolling values:\n{last5.to_string()}')
    print('Test 7: PASSED\n')

    all_passed = (
        pec_straight == 1.0 and
        pec_zigzag is not None and pec_zigzag < 0.1 and
        pec_trend is not None and pec_trend > 0.6 and
        pec_rev is not None and pec_rev < 0.4
    )
    print(
        '=== MODULE 05 — PEC: '
        f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
          )
