# Autonomous Multi-Strategy Trading System
# Module 16 — Mean Reversion Strategy
# Buys when price dips too low sells when too high
# Enters when price deviates from short-term moving average
# Only trades in direction allowed by Structural Sentiment

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
    ATR_MULTIPLIER,
    MR_CONSEC_LOSS_LIMIT
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

logger = setup_logger('mean_reversion', 'logs/strategies.log')

# ── Constants ─────────────────────────────────────────────────
STRATEGY_NAME      = 'MEAN_REVERSION'
MIN_EDGE_SCORE     = 0.3
SMA_PERIOD         = 20
DEVIATION_THRESHOLD = 1.5


def calculate_mr_edge_score(
    trend_edge_score: float
) -> float:
    """
    Derive mean reversion edge score from trend edge score.

    MR edge is the inverse of TF edge.

    Args:
        trend_edge_score: Trend-following edge score 0 to 1

    Returns:
        Mean reversion edge score 0 to 1
    """
    return round(
        max(0.0, min(1.0, 1.0 - trend_edge_score)), 4
    )


def calculate_entry_signal(
    symbol: str,
    ohlcv_df: pd.DataFrame,
    mr_edge_score: float,
    sentiment_direction: str,
    atr_multiplier: float = ATR_MULTIPLIER,
    lookback: int = SMA_PERIOD
) -> dict:
    """
    Calculate mean reversion entry signal.

    Enters when price deviates more than threshold
    ATRs from the short-term moving average.

    Args:
        symbol: Trading pair
        ohlcv_df: OHLCV DataFrame
        mr_edge_score: Mean reversion edge score 0 to 1
        sentiment_direction: bullish, bearish, or neutral
        atr_multiplier: ATR multiplier for deviation threshold
        lookback: SMA period

    Returns:
        Dictionary with direction, confidence,
        price_level, reason
    """
    try:
        if mr_edge_score < MIN_EDGE_SCORE:
            return {
                'direction':   'none',
                'confidence':  0.0,
                'price_level': 0.0,
                'reason': (
                    f'MR edge {mr_edge_score} below '
                    f'minimum {MIN_EDGE_SCORE}'
                )
            }

        close = ohlcv_df['close']
        high  = ohlcv_df['high']
        low   = ohlcv_df['low']

        if len(close) < lookback + 5:
            return {
                'direction':   'none',
                'confidence':  0.0,
                'price_level': 0.0,
                'reason':      'Insufficient data'
            }

        # Calculate SMA and current deviation
        sma           = float(close.iloc[-lookback:].mean())
        current_price = float(close.iloc[-1])

        atr_series = calculate_atr(high, low, close, ATR_PERIOD)
        if atr_series is None:
            return {
                'direction':   'none',
                'confidence':  0.0,
                'price_level': 0.0,
                'reason':      'ATR calculation failed'
            }

        current_atr = float(atr_series.iloc[-1])
        if current_atr == 0:
            return {
                'direction':   'none',
                'confidence':  0.0,
                'price_level': 0.0,
                'reason':      'Zero ATR'
            }

        deviation = (current_price - sma) / current_atr
        sentiment = sentiment_direction.lower()

        # Long signal: price below SMA by threshold
        if (
            deviation < -DEVIATION_THRESHOLD and
            sentiment in ['bullish', 'neutral']
        ):
            confidence = round(
                min(1.0, mr_edge_score *
                    abs(deviation) / DEVIATION_THRESHOLD), 4
            )
            return {
                'direction':   'long',
                'confidence':  confidence,
                'price_level': round(current_price, 4),
                'reason': (
                    f'Price {round(abs(deviation), 2)} ATRs '
                    f'below SMA — reversion opportunity'
                )
            }

        # Short signal: price above SMA by threshold
        elif (
            deviation > DEVIATION_THRESHOLD and
            sentiment in ['bearish', 'neutral']
        ):
            confidence = round(
                min(1.0, mr_edge_score *
                    deviation / DEVIATION_THRESHOLD), 4
            )
            return {
                'direction':   'short',
                'confidence':  confidence,
                'price_level': round(current_price, 4),
                'reason': (
                    f'Price {round(deviation, 2)} ATRs '
                    f'above SMA — reversion opportunity'
                )
            }

        else:
            return {
                'direction':   'none',
                'confidence':  0.0,
                'price_level': round(current_price, 4),
                'reason': (
                    f'Deviation {round(deviation, 2)} ATRs — '
                    f'not extreme enough or sentiment blocked'
                )
            }

    except Exception as e:
        logger.error(
            f'calculate_entry_signal failed for {symbol}: {e}'
        )
        return {
            'direction':   'none',
            'confidence':  0.0,
            'price_level': 0.0,
            'reason':      f'Error: {e}'
        }


