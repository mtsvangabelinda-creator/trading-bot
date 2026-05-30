# Autonomous Multi-Strategy Trading System
# Module 14b — Liquidity Monitor
# Checks order book depth, spread, and volume
# Part of the Sentinel order book monitor

import logging
import os
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np

from config import (
    SPREAD_MULTIPLIER,
    SLIPPAGE_TOLERANCE,
    LIQUIDITY_DEPTH_PCT,
    VOLUME_DRYUP_SECS
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

logger = setup_logger('liquidity_monitor', 'logs/sentinel.log')

# ── Spread History ────────────────────────────────────────────
_spread_history: dict = {}


def check_liquidity_gaps(
    order_book: dict,
    depth_pct: float = LIQUIDITY_DEPTH_PCT
) -> dict:
    """
    Find significant price gaps in the order book.

    Args:
        order_book: Dict with bids and asks lists
        depth_pct: Percentage depth to search within

    Returns:
        Dictionary with has_gap, gap_percent, gap_location
    """
    try:
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])

        if not bids or not asks:
            return {
                'has_gap':      False,
                'gap_percent':  0.0,
                'gap_location': 'N/A'
            }

        mid_price = (
            float(bids[0][0]) + float(asks[0][0])
        ) / 2

        depth_range = mid_price * depth_pct

        # Check for gaps in asks
        max_ask_gap     = 0.0
        max_gap_location = 'N/A'

        for i in range(len(asks) - 1):
            price_curr = float(asks[i][0])
            price_next = float(asks[i + 1][0])

            if price_curr > mid_price + depth_range:
                break

            gap = price_next - price_curr
            gap_pct = gap / mid_price

            if gap_pct > max_ask_gap:
                max_ask_gap      = gap_pct
                max_gap_location = f'asks at {price_curr:.2f}'

        # Check for gaps in bids
        for i in range(len(bids) - 1):
            price_curr = float(bids[i][0])
            price_next = float(bids[i + 1][0])

            if price_curr < mid_price - depth_range:
                break

            gap = price_curr - price_next
            gap_pct = gap / mid_price

            if gap_pct > max_ask_gap:
                max_ask_gap      = gap_pct
                max_gap_location = f'bids at {price_curr:.2f}'

        has_gap = max_ask_gap > SLIPPAGE_TOLERANCE

        if has_gap:
            logger.warning(
                f'Liquidity gap detected: '
                f'{round(max_ask_gap*100, 3)}% at '
                f'{max_gap_location}'
            )

        return {
            'has_gap':      has_gap,
            'gap_percent':  round(max_ask_gap, 6),
            'gap_location': max_gap_location
        }

    except Exception as e:
        logger.error(f'check_liquidity_gaps failed: {e}')
        return {
            'has_gap':      False,
            'gap_percent':  0.0,
            'gap_location': 'error'
        }


def check_spread_abnormal(
    symbol: str,
    order_book: dict,
    spread_multiplier: float = SPREAD_MULTIPLIER
) -> dict:
    """
    Check if current spread is abnormally wide.

    Compares current spread to rolling 4-hour average.

    Args:
        symbol: Trading pair
        order_book: Dict with bids and asks
        spread_multiplier: Alert threshold vs average

    Returns:
        Dictionary with is_abnormal, current_spread,
        avg_spread, ratio
    """
    try:
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])

        if not bids or not asks:
            return {
                'is_abnormal':    False,
                'current_spread': 0.0,
                'avg_spread':     0.0,
                'ratio':          1.0
            }

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        mid      = (best_bid + best_ask) / 2

        if mid == 0:
            return {
                'is_abnormal':    False,
                'current_spread': 0.0,
                'avg_spread':     0.0,
                'ratio':          1.0
            }

        current_spread = (best_ask - best_bid) / mid

        # Store in history
        if symbol not in _spread_history:
            _spread_history[symbol] = deque(maxlen=240)

        _spread_history[symbol].append(current_spread)

        if len(_spread_history[symbol]) < 5:
            return {
                'is_abnormal':    False,
                'current_spread': round(current_spread, 6),
                'avg_spread':     round(current_spread, 6),
                'ratio':          1.0
            }

        avg_spread   = float(
            np.mean(list(_spread_history[symbol]))
        )
        ratio        = (
            current_spread / avg_spread
            if avg_spread > 0 else 1.0
        )
        is_abnormal  = ratio > spread_multiplier

        if is_abnormal:
            logger.warning(
                f'Abnormal spread for {symbol}: '
                f'current={round(current_spread*100, 4)}%, '
                f'avg={round(avg_spread*100, 4)}%, '
                f'ratio={round(ratio, 2)}'
            )

        return {
            'is_abnormal':    is_abnormal,
            'current_spread': round(current_spread, 6),
            'avg_spread':     round(avg_spread, 6),
            'ratio':          round(ratio, 4)
        }

    except Exception as e:
        logger.error(
            f'check_spread_abnormal failed for {symbol}: {e}'
        )
        return {
            'is_abnormal':    False,
            'current_spread': 0.0,
            'avg_spread':     0.0,
            'ratio':          1.0
        }


