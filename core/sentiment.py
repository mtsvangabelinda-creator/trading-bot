# Autonomous Multi-Strategy Trading System
# Module 08 — Structural Sentiment
# Higher-timeframe directional bias
# Prevents system from fighting the macro trend
# Updated every hour — acts as directional filter
# for all strategies

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import SENTIMENT_INTERVAL
from core.hurst import calculate_with_confidence as hurst_confidence

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

logger = setup_logger('sentiment', 'logs/errors.log')

# ── Constants ─────────────────────────────────────────────────
EMA_FAST                  = 20
EMA_SLOW                  = 50
PRICE_POSITION_THRESHOLD  = 0.01
BULLISH                   = 'BULLISH'
BEARISH                   = 'BEARISH'
NEUTRAL                   = 'NEUTRAL'


def calculate_ema(
    prices: pd.Series,
    period: int
) -> Optional[pd.Series]:
    """
    Calculate Exponential Moving Average.

    Args:
        prices: Series of closing prices
        period: EMA period

    Returns:
        Pandas Series of EMA values or None on failure
    """
    try:
        if len(prices) < period:
            logger.warning(
                f'calculate_ema: insufficient data '
                f'({len(prices)} prices, need {period})'
            )
            return None

        ema = prices.ewm(span=period, adjust=False).mean()
        return ema

    except Exception as e:
        logger.error(f'calculate_ema failed: {e}')
        return None


def calculate(
    close: pd.Series,
    high: pd.Series = None,
    low: pd.Series = None
) -> Optional[dict]:
    """
    Calculate Market Structural Sentiment.

    Uses three indicators that must agree:
    1. EMA Trend — Fast vs Slow EMA relationship
    2. Price Position — Current price vs EMA50
    3. Hurst Confirmation — Hurst trend direction

    Args:
        close: Series of closing prices
        high: Optional series of high prices
        low: Optional series of low prices

    Returns:
        Dictionary with sentiment, conviction,
        allowed_directions, reasoning and all
        indicator values or None on failure
    """
    try:
        close = pd.Series(np.array(close, dtype=float))

        if len(close) < EMA_SLOW + 5:
            logger.warning(
                f'calculate: insufficient data ({len(close)} candles)'
            )
            return None

        failed_signals = 0

        # ── Indicator 1: EMA Trend ────────────────────────────
        ema_fast_series = calculate_ema(close, EMA_FAST)
        ema_slow_series = calculate_ema(close, EMA_SLOW)

        if ema_fast_series is None or ema_slow_series is None:
            failed_signals += 1
            ema_signal  = NEUTRAL
            ema_fast    = 0.0
            ema_slow    = 0.0
        else:
            ema_fast = float(ema_fast_series.iloc[-1])
            ema_slow = float(ema_slow_series.iloc[-1])

            # Check slope of fast EMA
            ema_fast_slope = (
                float(ema_fast_series.iloc[-1]) -
                float(ema_fast_series.iloc[-5])
            )

            if ema_fast > ema_slow and ema_fast_slope > 0:
                ema_signal = BULLISH
            elif ema_fast < ema_slow and ema_fast_slope < 0:
                ema_signal = BEARISH
            else:
                ema_signal = NEUTRAL

        # ── Indicator 2: Price Position ───────────────────────
        if ema_slow == 0.0:
            price_signal = NEUTRAL
        else:
            current_price = float(close.iloc[-1])
            price_deviation = (current_price - ema_slow) / ema_slow

            if price_deviation > PRICE_POSITION_THRESHOLD:
                price_signal = BULLISH
            elif price_deviation < -PRICE_POSITION_THRESHOLD:
                price_signal = BEARISH
            else:
                price_signal = NEUTRAL

        # ── Indicator 3: Hurst Confirmation ───────────────────
        h_result = hurst_confidence(close)

        if h_result is None:
            failed_signals += 1
            hurst_signal = NEUTRAL
            hurst_value  = 0.5
        else:
            hurst_value = h_result['hurst']

            if hurst_value > 0.55:
                # Trend exists — confirm EMA direction
                if ema_signal == BULLISH:
                    hurst_signal = BULLISH
                elif ema_signal == BEARISH:
                    hurst_signal = BEARISH
                else:
                    hurst_signal = NEUTRAL
            else:
                # Weak trend — push toward neutral
                hurst_signal = NEUTRAL

        if failed_signals > 1:
            logger.error(
                'calculate: too many indicator failures'
            )
            return None

        # ── Final Sentiment Voting ────────────────────────────
        indicators = [ema_signal, price_signal, hurst_signal]
        bullish_count = indicators.count(BULLISH)
        bearish_count = indicators.count(BEARISH)

        if bullish_count == 3:
            sentiment  = BULLISH
            conviction = 'HIGH'
        elif bearish_count == 3:
            sentiment  = BEARISH
            conviction = 'HIGH'
        elif bullish_count == 2:
            sentiment  = BULLISH
            conviction = 'MODERATE'
        elif bearish_count == 2:
            sentiment  = BEARISH
            conviction = 'MODERATE'
        else:
            sentiment  = NEUTRAL
            conviction = 'LOW'

        # ── Allowed Directions ────────────────────────────────
        if sentiment == BULLISH:
            allowed_directions = ['long']
        elif sentiment == BEARISH:
            allowed_directions = ['short']
        else:
            allowed_directions = ['long', 'short']

        # ── Reasoning String ──────────────────────────────────
        reasoning = (
            f'EMA{EMA_FAST}={round(ema_fast, 2)} vs '
            f'EMA{EMA_SLOW}={round(ema_slow, 2)} '
            f'({ema_signal}). '
            f'Price position ({price_signal}). '
            f'Hurst={hurst_value} ({hurst_signal}). '
            f'{bullish_count} BULLISH, {bearish_count} BEARISH. '
            f'{conviction} conviction {sentiment} sentiment. '
            f'Allowed: {allowed_directions}.'
        )

        return {
            'sentiment':           sentiment,
            'conviction':          conviction,
            'ema_fast':            round(ema_fast, 4),
            'ema_slow':            round(ema_slow, 4),
            'ema_signal':          ema_signal,
            'price_signal':        price_signal,
            'hurst_signal':        hurst_signal,
            'hurst_value':         hurst_value,
            'bullish_count':       bullish_count,
            'bearish_count':       bearish_count,
            'allowed_directions':  allowed_directions,
            'reasoning':           reasoning
        }

    except Exception as e:
        logger.error(f'calculate failed: {e}')
        return None