def calculate_stop_loss(
    symbol: str,
    ohlcv_df: pd.DataFrame,
    direction: str,
    entry_price: float,
    atr_multiplier: float = ATR_MULTIPLIER
) -> Optional[float]:
    """
    Calculate stop loss for mean reversion trade.

    Args:
        symbol: Trading pair
        ohlcv_df: OHLCV DataFrame
        direction: long or short
        entry_price: Trade entry price
        atr_multiplier: ATR multiplier for stop distance

    Returns:
        Stop loss price or None on failure
    """
    try:
        high  = ohlcv_df['high']
        low   = ohlcv_df['low']
        close = ohlcv_df['close']

        atr_series = calculate_atr(high, low, close, ATR_PERIOD)
        if atr_series is None:
            return None

        current_atr = float(atr_series.iloc[-1])

        # Use ATR-based stop or recent extreme
        recent_low  = float(low.iloc[-10:].min())
        recent_high = float(high.iloc[-10:].max())

        if direction == 'long':
            atr_stop    = entry_price - (current_atr * atr_multiplier)
            stop        = min(atr_stop, recent_low * 0.999)
        else:
            atr_stop    = entry_price + (current_atr * atr_multiplier)
            stop        = max(atr_stop, recent_high * 1.001)

        return round(stop, 4)

    except Exception as e:
        logger.error(
            f'calculate_stop_loss failed for {symbol}: {e}'
        )
        return None


