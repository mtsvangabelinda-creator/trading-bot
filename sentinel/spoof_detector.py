# Autonomous Multi-Strategy Trading System
# Module 14a — Spoof Detector
# Detects fake large orders that appear then disappear
# Part of the Sentinel order book monitor

import logging
import os
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np

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

logger = setup_logger('spoof_detector', 'logs/sentinel.log')

# ── Order Book History ────────────────────────────────────────
# Stores recent order book snapshots per symbol
_order_book_history: dict = {}


def detect_spoof(
    symbol: str,
    order_book: dict,
    threshold_ratio: float = 0.3,
    lookback_seconds: int = 10
) -> dict:
    """
    Detect potential spoofing in the order book.

    Tracks large orders that appear then disappear
    within a short window as potential spoof signals.

    Args:
        symbol: Trading pair
        order_book: Dict with bids and asks lists
        threshold_ratio: Orders larger than this ratio
            of total book depth are flagged as large
        lookback_seconds: Window to track order changes

    Returns:
        Dictionary with spoof_detected, suspicious_orders,
        confidence
    """
    try:
        now = time.time()

        if symbol not in _order_book_history:
            _order_book_history[symbol] = deque(maxlen=20)

        # Store current snapshot
        _order_book_history[symbol].append({
            'timestamp': now,
            'bids': list(order_book.get('bids', [])[:10]),
            'asks': list(order_book.get('asks', [])[:10])
        })

        history = _order_book_history[symbol]

        if len(history) < 2:
            return {
                'spoof_detected':    False,
                'suspicious_orders': 0,
                'confidence':        0.0
            }

        # Get relevant snapshots within lookback window
        recent = [
            h for h in history
            if now - h['timestamp'] <= lookback_seconds
        ]

        if len(recent) < 2:
            return {
                'spoof_detected':    False,
                'suspicious_orders': 0,
                'confidence':        0.0
            }

        # Calculate total bid and ask volumes
        current  = recent[-1]
        previous = recent[0]

        def get_total_volume(side):
            return sum(
                float(order[1])
                for order in side
                if len(order) >= 2
            )

        curr_bid_vol = get_total_volume(current['bids'])
        curr_ask_vol = get_total_volume(current['asks'])
        prev_bid_vol = get_total_volume(previous['bids'])
        prev_ask_vol = get_total_volume(previous['asks'])

        suspicious_count = 0
        confidence       = 0.0

        # Check for large orders that disappeared
        if prev_bid_vol > 0 and curr_bid_vol > 0:
            bid_change = abs(prev_bid_vol - curr_bid_vol)
            if bid_change / prev_bid_vol > threshold_ratio:
                suspicious_count += 1
                confidence += 0.4

        if prev_ask_vol > 0 and curr_ask_vol > 0:
            ask_change = abs(prev_ask_vol - curr_ask_vol)
            if ask_change / prev_ask_vol > threshold_ratio:
                suspicious_count += 1
                confidence += 0.4

        # Check for imbalanced order book
        if curr_bid_vol > 0 and curr_ask_vol > 0:
            imbalance = abs(curr_bid_vol - curr_ask_vol) / (
                curr_bid_vol + curr_ask_vol
            )
            if imbalance > 0.7:
                suspicious_count += 1
                confidence += 0.2

        spoof_detected = suspicious_count >= 2
        confidence     = round(min(1.0, confidence), 4)

        if spoof_detected:
            logger.warning(
                f'Spoof detected for {symbol}: '
                f'suspicious_orders={suspicious_count}, '
                f'confidence={confidence}'
            )

        return {
            'spoof_detected':    spoof_detected,
            'suspicious_orders': suspicious_count,
            'confidence':        confidence
        }

    except Exception as e:
        logger.error(f'detect_spoof failed for {symbol}: {e}')
        return {
            'spoof_detected':    False,
            'suspicious_orders': 0,
            'confidence':        0.0
  }
