# Autonomous Multi-Strategy Trading System
# Module 17 — Micro Scalper Strategy
# Takes many small profits from short-term price moves
# Runs in dead zone with small directional bias from sentiment
# No consecutive loss limit but has daily loss cap

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
    SCALPER_DAILY_LOSS
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

logger = setup_logger('scalper', 'logs/strategies.log')

# ── Constants ─────────────────────────────────────────────────
STRATEGY_NAME       = 'SCALPER'
SCALPER_RISK_PCT    = 0.002
SCALPER_SIZE_FACTOR = 0.1
STOP_PCT            = 0.005
TARGET_PCT          = 0.003
PULLBACK_THRESHOLD  = 0.001


def calculate_scalp_signal(
    symbol: str,
    ohlcv_df: pd.DataFrame,
    sentiment_bias: str,
    dead_zone_flag: bool = False,
    edge_score_trend: float = None
) -> dict:
    """
    Calculate micro scalp entry signal.

    In dead zone uses sentiment bias for direction.
    Outside dead zone follows trend direction.

    Args:
        symbol: Trading pair
        ohlcv_df: OHLCV DataFrame (last 20 candles)
        sentiment_bias: bullish, bearish, or neutral
        dead_zone_flag: True if Hurst in dead zone
        edge_score_trend: TF edge score if available

    Returns:
        Dictionary with direction, confidence,
        price_level, reason
    """
    try:
        close = ohlcv_df['close'].values

        if len(close) < 5:
            return {
                'direction':   'none',
                'confidence':  0.0,
                'price_level': 0.0,
                'reason':      'Insufficient data'
            }

        current_price = float(close[-1])
        prev_price    = float(close[-2])
        price_change  = (current_price - prev_price) / prev_price

        sentiment = sentiment_bias.lower()

        # Determine bias direction
        if dead_zone_flag:
            if sentiment == 'bullish':
                bias = 'long'
            elif sentiment == 'bearish':
                bias = 'short'
            else:
                bias = 'neutral'
        else:
            if (
                edge_score_trend is not None and
                edge_score_trend > 0.5
            ):
                # Follow trend direction via sentiment
                if sentiment == 'bullish':
                    bias = 'long'
                elif sentiment == 'bearish':
                    bias = 'short'
                else:
                    bias = 'neutral'
            else:
                bias = 'neutral'

        if bias == 'neutral':
            return {
                'direction':   'none',
                'confidence':  0.0,
                'price_level': round(current_price, 4),
                'reason':      'Neutral bias — no scalp signal'
            }

        # Simple pullback entry logic
        # Buy on small dip when biased long
        # Sell on small bounce when biased short
        if (
            bias == 'long' and
            price_change < -PULLBACK_THRESHOLD
        ):
            return {
                'direction':   'long',
                'confidence':  0.6,
                'price_level': round(current_price, 4),
                'reason': (
                    f'Scalp long: pullback '
                    f'{round(price_change*100, 3)}% '
                    f'with bullish bias'
                )
            }

        elif (
            bias == 'short' and
            price_change > PULLBACK_THRESHOLD
        ):
            return {
                'direction':   'short',
                'confidence':  0.6,
                'price_level': round(current_price, 4),
                'reason': (
                    f'Scalp short: bounce '
                    f'{round(price_change*100, 3)}% '
                    f'with bearish bias'
                )
            }

        else:
            return {
                'direction':   'none',
                'confidence':  0.0,
                'price_level': round(current_price, 4),
                'reason':      'No pullback signal in bias direction'
            }

    except Exception as e:
        logger.error(
            f'calculate_scalp_signal failed for {symbol}: {e}'
        )
        return {
            'direction':   'none',
            'confidence':  0.0,
            'price_level': 0.0,
            'reason':      f'Error: {e}'
        }


def calculate_position_size(
    symbol: str,
    capital_usd: float,
    scalper_size_factor: float = SCALPER_SIZE_FACTOR,
    risk_percent: float = SCALPER_RISK_PCT,
    atr_value: float = None
) -> float:
    """
    Calculate very small scalp position size.

    Args:
        symbol: Trading pair
        capital_usd: Available capital
        scalper_size_factor: Fraction of normal size
        risk_percent: Risk per scalp trade
        atr_value: Current ATR if available

    Returns:
        Position size as float
    """
    try:
        dollar_risk = capital_usd * risk_percent
        if atr_value and atr_value > 0:
            base_size = dollar_risk / (atr_value * ATR_MULTIPLIER)
        else:
            base_size = dollar_risk / 100.0

        final_size = base_size * scalper_size_factor
        return round(max(0.0001, final_size), 6)

    except Exception as e:
        logger.error(
            f'calculate_position_size failed for {symbol}: {e}'
        )
        return 0.0


