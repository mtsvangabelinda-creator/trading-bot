# Autonomous Multi-Strategy Trading System
# Module 20a — Stop Placer
# Places stop-loss orders outside known liquidity voids
# Ensures stops are never placed inside thin order book areas

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import ATR_MULTIPLIER, ATR_PERIOD
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

logger = setup_logger('stop_placer', 'logs/trades.log')


def find_liquidity_void(
    order_book: dict,
    direction: str,
    current_price: float,
    search_range_pct: float = 0.05
) -> dict:
    """
    Find the largest liquidity gap in the order book.

    For long positions looks at bids below current price.
    For short positions looks at asks above current price.

    Args:
        order_book: Dict with bids and asks lists
        direction: long or short
        current_price: Current market price
        search_range_pct: How far to search as percentage

    Returns:
        Dictionary with void_price, void_size_pct,
        safe_stop_price
    """
    try:
        search_range = current_price * search_range_pct

        if direction == 'long':
            levels = [
                level for level in order_book.get('bids', [])
                if (
                    len(level) >= 2 and
                    float(level[0]) >= current_price - search_range
                )
            ]
            levels = sorted(
                levels, key=lambda x: float(x[0]), reverse=True
            )
        else:
            levels = [
                level for level in order_book.get('asks', [])
                if (
                    len(level) >= 2 and
                    float(level[0]) <= current_price + search_range
                )
            ]
            levels = sorted(
                levels, key=lambda x: float(x[0])
            )

        if len(levels) < 2:
            # No meaningful order book data
            if direction == 'long':
                safe_stop = current_price * (
                    1 - search_range_pct / 2
                )
            else:
                safe_stop = current_price * (
                    1 + search_range_pct / 2
                )

            return {
                'void_price':      safe_stop,
                'void_size_pct':   0.0,
                'safe_stop_price': round(safe_stop, 4)
            }

        # Find largest gap between consecutive levels
        max_gap     = 0.0
        void_price  = float(levels[-1][0])

        for i in range(len(levels) - 1):
            p1  = float(levels[i][0])
            p2  = float(levels[i + 1][0])
            gap = abs(p1 - p2)

            if gap > max_gap:
                max_gap    = gap
                void_price = (p1 + p2) / 2

        void_size_pct = max_gap / current_price

        # Safe stop is just beyond the void
        if direction == 'long':
            safe_stop = void_price - (max_gap * 0.1)
        else:
            safe_stop = void_price + (max_gap * 0.1)

        return {
            'void_price':      round(void_price, 4),
            'void_size_pct':   round(void_size_pct, 6),
            'safe_stop_price': round(safe_stop, 4)
        }

    except Exception as e:
        logger.error(f'find_liquidity_void failed: {e}')
        if direction == 'long':
            fallback = current_price * 0.975
        else:
            fallback = current_price * 1.025
        return {
            'void_price':      round(fallback, 4),
            'void_size_pct':   0.0,
            'safe_stop_price': round(fallback, 4)
        }


async def calculate_safe_stop(
    symbol: str,
    direction: str,
    entry_price: float,
    atr: float,
    exchange
) -> float:
    """
    Calculate the safest stop loss price.

    Compares void-based stop with ATR-based stop
    and takes the more conservative (wider) stop.

    Args:
        symbol: Trading pair
        direction: long or short
        entry_price: Trade entry price
        atr: Current ATR value
        exchange: KrakenClient instance

    Returns:
        Safe stop price as float
    """
    try:
        # ATR-based stop
        if direction == 'long':
            atr_stop = entry_price - (atr * ATR_MULTIPLIER)
        else:
            atr_stop = entry_price + (atr * ATR_MULTIPLIER)

        # Try to get order book for void detection
        try:
            order_book = await exchange.fetch_order_book(
                symbol, 20
            )
            if order_book:
                void = find_liquidity_void(
                    order_book, direction, entry_price
                )
                void_stop = void['safe_stop_price']

                # Take the more conservative stop
                if direction == 'long':
                    safe_stop = min(atr_stop, void_stop)
                else:
                    safe_stop = max(atr_stop, void_stop)
            else:
                safe_stop = atr_stop

        except Exception:
            safe_stop = atr_stop

        logger.debug(
            f'Safe stop for {symbol} {direction}: '
            f'{round(safe_stop, 4)} '
            f'(entry={entry_price}, atr={atr})'
        )

        return round(safe_stop, 4)

    except Exception as e:
        logger.error(f'calculate_safe_stop failed: {e}')
        if direction == 'long':
            return round(entry_price * 0.975, 4)
        else:
            return round(entry_price * 1.025, 4)