def check_depth_sufficiency(
    order_book: dict,
    order_amount_usd: float,
    slippage_tolerance: float = SLIPPAGE_TOLERANCE,
    depth_pct: float = LIQUIDITY_DEPTH_PCT
) -> dict:
    """
    Check if order book has enough depth to fill an order.

    Args:
        order_book: Dict with bids and asks
        order_amount_usd: Dollar value of order to fill
        slippage_tolerance: Maximum acceptable slippage
        depth_pct: Depth range to check within

    Returns:
        Dictionary with sufficient, expected_slippage,
        depth_available_usd
    """
    try:
        asks = order_book.get('asks', [])
        bids = order_book.get('bids', [])

        if not asks or not bids:
            return {
                'sufficient':          False,
                'expected_slippage':   1.0,
                'depth_available_usd': 0.0
            }

        mid_price   = (float(bids[0][0]) + float(asks[0][0])) / 2
        depth_limit = mid_price * (1 + depth_pct)

        # Simulate buy order through asks
        total_cost     = 0.0
        total_quantity = 0.0
        remaining_usd  = order_amount_usd

        for ask in asks:
            if len(ask) < 2:
                continue
            price = float(ask[0])
            qty   = float(ask[1])

            if price > depth_limit:
                break

            level_value = price * qty
            if level_value >= remaining_usd:
                filled_qty  = remaining_usd / price
                total_cost += remaining_usd
                total_quantity += filled_qty
                remaining_usd  = 0
                break
            else:
                total_cost     += level_value
                total_quantity += qty
                remaining_usd  -= level_value

        depth_available = order_amount_usd - remaining_usd

        if total_quantity > 0 and remaining_usd == 0:
            avg_fill_price    = total_cost / total_quantity
            expected_slippage = abs(
                avg_fill_price - mid_price
            ) / mid_price
        else:
            expected_slippage = 1.0

        sufficient = (
            remaining_usd == 0 and
            expected_slippage <= slippage_tolerance
        )

        if not sufficient:
            logger.warning(
                f'Insufficient depth: '
                f'available=${depth_available:.2f}, '
                f'slippage={round(expected_slippage*100, 3)}%'
            )

        return {
            'sufficient':          sufficient,
            'expected_slippage':   round(expected_slippage, 6),
            'depth_available_usd': round(depth_available, 2)
        }

    except Exception as e:
        logger.error(f'check_depth_sufficiency failed: {e}')
        return {
            'sufficient':          False,
            'expected_slippage':   1.0,
            'depth_available_usd': 0.0
        }


def check_volume_dryup(
    symbol: str,
    recent_trades: list,
    lookback_seconds: int = VOLUME_DRYUP_SECS,
    volume_threshold_pct: float = 0.2
) -> dict:
    """
    Detect sudden volume dry-up indicating liquidity collapse.

    Args:
        symbol: Trading pair
        recent_trades: List of recent trade dicts
        lookback_seconds: Time window to analyse
        volume_threshold_pct: Alert if volume below this
            percentage of normal

    Returns:
        Dictionary with dryup, current_volume, normal_volume
    """
    try:
        if not recent_trades:
            return {
                'dryup':          False,
                'current_volume': 0.0,
                'normal_volume':  0.0
            }

        now        = time.time()
        cutoff     = now - lookback_seconds

        # Calculate current volume
        current_vol = sum(
            float(t.get('amount', 0))
            for t in recent_trades
            if float(t.get('timestamp', 0)) / 1000 >= cutoff
        )

        # Use total as proxy for normal volume
        total_vol   = sum(
            float(t.get('amount', 0))
            for t in recent_trades
        )
        normal_vol  = total_vol / max(1, len(recent_trades)) * 10

        dryup = (
            normal_vol > 0 and
            current_vol < normal_vol * volume_threshold_pct
        )

        if dryup:
            logger.warning(
                f'Volume dry-up for {symbol}: '
                f'current={round(current_vol, 4)}, '
                f'normal={round(normal_vol, 4)}'
            )

        return {
            'dryup':          dryup,
            'current_volume': round(current_vol, 4),
            'normal_volume':  round(normal_vol, 4)
        }

    except Exception as e:
        logger.error(f'check_volume_dryup failed: {e}')
        return {
            'dryup':          False,
            'current_volume': 0.0,
            'normal_volume':  0.0
      }