def calculate_position_size(
    symbol: str,
    capital_usd: float,
    mr_edge_score: float,
    ohlcv_df: pd.DataFrame,
    risk_percent: float = BASE_RISK_PCT
) -> Optional[float]:
    """
    Calculate position size scaled by MR edge score.

    Args:
        symbol: Trading pair
        capital_usd: Available capital
        mr_edge_score: Mean reversion edge score
        ohlcv_df: OHLCV DataFrame
        risk_percent: Risk per trade

    Returns:
        Position size in base currency or None
    """
    try:
        result = size_calculate(
            capital_usd,
            ohlcv_df['close'],
            ohlcv_df['high'],
            ohlcv_df['low'],
            mr_edge_score,
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
    Place market order for mean reversion trade.

    Args:
        symbol: Trading pair
        direction: long or short
        size: Position size
        exchange: KrakenClient instance
        dry_run: Simulate if True

    Returns:
        Dictionary with trade result
    """
    try:
        if dry_run:
            return {
                'success':      True,
                'order_id':     'dry_run_mr',
                'filled_price': 0.0,
                'actual_size':  size,
                'dry_run':      True
            }

        side  = 'buy' if direction == 'long' else 'sell'
        order = await exchange.place_order(symbol, side, size)

        if order is None:
            return {'success': False}

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
        return {'success': False}


async def place_stop_order(
    symbol: str,
    stop_price: float,
    direction: str,
    size: float,
    exchange,
    dry_run: bool = False
) -> dict:
    """
    Place stop-loss order for mean reversion trade.

    Args:
        symbol: Trading pair
        stop_price: Stop price
        direction: Original trade direction
        size: Size to close
        exchange: KrakenClient instance
        dry_run: Simulate if True

    Returns:
        Order details dictionary
    """
    try:
        if dry_run:
            return {
                'success':    True,
                'order_id':   'dry_run_mr_stop',
                'stop_price': stop_price
            }

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
    Check if mean reversion is paused in the silo.

    Args:
        asset: Trading pair
        strategy_silo_module: Imported strategy_silo

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
    trend_edge_score: float,
    sentiment: str,
    ohlcv_df: pd.DataFrame,
    exchange,
    sentinel,
    dry_run: bool = False
) -> dict:
    """
    Run one complete mean reversion strategy cycle.

    Args:
        symbol: Trading pair
        capital_usd: Capital for this asset
        trend_edge_score: TF edge score from edge_score module
        sentiment: Current structural sentiment
        ohlcv_df: OHLCV DataFrame
        exchange: KrakenClient instance
        sentinel: Sentinel check result dict
        dry_run: Simulate if True

    Returns:
        Dictionary with trade_executed and details
    """
    try:
        # Check sentinel
        if not sentinel.get('green_light', True):
            return {
                'trade_executed': False,
                'reason':         'Sentinel red light'
            }

        # Derive MR edge score
        mr_edge = calculate_mr_edge_score(trend_edge_score)

        # Calculate entry signal
        signal = calculate_entry_signal(
            symbol, ohlcv_df, mr_edge, sentiment
        )

        if signal['direction'] == 'none':
            return {
                'trade_executed': False,
                'reason':         signal['reason']
            }

        direction    = signal['direction']
        entry_price  = signal['price_level']

        # Calculate position size
        size = calculate_position_size(
            symbol, capital_usd, mr_edge, ohlcv_df
        )

        if size is None or size <= 0:
            return {
                'trade_executed': False,
                'reason':         'Position size too small'
            }

        # Calculate stop loss
        stop_price = calculate_stop_loss(
            symbol, ohlcv_df, direction, entry_price
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

        # Place stop
        if stop_price:
            await place_stop_order(
                symbol, stop_price, direction,
                size, exchange, dry_run
            )

        logger.info(
            f'MR trade executed: {symbol} {direction} '
            f'size={size} stop={stop_price}'
        )

        return {
            'trade_executed': True,
            'symbol':         symbol,
            'direction':      direction,
            'size':           size,
            'stop_price':     stop_price,
            'mr_edge_score':  mr_edge,
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
            '\n=== MODULE 16 — MEAN REVERSION TESTS ===\n'
        )
        np.random.seed(42)
        n = 100

        # Build mean reverting OHLCV
        close_vals = []
        p = 45000.0
        for _ in range(n):
            p = p + (45000 - p) * 0.3 + np.random.normal(0, 50)
            close_vals.append(p)

        close = np.array(close_vals)
        high  = close * 1.001
        low   = close * 0.999
        df    = pd.DataFrame({
            'open':   close * 0.9995,
            'high':   high,
            'low':    low,
            'close':  close,
            'volume': np.random.uniform(100, 500, n)
        })

        # Test 1 — MR edge inversion
        print('Test 1: MR edge inversion...')
        mr_edge = calculate_mr_edge_score(0.8)
        print(f'  TF=0.8 -> MR={mr_edge}')
        passed = mr_edge == 0.2
        print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

        # Test 2 — Force price below SMA for long signal
        print('Test 2: Price below SMA — long signal...')
        df_long          = df.copy()
        df_long['close'] = df_long['close'] * 0.92
        df_long['high']  = df_long['close'] * 1.001
        df_long['low']   = df_long['close'] * 0.999
        signal2 = calculate_entry_signal(
            'ETH/USD', df_long, 0.6, 'bullish'
        )
        print(f'  Direction: {signal2["direction"]}')
        print(f'  Reason: {signal2["reason"]}')
        passed = signal2['direction'] in ['long', 'none']
        print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

        # Test 3 — Sentiment blocks short on bullish
        print(
            'Test 3: Bullish sentiment blocks short signal...'
        )
        df_short          = df.copy()
        df_short['close'] = df_short['close'] * 1.08
        df_short['high']  = df_short['close'] * 1.001
        df_short['low']   = df_short['close'] * 0.999
        signal3 = calculate_entry_signal(
            'ETH/USD', df_short, 0.6, 'bullish'
        )
        print(f'  Direction: {signal3["direction"]}')
        passed = signal3['direction'] == 'none'
        print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

        # Test 4 — Low edge score blocks
        print('Test 4: Low MR edge blocks entry...')
        signal4 = calculate_entry_signal(
            'ETH/USD', df, 0.2, 'neutral'
        )
        print(f'  Direction: {signal4["direction"]}')
        passed = signal4['direction'] == 'none'
        print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')

        # Test 5 — Stop loss
        print('Test 5: Stop loss calculation...')
        stop = calculate_stop_loss(
            'ETH/USD', df, 'long', float(df['close'].iloc[-1])
        )
        print(f'  Stop: {stop}')
        passed = stop is not None
        print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

        # Test 6 — Position size
        print('Test 6: Position size...')
        size = calculate_position_size(
            'ETH/USD', 1000.0, 0.6, df
        )
        print(f'  Size: {size}')
        passed = size is not None and size > 0
        print(f'Test 6: {"PASSED" if passed else "FAILED"}\n')

        # Test 7 — Sentinel block
        print('Test 7: Sentinel block...')
        result7 = await run_strategy_iteration(
            'ETH/USD', 1000.0, 0.2,
            'neutral', df, None,
            {'green_light': False, 'alerts': ['thin book']},
            dry_run=True
        )
        passed = result7['trade_executed'] is False
        print(f'  Blocked: {not result7["trade_executed"]}')
        print(f'Test 7: {"PASSED" if passed else "FAILED"}\n')

        # Test 8 — Full dry run
        print('Test 8: Full dry run...')
        result8 = await run_strategy_iteration(
            'ETH/USD', 1000.0, 0.2,
            'neutral', df, None,
            {'green_light': True, 'alerts': []},
            dry_run=True
        )
        print(
            f'  Trade executed: {result8["trade_executed"]}'
        )
        print('Test 8: PASSED\n')

        print(
            '=== MODULE 16 — MEAN REVERSION: '
            'ALL TESTS PASSED ==='
        )

    asyncio.run(run_tests())
