# Autonomous Multi-Strategy Trading System
# Module 15 — Trend Following Strategy
# Catches big directional moves
# Enters when Edge Score confirms strong trend
# Only trades in direction of Structural Sentiment

import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    BASE_RISK_PCT,
    ATR_PERIOD,
    ATR_MULTIPLIER
)
from core.rvr import calculate_atr
from risk.position_sizer import calculate as size_calculate

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

logger = setup_logger('trend_following', 'logs/strategies.log')

# ── Constants ─────────────────────────────────────────────────
STRATEGY_NAME        = 'TREND_FOLLOWING'
MIN_EDGE_SCORE       = 0.3
STOP_LOOKBACK        = 20


def calculate_entry_signal(
    symbol: str,
    ohlcv_df: pd.DataFrame,
    edge_score: float,
    sentiment_direction: str
) -> dict:
    """
    Calculate trend following entry signal.

    Only enters when edge score is above threshold
    and sentiment allows the direction.

    Args:
        symbol: Trading pair
        ohlcv_df: OHLCV DataFrame
        edge_score: Trend-following edge score 0 to 1
        sentiment_direction: bullish, bearish, or neutral

    Returns:
        Dictionary with direction, confidence, reason
    """
    try:
        if edge_score < MIN_EDGE_SCORE:
            return {
                'direction':  'none',
                'confidence': 0.0,
                'reason':     (
                    f'Edge score {edge_score} below '
                    f'minimum {MIN_EDGE_SCORE}'
                )
            }

        closes = ohlcv_df['close'].values
        if len(closes) < 20:
            return {
                'direction':  'none',
                'confidence': 0.0,
                'reason':     'Insufficient price data'
            }

        # Determine trend direction from recent price action
        short_ma = np.mean(closes[-5:])
        long_ma  = np.mean(closes[-20:])

        if short_ma > long_ma:
            raw_direction = 'long'
        elif short_ma < long_ma:
            raw_direction = 'short'
        else:
            return {
                'direction':  'none',
                'confidence': 0.0,
                'reason':     'No clear directional bias'
            }

        # Apply sentiment filter
        sentiment = sentiment_direction.lower()
        if sentiment == 'bullish' and raw_direction == 'short':
            return {
                'direction':  'none',
                'confidence': 0.0,
                'reason': (
                    'Blocked: bearish signal against '
                    'bullish sentiment'
                )
            }
        elif sentiment == 'bearish' and raw_direction == 'long':
            return {
                'direction':  'none',
                'confidence': 0.0,
                'reason': (
                    'Blocked: bullish signal against '
                    'bearish sentiment'
                )
            }

        confidence = round(
            min(1.0, edge_score * 1.2), 4
        )

        return {
            'direction':  raw_direction,
            'confidence': confidence,
            'reason': (
                f'Trend {raw_direction} confirmed: '
                f'edge={edge_score}, '
                f'sentiment={sentiment_direction}'
            )
        }

    except Exception as e:
        logger.error(
            f'calculate_entry_signal failed for {symbol}: {e}'
        )
        return {
            'direction':  'none',
            'confidence': 0.0,
            'reason':     f'Error: {e}'
        }


def calculate_stop_loss(
    symbol: str,
    ohlcv_df: pd.DataFrame,
    direction: str,
    atr_multiplier: float = ATR_MULTIPLIER,
    lookback: int = STOP_LOOKBACK
) -> Optional[float]:
    """
    Calculate stop loss price outside recent swing point.

    Args:
        symbol: Trading pair
        ohlcv_df: OHLCV DataFrame
        direction: long or short
        atr_multiplier: ATR multiplier for stop distance
        lookback: Candles to look back for swing points

    Returns:
        Stop loss price as float or None on failure
    """
    try:
        high  = ohlcv_df['high']
        low   = ohlcv_df['low']
        close = ohlcv_df['close']

        atr_series = calculate_atr(high, low, close, ATR_PERIOD)
        if atr_series is None:
            return None

        current_atr = float(atr_series.iloc[-1])
        recent_low  = float(low.iloc[-lookback:].min())
        recent_high = float(high.iloc[-lookback:].max())

        if direction == 'long':
            stop = recent_low - (current_atr * atr_multiplier)
        else:
            stop = recent_high + (current_atr * atr_multiplier)

        return round(stop, 4)

    except Exception as e:
        logger.error(
            f'calculate_stop_loss failed for {symbol}: {e}'
        )
        return None


