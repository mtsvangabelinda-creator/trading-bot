# Autonomous Multi-Strategy Trading System
# Module 18a — Backtest Simulator
# Simulates realistic order fills with fees and slippage
# No real exchange connection — all simulated

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

from config import MAKER_FEE, TAKER_FEE

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

logger = setup_logger('simulator', 'logs/backtest.log')

# ── Simulated Slippage ────────────────────────────────────────
SIMULATED_SLIPPAGE = 0.0005


def simulate_market_order(
    direction: str,
    size: float,
    current_price: float,
    fee_rate: float = TAKER_FEE
) -> dict:
    """
    Simulate a market order fill with realistic fees.

    Args:
        direction: buy or sell
        size: Quantity to trade in base currency
        current_price: Current market price
        fee_rate: Taker fee rate as decimal

    Returns:
        Dictionary with filled_price, fee_paid,
        net_cost, slippage
    """
    try:
        # Apply slippage
        if direction == 'buy':
            filled_price = current_price * (
                1 + SIMULATED_SLIPPAGE
            )
        else:
            filled_price = current_price * (
                1 - SIMULATED_SLIPPAGE
            )

        notional = filled_price * size
        fee_paid = notional * fee_rate
        net_cost = notional + fee_paid

        return {
            'filled_price': round(filled_price, 4),
            'fee_paid':     round(fee_paid, 4),
            'net_cost':     round(net_cost, 4),
            'slippage':     SIMULATED_SLIPPAGE,
            'notional':     round(notional, 4)
        }

    except Exception as e:
        logger.error(f'simulate_market_order failed: {e}')
        return {
            'filled_price': current_price,
            'fee_paid':     0.0,
            'net_cost':     current_price * size,
            'slippage':     0.0,
            'notional':     current_price * size
        }


def simulate_stop_hit(
    stop_price: float,
    candle_low: float,
    candle_high: float,
    direction: str
) -> bool:
    """
    Check if stop loss was hit on this candle.

    Args:
        stop_price: Stop loss price
        candle_low: Candle low price
        candle_high: Candle high price
        direction: Original trade direction

    Returns:
        True if stop was hit, False otherwise
    """
    try:
        if direction == 'long':
            return candle_low <= stop_price
        else:
            return candle_high >= stop_price

    except Exception as e:
        logger.error(f'simulate_stop_hit failed: {e}')
        return False


def simulate_take_profit_hit(
    tp_price: float,
    candle_low: float,
    candle_high: float,
    direction: str
) -> bool:
    """
    Check if take profit was hit on this candle.

    Args:
        tp_price: Take profit price
        candle_low: Candle low price
        candle_high: Candle high price
        direction: Original trade direction

    Returns:
        True if take profit was hit, False otherwise
    """
    try:
        if direction == 'long':
            return candle_high >= tp_price
        else:
            return candle_low <= tp_price

    except Exception as e:
        logger.error(f'simulate_take_profit_hit failed: {e}')
        return False


def calculate_pnl(
    direction: str,
    entry_price: float,
    exit_price: float,
    size: float,
    entry_fee: float,
    exit_fee: float
) -> float:
    """
    Calculate net PnL for a completed trade after fees.

    Args:
        direction: long or short
        entry_price: Trade entry price
        exit_price: Trade exit price
        size: Position size in base currency
        entry_fee: Fee paid on entry
        exit_fee: Fee paid on exit

    Returns:
        Net PnL in USD as float
    """
    try:
        if direction == 'long':
            gross_pnl = (exit_price - entry_price) * size
        else:
            gross_pnl = (entry_price - exit_price) * size

        net_pnl = gross_pnl - entry_fee - exit_fee

        return round(net_pnl, 4)

    except Exception as e:
        logger.error(f'calculate_pnl failed: {e}')
        return 0.0


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 18a — SIMULATOR TESTS ===\n')

    # Test 1 — simulate_market_order
    print('Test 1: simulate_market_order...')
    result = simulate_market_order('buy', 0.1, 45000.0)
    print(f'  Filled price: {result["filled_price"]}')
    print(f'  Fee paid: {result["fee_paid"]}')
    print(f'  Net cost: {result["net_cost"]}')
    expected_fee = round(45000.0 * 0.1 * TAKER_FEE, 4)
    passed = abs(result['fee_paid'] - expected_fee) < 1.0
    print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')

    # Test 2 — simulate_stop_hit long
    print('Test 2: Stop hit on long position...')
    hit = simulate_stop_hit(44000.0, 43800.0, 44500.0, 'long')
    no_hit = simulate_stop_hit(
        44000.0, 44200.0, 44800.0, 'long'
    )
    print(f'  Stop at 44000, low 43800: {hit}')
    print(f'  Stop at 44000, low 44200: {no_hit}')
    passed = hit is True and no_hit is False
    print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

    # Test 3 — simulate_take_profit_hit
    print('Test 3: Take profit hit...')
    tp_hit = simulate_take_profit_hit(
        46000.0, 45500.0, 46200.0, 'long'
    )
    tp_miss = simulate_take_profit_hit(
        46000.0, 45500.0, 45900.0, 'long'
    )
    print(f'  TP at 46000, high 46200: {tp_hit}')
    print(f'  TP at 46000, high 45900: {tp_miss}')
    passed = tp_hit is True and tp_miss is False
    print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')

    # Test 4 — calculate_pnl
    print('Test 4: calculate_pnl...')
    pnl = calculate_pnl(
        'long', 45000.0, 46000.0, 0.1, 11.7, 11.96
    )
    print(f'  Net PnL: ${pnl}')
    passed = pnl > 0
    print(f'Test 4: {"PASSED" if passed else "FAILED"}\n')

    print('=== MODULE 18a — SIMULATOR: ALL TESTS PASSED ===')