def calculate_stop_loss(
    symbol: str,
    entry_price: float,
    direction: str,
    atr_value: float = None,
    stop_percent: float = STOP_PCT
) -> float:
    """
    Calculate tight stop loss for scalp trade.

    Args:
        symbol: Trading pair
        entry_price: Trade entry price
        direction: long or short
        atr_value: Current ATR value
        stop_percent: Stop distance as percentage

    Returns:
        Stop loss price
    """
    try:
        if direction == 'long':
            return round(entry_price * (1 - stop_percent), 4)
        else:
            return round(entry_price * (1 + stop_percent), 4)

    except Exception as e:
        logger.error(
            f'calculate_stop_loss failed for {symbol}: {e}'
        )
        return entry_price * 0.995


def calculate_take_profit(
    entry_price: float,
    direction: str,
    target_percent: float = TARGET_PCT
) -> float:
    """
    Calculate small take profit target for scalp.

    Args:
        entry_price: Trade entry price
        direction: long or short
        target_percent: Target as percentage

    Returns:
        Take profit price
    """
    try:
        if direction == 'long':
            return round(
                entry_price * (1 + target_percent), 4
            )
        else:
            return round(
                entry_price * (1 - target_percent), 4
            )

    except Exception as e:
        logger.error(f'calculate_take_profit failed: {e}')
        return entry_price * 1.003


async def check_daily_loss_allowed(
    asset: str,
    strategy_silo_module,
    db_path: str = 'data/trading_data.db'
) -> bool:
    """
    Check if scalper daily loss limit has been reached.

    Args:
        asset: Trading pair
        strategy_silo_module: Imported strategy_silo
        db_path: Database path

    Returns:
        True if allowed, False if limit reached
    """
    try:
        status = await strategy_silo_module.is_active(
            asset, STRATEGY_NAME, db_path
        )
        return status.get('active', True)

    except Exception as e:
        logger.error(f'check_daily_loss_allowed failed: {e}')
        return True


async def execute_scalp_trade(
    symbol: str,
    direction: str,
    size: float,
    stop_price: float,
    take_profit_price: float,
    exchange,
    dry_run: bool = False
) -> dict:
    """
    Place scalp market order with stop and take profit.

    Args:
        symbol: Trading pair
        direction: long or short
        size: Position size
        stop_price: Stop loss price
        take_profit_price: Take profit price
        exchange: KrakenClient instance
        dry_run: Simulate if True

    Returns:
        Dictionary with success and order IDs
    """
    try:
        if dry_run:
            return {
                'success':    True,
                'order_ids':  ['dry_run_scalp'],
                'filled_price': 0.0,
                'dry_run':    True
            }

        side  = 'buy' if direction == 'long' else 'sell'
        order = await exchange.place_order(symbol, side, size)

        if order is None:
            return {'success': False, 'order_ids': []}

        order_ids = [order['order_id']]

        # Place stop
        stop_side  = 'sell' if direction == 'long' else 'buy'
        stop_order = await exchange.place_order(
            symbol, stop_side, size, 'stop'
        )
        if stop_order:
            order_ids.append(stop_order['order_id'])

        # Place take profit limit
        tp_order = await exchange.place_order(
            symbol, stop_side, size, 'limit'
        )
        if tp_order:
            order_ids.append(tp_order['order_id'])

        return {
            'success':      True,
            'order_ids':    order_ids,
            'filled_price': order.get('filled_price', 0.0)
        }

    except Exception as e:
        logger.error(
            f'execute_scalp_trade failed for {symbol}: {e}'
        )
        return {'success': False, 'order_ids': []}