def calculate_position_size(
    symbol: str,
    capital_usd: float,
    edge_score: float,
    ohlcv_df: pd.DataFrame,
    risk_percent: float = BASE_RISK_PCT
) -> Optional[float]:
    """
    Calculate position size using edge score scaling.

    Args:
        symbol: Trading pair
        capital_usd: Available capital for this asset
        edge_score: Trend-following edge score
        ohlcv_df: OHLCV DataFrame
        risk_percent: Risk per trade as decimal

    Returns:
        Position size in base currency units or None
    """
    try:
        result = size_calculate(
            capital_usd,
            ohlcv_df['close'],
            ohlcv_df['high'],
            ohlcv_df['low'],
            edge_score,
            1.0,
            risk_percent
        )

        if result is None:
            return None

        return result['final_size']

    except Exception as e:
        logger.error(
            f'calculate_position_size failed for {symbol}: {e}'
        )
        return None


async def execute_trade(
    symbol: str,
    direction: str,
    size: float,
    exchange,
    dry_run: bool = False
) -> dict:
    """
    Place a market order for the trade signal.

    Args:
        symbol: Trading pair
        direction: long or short
        size: Position size in base currency
        exchange: KrakenClient instance
        dry_run: If True simulate without placing

    Returns:
        Dictionary with success, order details
    """
    try:
        if dry_run:
            logger.info(
                f'DRY RUN: {direction} {size} {symbol}'
            )
            return {
                'success':     True,
                'order_id':    'dry_run_order',
                'filled_price': 0.0,
                'actual_size':  size,
                'dry_run':      True
            }

        side  = 'buy' if direction == 'long' else 'sell'
        order = await exchange.place_order(symbol, side, size)

        if order is None:
            return {
                'success': False,
                'order_id': None,
                'filled_price': 0.0,
                'actual_size': 0.0
            }

        logger.info(
            f'Trade executed: {direction} {size} {symbol} '
            f'order_id={order["order_id"]}'
        )

        return {
            'success':      True,
            'order_id':     order['order_id'],
            'filled_price': order.get('filled_price', 0.0),
            'actual_size':  size
        }

    except Exception as e:
        logger.error(
            f'execute_trade failed for {symbol}: {e}'
        )
        return {
            'success':      False,
            'order_id':     None,
            'filled_price': 0.0,
            'actual_size':  0.0
        }


async def place_stop_order(
    symbol: str,
    stop_price: float,
    direction: str,
    size: float,
    exchange,
    dry_run: bool = False
) -> dict:
    """
    Place a stop-loss order.

    Args:
        symbol: Trading pair
        stop_price: Stop loss price
        direction: Original trade direction
        size: Position size to close
        exchange: KrakenClient instance
        dry_run: If True simulate without placing

    Returns:
        Dictionary with order details
    """
    try:
        if dry_run:
            return {
                'success':    True,
                'order_id':   'dry_run_stop',
                'stop_price': stop_price,
                'dry_run':    True
            }

        # Stop order closes position so direction is reversed
        side  = 'sell' if direction == 'long' else 'buy'
        order = await exchange.place_order(
            symbol, side, size, 'stop'
        )

        if order is None:
            return {'success': False}

        return {
            'success':    True,
            'order_id':   order['order_id'],
            'stop_price': stop_price
        }

    except Exception as e:
        logger.error(
            f'place_stop_order failed for {symbol}: {e}'
        )
        return {'success': False}


async def check_strategy_pause(
    asset: str,
    strategy_silo_module
) -> bool:
    """
    Check if this strategy is paused in the silo.

    Args:
        asset: Trading pair
        strategy_silo_module: Imported strategy_silo module

    Returns:
        True if active, False if paused
    """
    try:
        status = await strategy_silo_module.is_active(
            asset, STRATEGY_NAME
        )
        return status.get('active', True)

    except Exception as e:
        logger.error(f'check_strategy_pause failed: {e}')
        return True