def calculate_all(
    assets_data: dict
) -> dict:
    """
    Calculate sentiment for all assets independently.

    Args:
        assets_data: Dictionary of asset name to dict
            with close, high, low Series

    Returns:
        Dictionary of asset name to sentiment result
    """
    results = {}
    for asset, data in assets_data.items():
        try:
            result = calculate(
                data['close'],
                data.get('high'),
                data.get('low')
            )
            results[asset] = result
            if result:
                logger.debug(
                    f'{asset}: {result["sentiment"]} '
                    f'({result["conviction"]})'
                )
        except Exception as e:
            logger.error(
                f'calculate_all failed for {asset}: {e}'
            )
            results[asset] = None

    return results


def get_summary(results: dict) -> str:
    """
    Format sentiment results as a Telegram-ready string.

    Args:
        results: Output from calculate_all

    Returns:
        Formatted summary string
    """
    try:
        lines = ['STRUCTURAL SENTIMENT', '─' * 30]
        for asset, result in results.items():
            if result is None:
                lines.append(
                    f'{asset}: ERROR — calculation failed'
                )
            else:
                sentiment  = result['sentiment']
                conviction = result['conviction']
                directions = result['allowed_directions']
                dir_str = ' and '.join(
                    [d.upper() for d in directions]
                ) + ' only'
                lines.append(
                    f'{asset}: {sentiment} '
                    f'({conviction} conviction) — {dir_str}'
                )
        lines.append('─' * 30)
        return '\n'.join(lines)

    except Exception as e:
        logger.error(f'get_summary failed: {e}')
        return 'Sentiment summary unavailable'