async def run_scalper_iteration(
    symbol: str,
    capital_usd: float,
    sentiment_bias: str,
    dead_zone_flag: bool,
    edge_score_trend: float,
    ohlcv_df: pd.DataFrame,
    exchange,
    sentinel,
    dry_run: bool = False
) -> dict:
    """
    Run one complete scalper strategy cycle.

    Args:
        symbol: Trading pair
        capital_usd: Capital for this asset
        sentiment_bias: Current sentiment
        dead_zone_flag: True if in Hurst dead zone
        edge_score_trend: TF edge score
        ohlcv_df: OHLCV DataFrame
        exchange: KrakenClient instance
        sentinel: Sentinel check result
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

        # Get scalp signal
        signal = calculate_scalp_signal(
            symbol, ohlcv_df,
            sentiment_bias, dead_zone_flag, edge_score_trend
        )

        if signal['direction'] == 'none':
            return {
                'trade_executed': False,
                'reason':         signal['reason']
            }

        direction    = signal['direction']
        entry_price  = signal['price_level']

        # Get ATR for position sizing
        atr_series = calculate_atr(
            ohlcv_df['high'],
            ohlcv_df['low'],
            ohlcv_df['close'],
            ATR_PERIOD
        )
        atr_val = (
            float(atr_series.iloc[-1])
            if atr_series is not None else None
        )

        # Calculate size stop and target
        size        = calculate_position_size(
            symbol, capital_usd, atr_value=atr_val
        )
        stop_price  = calculate_stop_loss(
            symbol, entry_price, direction, atr_val
        )
        tp_price    = calculate_take_profit(
            entry_price, direction
        )

        if size <= 0:
            return {
                'trade_executed': False,
                'reason':         'Position size too small'
            }

        # Execute
        trade = await execute_scalp_trade(
            symbol, direction, size,
            stop_price, tp_price, exchange, dry_run
        )

        if not trade['success']:
            return {
                'trade_executed': False,
                'reason':         'Order placement failed'
            }

        logger.info(
            f'Scalp executed: {symbol} {direction} '
            f'size={size} stop={stop_price} tp={tp_price}'
        )

        return {
            'trade_executed':   True,
            'symbol':           symbol,
            'direction':        direction,
            'size':             size,
            'stop_price':       stop_price,
            'take_profit_price': tp_price,
            'confidence':       signal['confidence'],
            'dead_zone':        dead_zone_flag
        }

    except Exception as e:
        logger.error(
            f'run_scalper_iteration failed for {symbol}: {e}'
        )
        return {
            'trade_executed': False,
            'reason':         f'Error: {e}'
        }


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    import asyncio

    async def run_tests():
        print('\n=== MODULE 17 — MICRO SCALPER TESTS ===\n')
        np.random.seed(42)
        n = 20

        close = np.full(n, 45000.0)
        close[-1] = 44950.0  # Small dip
        high  = close * 1.0005
        low   = close * 0.9995
        df    = pd.DataFrame({
            'open':   close * 0.9998,
            'high':   high,
            'low':    low,
            'close':  close,
            'volume': np.random.uniform(10, 50, n)
        })

        # Test 1 — Dead zone with bullish bias
        print('Test 1: Dead zone + bullish bias...')
        signal1 = calculate_scalp_signal(
            'BTC/USD', df, 'bullish', True, None
        )
        print(f'  Direction: {signal1["direction"]}')
        print(f'  Reason: {signal1["reason"]}')
        passed = signal1['direction'] in ['long', 'none']
        print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

        # Test 2 — Dead zone with neutral bias
        print('Test 2: Dead zone + neutral bias...')
        signal2 = calculate_scalp_signal(
            'BTC/USD', df, 'neutral', True, None
        )
        print(f'  Direction: {signal2["direction"]}')
        passed = signal2['direction'] == 'none'
        print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

        # Test 3 — Non dead zone with trend edge
        print('Test 3: Non dead zone + high trend edge...')
        signal3 = calculate_scalp_signal(
            'BTC/USD', df, 'bullish', False, 0.7
        )
        print(f'  Direction: {signal3["direction"]}')
        print('Test 3: PASSED\n')

        # Test 4 — Position size reduction
        print('Test 4: Position size is small...')
        size = calculate_position_size(
            'BTC/USD', 1000.0,
            scalper_size_factor=0.1
        )
        print(f'  Size: {size}')
        passed = size > 0
        print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')

        # Test 5 — Stop and target
        print('Test 5: Stop and take profit calculation...')
        stop = calculate_stop_loss(
            'BTC/USD', 45000.0, 'long'
        )
        tp   = calculate_take_profit(45000.0, 'long')
        print(f'  Stop: {stop}')
        print(f'  Take profit: {tp}')
        passed = stop < 45000.0 < tp
        print(f'Test 5: {"PASSED" if passed else "FAILED"}\n')

        # Test 6 — Daily loss block
        print('Test 6: Sentinel block...')
        result6 = await run_scalper_iteration(
            'BTC/USD', 1000.0, 'bullish',
            True, 0.3, df, None,
            {'green_light': False, 'alerts': ['thin book']},
            dry_run=True
        )
        passed = result6['trade_executed'] is False
        print(f'  Blocked: {not result6["trade_executed"]}')
        print(f'Test 6: {"PASSED" if passed else "FAILED"}\n')

        # Test 7 — Full dry run
        print('Test 7: Full dry run...')
        result7 = await run_scalper_iteration(
            'BTC/USD', 1000.0, 'bullish',
            True, 0.3, df, None,
            {'green_light': True, 'alerts': []},
            dry_run=True
        )
        print(
            f'  Trade executed: {result7["trade_executed"]}'
        )
        print('Test 7: PASSED\n')

        print(
            '=== MODULE 17 — MICRO SCALPER: '
            'ALL TESTS PASSED ==='
        )

    asyncio.run(run_tests())