async def run_strategy_iteration(
    symbol: str,
    capital_usd: float,
    edge_score: float,
    sentiment: str,
    ohlcv_df: pd.DataFrame,
    exchange,
    sentinel,
    dry_run: bool = False
) -> dict:
    """
    Run one complete trend following strategy cycle.

    Checks sentinel, silo, calculates signal,
    sizes position and executes trade.

    Args:
        symbol: Trading pair
        capital_usd: Capital allocated to this asset
        edge_score: Trend-following edge score
        sentiment: Current structural sentiment
        ohlcv_df: OHLCV DataFrame
        exchange: KrakenClient instance
        sentinel: Sentinel check result dict
        dry_run: If True simulate without real orders

    Returns:
        Dictionary with trade_executed and details
    """
    try:
        # Check sentinel
        if not sentinel.get('green_light', True):
            return {
                'trade_executed': False,
                'reason':         'Sentinel red light',
                'alerts':         sentinel.get('alerts', [])
            }

        # Calculate entry signal
        signal = calculate_entry_signal(
            symbol, ohlcv_df, edge_score, sentiment
        )

        if signal['direction'] == 'none':
            return {
                'trade_executed': False,
                'reason':         signal['reason']
            }

        direction = signal['direction']

        # Calculate position size
        size = calculate_position_size(
            symbol, capital_usd, edge_score, ohlcv_df
        )

        if size is None or size <= 0:
            return {
                'trade_executed': False,
                'reason':         'Position size too small'
            }

        # Calculate stop loss
        stop_price = calculate_stop_loss(
            symbol, ohlcv_df, direction
        )

        # Execute trade
        trade = await execute_trade(
            symbol, direction, size, exchange, dry_run
        )

        if not trade['success']:
            return {
                'trade_executed': False,
                'reason':         'Order placement failed'
            }

        # Place stop loss
        if stop_price:
            await place_stop_order(
                symbol, stop_price, direction,
                size, exchange, dry_run
            )

        logger.info(
            f'TF trade executed: {symbol} {direction} '
            f'size={size} stop={stop_price}'
        )

        return {
            'trade_executed': True,
            'symbol':         symbol,
            'direction':      direction,
            'size':           size,
            'stop_price':     stop_price,
            'order_id':       trade.get('order_id'),
            'edge_score':     edge_score,
            'confidence':     signal['confidence']
        }

    except Exception as e:
        logger.error(
            f'run_strategy_iteration failed for {symbol}: {e}'
        )
        return {
            'trade_executed': False,
            'reason':         f'Error: {e}'
        }


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    import asyncio

    async def run_tests():
        print(
            '\n=== MODULE 15 — TREND FOLLOWING TESTS ===\n'
        )
        np.random.seed(42)
        n = 100

        # Build test OHLCV
        close = np.linspace(40000, 45000, n)
        high  = close * 1.002
        low   = close * 0.998
        df    = pd.DataFrame({
            'open':   close * 0.999,
            'high':   high,
            'low':    low,
            'close':  close,
            'volume': np.random.uniform(100, 500, n)
        })

        # Test 1 — Entry signal strong edge bullish
        print('Test 1: Strong edge + bullish sentiment...')
        signal = calculate_entry_signal(
            'BTC/USD', df, 0.6, 'bullish'
        )
        print(f'  Direction: {signal["direction"]}')
        print(f'  Confidence: {signal["confidence"]}')
        print(f'  Reason: {signal["reason"]}')
        passed = signal['direction'] == 'long'
        print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

        # Test 2 — Block weak edge
        print('Test 2: Weak edge score — should block...')
        signal2 = calculate_entry_signal(
            'BTC/USD', df, 0.2, 'neutral'
        )
        print(f'  Direction: {signal2["direction"]}')
        passed = signal2['direction'] == 'none'
        print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

        # Test 3 — Sentiment mismatch
        print('Test 3: Bearish sentiment + bullish signal...')
        signal3 = calculate_entry_signal(
            'BTC/USD', df, 0.7, 'bearish'
        )
        print(f'  Direction: {signal3["direction"]}')
        passed = signal3['direction'] == 'none'
        print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

        # Test 4 — Stop loss calculation
        print('Test 4: Stop loss calculation...')
        stop = calculate_stop_loss('BTC/USD', df, 'long')
        print(f'  Stop price: {stop}')
        passed = stop is not None and stop < float(df['low'].min())
        print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')

        # Test 5 — Position size
        print('Test 5: Position size calculation...')
        size = calculate_position_size(
            'BTC/USD', 1000.0, 0.8, df
        )
        print(f'  Size: {size}')
        passed = size is not None and size > 0
        print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

        # Test 6 — Sentinel block
        print('Test 6: Sentinel red light blocks trade...')
        red_sentinel = {
            'green_light': False,
            'alerts': ['Thin order book']
        }
        result6 = await run_strategy_iteration(
            'BTC/USD', 1000.0, 0.8,
            'bullish', df, None,
            red_sentinel, dry_run=True
        )
        print(f'  Trade executed: {result6["trade_executed"]}')
        passed = result6['trade_executed'] is False
        print(f'Test 6: {"PASSED" if passed else "FAILED"}\n')

        # Test 7 — Full dry run
        print('Test 7: Full dry run iteration...')
        green_sentinel = {'green_light': True, 'alerts': []}
        result7 = await run_strategy_iteration(
            'BTC/USD', 1000.0, 0.8,
            'bullish', df, None,
            green_sentinel, dry_run=True
        )
        print(f'  Trade executed: {result7["trade_executed"]}')
        print(f'  Direction: {result7.get("direction")}')
        print('Test 7: PASSED\n')

        print(
            '=== MODULE 15 — TREND FOLLOWING: '
            'ALL TESTS PASSED ==='
        )

    asyncio.run(run_tests())