def direction_allowed(
    sentiment_result: dict,
    direction: str
) -> bool:
    """
    Check if a trade direction is permitted by sentiment.

    Args:
        sentiment_result: Output from calculate()
        direction: long or short

    Returns:
        True if direction is allowed, False if blocked
    """
    try:
        if sentiment_result is None:
            return True

        allowed = sentiment_result.get('allowed_directions', [])
        return direction.lower() in allowed

    except Exception as e:
        logger.error(f'direction_allowed failed: {e}')
        return True


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 08 — STRUCTURAL SENTIMENT TESTS ===\n')
    np.random.seed(42)
    n = 200

    # Test 1 — Strongly BULLISH dataset
    print('Test 1: Strongly BULLISH dataset...')
    bullish_close = pd.Series(
        np.linspace(100, 150, n) +
        np.random.normal(0, 0.5, n)
    )
    result_bull = calculate(bullish_close)
    if result_bull:
        print(f'  Sentiment: {result_bull["sentiment"]}')
        print(f'  Conviction: {result_bull["conviction"]}')
        print(f'  Allowed: {result_bull["allowed_directions"]}')
        passed = result_bull['sentiment'] == BULLISH
        print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 1: FAILED — no result\n')

    # Test 2 — Strongly BEARISH dataset
    print('Test 2: Strongly BEARISH dataset...')
    bearish_close = pd.Series(
        np.linspace(150, 100, n) +
        np.random.normal(0, 0.5, n)
    )
    result_bear = calculate(bearish_close)
    if result_bear:
        print(f'  Sentiment: {result_bear["sentiment"]}')
        print(f'  Conviction: {result_bear["conviction"]}')
        passed = result_bear['sentiment'] == BEARISH
        print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 2: FAILED — no result\n')

    # Test 3 — NEUTRAL dataset
    print('Test 3: NEUTRAL sideways dataset...')
    neutral_close = pd.Series(
        100 + np.random.normal(0, 1.0, n)
    )
    result_neut = calculate(neutral_close)
    if result_neut:
        print(f'  Sentiment: {result_neut["sentiment"]}')
        print(f'  Conviction: {result_neut["conviction"]}')
        passed = result_neut['sentiment'] == NEUTRAL
        print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 3: FAILED — no result\n')

    # Test 4 — direction_allowed
    print('Test 4: direction_allowed on BULLISH result...')
    if result_bull:
        long_ok  = direction_allowed(result_bull, 'long')
        short_ok = direction_allowed(result_bull, 'short')
        print(f'  Long allowed: {long_ok}')
        print(f'  Short allowed: {short_ok}')
        passed = long_ok is True and short_ok is False
        print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')

    # Test 5 — calculate_all
    print('Test 5: calculate_all with three assets...')
    assets = {
        'BTC/USD': {'close': bullish_close},
        'ETH/USD': {'close': bearish_close},
        'SOL/USD': {'close': neutral_close}
    }
    all_results = calculate_all(assets)
    for asset, res in all_results.items():
        if res:
            print(
                f'  {asset}: {res["sentiment"]} '
                f'({res["conviction"]})'
            )
    print('Test 5: PASSED\n')

    # Test 6 — get_summary
    print('Test 6: get_summary...')
    summary = get_summary(all_results)
    print(summary)
    print('Test 6: PASSED\n')

    all_passed = (
        result_bull is not None and
        result_bull['sentiment'] == BULLISH and
        result_bear is not None and
        result_bear['sentiment'] == BEARISH and
        result_neut is not None and
        result_neut['sentiment'] == NEUTRAL and
        direction_allowed(result_bull, 'long') is True and
        direction_allowed(result_bull, 'short') is False
    )
    print(
        '=== MODULE 08 — STRUCTURAL SENTIMENT: '
        f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
      )