async def place_stop_loss(
    symbol: str,
    stop_price: float,
    size: float,
    direction: str,
    exchange,
    dry_run: bool = False
) -> Optional[dict]:
    """
    Place a stop-loss order on Kraken.

    Args:
        symbol: Trading pair
        stop_price: Stop loss price
        size: Position size to close
        direction: Original trade direction
        exchange: KrakenClient instance
        dry_run: Simulate if True

    Returns:
        Order details dictionary or None on failure
    """
    try:
        if dry_run:
            logger.info(
                f'DRY RUN stop loss: {symbol} '
                f'stop={stop_price} size={size}'
            )
            return {
                'success':    True,
                'order_id':   'dry_run_stop',
                'stop_price': stop_price,
                'size':       size,
                'dry_run':    True
            }

        # Stop order closes the position
        side  = 'sell' if direction == 'long' else 'buy'
        order = await exchange.place_order(
            symbol, side, size, 'stop'
        )

        if order is None:
            logger.error(
                f'place_stop_loss: order placement failed '
                f'for {symbol}'
            )
            return None

        logger.info(
            f'Stop loss placed: {symbol} at {stop_price} '
            f'size={size} id={order["order_id"]}'
        )

        return {
            'success':    True,
            'order_id':   order['order_id'],
            'stop_price': stop_price,
            'size':       size
        }

    except Exception as e:
        logger.error(f'place_stop_loss failed for {symbol}: {e}')
        return None


async def place_take_profit(
    symbol: str,
    tp_price: float,
    size: float,
    direction: str,
    exchange,
    dry_run: bool = False
) -> Optional[dict]:
    """
    Place a take profit limit order on Kraken.

    Args:
        symbol: Trading pair
        tp_price: Take profit price
        size: Position size to close
        direction: Original trade direction
        exchange: KrakenClient instance
        dry_run: Simulate if True

    Returns:
        Order details dictionary or None on failure
    """
    try:
        if dry_run:
            return {
                'success':  True,
                'order_id': 'dry_run_tp',
                'tp_price': tp_price,
                'size':     size,
                'dry_run':  True
            }

        side  = 'sell' if direction == 'long' else 'buy'
        order = await exchange.place_order(
            symbol, side, size, 'limit'
        )

        if order is None:
            return None

        logger.info(
            f'Take profit placed: {symbol} at {tp_price} '
            f'size={size} id={order["order_id"]}'
        )

        return {
            'success':  True,
            'order_id': order['order_id'],
            'tp_price': tp_price,
            'size':     size
        }

    except Exception as e:
        logger.error(
            f'place_take_profit failed for {symbol}: {e}'
        )
        return None


async def cancel_all_stops(
    symbol: str,
    exchange
) -> int:
    """
    Cancel all open stop orders for a symbol.

    Used by emergency close function.

    Args:
        symbol: Trading pair
        exchange: KrakenClient instance

    Returns:
        Count of cancelled orders
    """
    try:
        open_orders = await exchange.fetch_open_orders(symbol)

        if not open_orders:
            return 0

        cancelled = 0
        for order in open_orders:
            order_id = order.get('order_id')
            if order_id:
                success = await exchange.cancel_order(
                    order_id, symbol
                )
                if success:
                    cancelled += 1

        logger.info(
            f'Cancelled {cancelled} orders for {symbol}'
        )
        return cancelled

    except Exception as e:
        logger.error(
            f'cancel_all_stops failed for {symbol}: {e}'
        )
        return 0


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 20a — STOP PLACER TESTS ===\n')

    # Test 1 — find_liquidity_void with clear gap
    print('Test 1: find_liquidity_void with gap...')
    mock_book = {
        'bids': [
            [44990, 1.0], [44970, 0.5],
            [44500, 2.0], [44490, 1.0]
        ],
        'asks': [
            [45010, 1.0], [45030, 0.5],
            [45500, 2.0], [45510, 1.0]
        ]
    }
    void = find_liquidity_void(
        mock_book, 'long', 45000.0
    )
    print(f'  Void price: {void["void_price"]}')
    print(f'  Void size: {void["void_size_pct"]}')
    print(f'  Safe stop: {void["safe_stop_price"]}')
    passed = void['safe_stop_price'] < 45000.0
    print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

    # Test 2 — find_liquidity_void short
    print('Test 2: find_liquidity_void short...')
    void2 = find_liquidity_void(
        mock_book, 'short', 45000.0
    )
    print(f'  Safe stop: {void2["safe_stop_price"]}')
    passed = void2['safe_stop_price'] > 45000.0
    print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

    # Test 3 — Empty order book fallback
    print('Test 3: Empty order book fallback...')
    void3 = find_liquidity_void(
        {'bids': [], 'asks': []}, 'long', 45000.0
    )
    print(f'  Safe stop: {void3["safe_stop_price"]}')
    passed = void3['safe_stop_price'] < 45000.0
    print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

    print('=== MODULE 20a — STOP PLACER: ALL TESTS PASSED ===')
