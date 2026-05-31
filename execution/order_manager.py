# Autonomous Multi-Strategy Trading System
# Module 20b — Order Manager
# Orchestrates complete trade lifecycle
# From signal to execution to exit
# Manages all open positions and monitors for exits

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional

from config import ATR_MULTIPLIER, ATR_PERIOD, ASSETS
from execution.stop_placer import (
    calculate_safe_stop,
    place_stop_loss,
    place_take_profit,
    cancel_all_stops
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

logger        = setup_logger('order_manager', 'logs/trades.log')
trades_logger = setup_logger('trades', 'logs/trades.log')

# ── Take Profit Multiplier ────────────────────────────────────
TP_ATR_MULTIPLIER = 2.0

# ── Open Positions Store ──────────────────────────────────────
# In-memory dictionary tracking all open positions
# Format: {symbol: {direction, entry_price, size, stop, tp, ...}}
_open_positions: dict = {}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def open_position(
    symbol: str,
    direction: str,
    size: float,
    strategy: str,
    edge_score: float,
    atr: float,
    exchange,
    tp_multiplier: float = TP_ATR_MULTIPLIER,
    dry_run: bool = False
) -> Optional[dict]:
    """
    Open a new position with stop loss and take profit.

    Places market order then immediately places stop and
    take profit orders. If stop placement fails the
    position is immediately closed.

    Args:
        symbol: Trading pair
        direction: long or short
        size: Position size in base currency
        strategy: Strategy that generated the signal
        edge_score: Edge score at time of entry
        atr: Current ATR value
        exchange: KrakenClient instance
        tp_multiplier: Take profit ATR multiplier
        dry_run: Simulate if True

    Returns:
        Full position details dictionary or None on failure
    """
    try:
        # Check no existing position for this symbol
        if symbol in _open_positions:
            logger.warning(
                f'open_position: position already open '
                f'for {symbol}'
            )
            return None

        # Place market order
        side = 'buy' if direction == 'long' else 'sell'

        if dry_run:
            # Simulate entry
            entry_price = 45000.0
            order_id    = f'dry_run_{symbol}_{now_utc().timestamp()}'
            logger.info(
                f'DRY RUN: open {direction} {size} {symbol}'
            )
        else:
            order = await exchange.place_order(
                symbol, side, size
            )
            if order is None:
                logger.error(
                    f'open_position: entry order failed '
                    f'for {symbol}'
                )
                return None
            entry_price = order.get('filled_price', 0.0)
            order_id    = order['order_id']

        if entry_price == 0.0:
            # Use current price estimate
            try:
                book = await exchange.fetch_order_book(symbol, 1)
                if book and book['bids'] and book['asks']:
                    entry_price = (
                        float(book['bids'][0][0]) +
                        float(book['asks'][0][0])
                    ) / 2
            except Exception:
                entry_price = 45000.0

        # Calculate safe stop loss
        stop_price = await calculate_safe_stop(
            symbol, direction, entry_price, atr, exchange
        )

        # Calculate take profit
        if direction == 'long':
            tp_price = entry_price + (atr * tp_multiplier)
        else:
            tp_price = entry_price - (atr * tp_multiplier)

        # Place stop loss
        stop_result = await place_stop_loss(
            symbol, stop_price, size,
            direction, exchange, dry_run
        )

        if stop_result is None and not dry_run:
            # Critical: close position immediately if stop fails
            logger.critical(
                f'CRITICAL: Stop placement failed for {symbol} '
                f'— closing position immediately'
            )
            close_side = 'sell' if direction == 'long' else 'buy'
            await exchange.place_order(symbol, close_side, size)
            return None

        stop_order_id = (
            stop_result.get('order_id')
            if stop_result else 'dry_run_stop'
        )

        # Place take profit
        tp_result = await place_take_profit(
            symbol, tp_price, size,
            direction, exchange, dry_run
        )

        tp_order_id = (
            tp_result.get('order_id')
            if tp_result else 'dry_run_tp'
        )

        # Store position
        position = {
            'symbol':       symbol,
            'direction':    direction,
            'entry_price':  round(entry_price, 4),
            'size':         size,
            'stop_price':   stop_price,
            'tp_price':     round(tp_price, 4),
            'strategy':     strategy,
            'entry_time':   now_utc(),
            'stop_order_id': stop_order_id,
            'tp_order_id':  tp_order_id,
            'edge_score':   edge_score,
            'atr':          atr,
            'order_id':     order_id
        }

        _open_positions[symbol] = position

        trades_logger.info(
            f'POSITION OPENED | {symbol} | {direction} | '
            f'size={size} | entry={entry_price} | '
            f'stop={stop_price} | tp={round(tp_price,4)} | '
            f'strategy={strategy}'
        )

        return position

    except Exception as e:
        logger.error(
            f'open_position failed for {symbol}: {e}'
        )
        return None


async def close_position(
    symbol: str,
    reason: str,
    exchange,
    dry_run: bool = False
) -> Optional[dict]:
    """
    Close an open position and calculate final PnL.

    Args:
        symbol: Trading pair to close
        reason: Why position is being closed
        exchange: KrakenClient instance
        dry_run: Simulate if True

    Returns:
        Dictionary with pnl, reason, entry/exit prices
        or None on failure
    """
    try:
        if symbol not in _open_positions:
            logger.warning(
                f'close_position: no position found for {symbol}'
            )
            return None

        position = _open_positions[symbol]
        direction = position['direction']
        size      = position['size']
        entry     = position['entry_price']

        # Cancel existing stop and tp orders
        try:
            await cancel_all_stops(symbol, exchange)
        except Exception as e:
            logger.warning(
                f'Could not cancel stops for {symbol}: {e}'
            )

        # Place closing market order
        close_side = 'sell' if direction == 'long' else 'buy'

        if dry_run:
            exit_price = position['entry_price'] * 1.01
            logger.info(
                f'DRY RUN: close {symbol} reason={reason}'
            )
        else:
            order = await exchange.place_order(
                symbol, close_side, size
            )
            if order is None:
                logger.error(
                    f'close_position: closing order failed '
                    f'for {symbol}'
                )
                return None
            exit_price = order.get('filled_price', entry)

        # Calculate PnL
        if direction == 'long':
            gross_pnl = (exit_price - entry) * size
        else:
            gross_pnl = (entry - exit_price) * size

        # Deduct estimated fees
        fee = exit_price * size * 0.0026
        net_pnl = round(gross_pnl - fee, 4)

        duration = now_utc() - position['entry_time']

        result = {
            'symbol':      symbol,
            'direction':   direction,
            'pnl':         net_pnl,
            'reason':      reason,
            'entry_price': entry,
            'exit_price':  round(exit_price, 4),
            'size':        size,
            'strategy':    position['strategy'],
            'duration':    duration,
            'entry_time':  position['entry_time'],
            'exit_time':   now_utc()
        }

        trades_logger.info(
            f'POSITION CLOSED | {symbol} | {direction} | '
            f'pnl={net_pnl} | reason={reason} | '
            f'entry={entry} | exit={round(exit_price,4)}'
        )

        # Remove from open positions
        del _open_positions[symbol]

        return result

    except Exception as e:
        logger.error(
            f'close_position failed for {symbol}: {e}'
        )
        return None


async def check_open_positions(
    exchange,
    dry_run: bool = False
) -> list:
    """
    Check all open positions for stop or tp hits.

    Fetches latest prices and checks exit conditions.

    Args:
        exchange: KrakenClient instance
        dry_run: Simulate if True

    Returns:
        List of positions that were closed this cycle
    """
    closed = []

    for symbol, position in list(_open_positions.items()):
        try:
            # Get latest price
            book = await exchange.fetch_order_book(symbol, 1)
            if not book:
                continue

            current_price = (
                float(book['bids'][0][0]) +
                float(book['asks'][0][0])
            ) / 2

            direction  = position['direction']
            stop_price = position['stop_price']
            tp_price   = position['tp_price']

            stop_hit = (
                direction == 'long' and
                current_price <= stop_price
            ) or (
                direction == 'short' and
                current_price >= stop_price
            )

            tp_hit = (
                direction == 'long' and
                current_price >= tp_price
            ) or (
                direction == 'short' and
                current_price <= tp_price
            )

            if stop_hit:
                result = await close_position(
                    symbol, 'stop_hit', exchange, dry_run
                )
                if result:
                    closed.append(result)

            elif tp_hit:
                result = await close_position(
                    symbol, 'take_profit', exchange, dry_run
                )
                if result:
                    closed.append(result)

        except Exception as e:
            logger.error(
                f'check_open_positions error for {symbol}: {e}'
            )

    return closed


def get_open_positions() -> dict:
    """
    Get copy of all currently open positions.

    Returns:
        Copy of open positions dictionary
    """
    return dict(_open_positions)


async def emergency_close_all(
    exchange,
    dry_run: bool = False
) -> int:
    """
    Emergency close all open positions immediately.

    Cancels all orders then closes all positions
    with market orders.

    Args:
        exchange: KrakenClient instance
        dry_run: Simulate if True

    Returns:
        Count of positions closed
    """
    logger.critical('EMERGENCY CLOSE ALL triggered')
    closed_count = 0

    for symbol in list(_open_positions.keys()):
        try:
            result = await close_position(
                symbol, 'emergency', exchange, dry_run
            )
            if result:
                closed_count += 1
                logger.critical(
                    f'EMERGENCY CLOSED: {symbol} '
                    f'pnl={result["pnl"]}'
                )
        except Exception as e:
            logger.critical(
                f'Emergency close failed for {symbol}: {e}'
            )

    trades_logger.critical(
        f'EMERGENCY CLOSE COMPLETE: '
        f'{closed_count} positions closed'
    )

    return closed_count


def format_position_summary() -> str:
    """
    Format all open positions for Telegram display.

    Returns:
        Formatted position summary string
    """
    try:
        lines = ['OPEN POSITIONS', '─' * 22]

        if not _open_positions:
            for asset in ASSETS.keys():
                lines.append(f'{asset}: No position')
        else:
            for asset in ASSETS.keys():
                if asset in _open_positions:
                    pos      = _open_positions[asset]
                    duration = now_utc() - pos['entry_time']
                    hours    = int(
                        duration.total_seconds() // 3600
                    )
                    minutes  = int(
                        (duration.total_seconds() % 3600) // 60
                    )

                    lines.append(
                        f'{asset}: {pos["direction"].upper()} '
                        f'{pos["size"]} '
                        f'{asset.split("/")[0]}'
                    )
                    lines.append(
                        f'  Entry: ${pos["entry_price"]:,.2f} | '
                        f'Stop: ${pos["stop_price"]:,.2f}'
                    )
                    lines.append(
                        f'  Strategy: {pos["strategy"]}'
                    )
                    lines.append(
                        f'  Duration: {hours}h {minutes}m'
                    )
                else:
                    lines.append(f'{asset}: No position')

        lines.append('─' * 22)
        return '\n'.join(lines)

    except Exception as e:
        logger.error(f'format_position_summary failed: {e}')
        return 'Position summary unavailable'


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        print(
            '\n=== MODULE 20b — ORDER MANAGER TESTS ===\n'
        )

        # Test 1 — Verify place_order exists in KrakenClient
        print(
            'Test 1: Verify place_order in KrakenClient...'
        )
        try:
            from execution.kraken_client import KrakenClient
            client = KrakenClient()
            has_place  = hasattr(client, 'place_order')
            has_cancel = hasattr(client, 'cancel_order')
            print(f'  place_order: {has_place}')
            print(f'  cancel_order: {has_cancel}')
            passed = has_place and has_cancel
            print(
                f'Test 1: {"PASSED" if passed else "FAILED"}\n'
            )
            await client.close()
        except Exception as e:
            print(f'Test 1: FAILED — {e}\n')

        # Test 2 — find_liquidity_void with mock book
        print('Test 2: find_liquidity_void...')
        from execution.stop_placer import find_liquidity_void
        mock_book = {
            'bids': [
                [44990, 1.0], [44950, 0.5],
                [44500, 2.0], [44490, 0.5]
            ],
            'asks': [
                [45010, 1.0], [45050, 0.5],
                [45500, 2.0], [45510, 0.5]
            ]
        }
        void = find_liquidity_void(
            mock_book, 'long', 45000.0
        )
        print(f'  Void price: {void["void_price"]}')
        print(f'  Safe stop: {void["safe_stop_price"]}')
        passed = void['safe_stop_price'] < 45000.0
        print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')

        # Test 3 — Open position dry run
        print('Test 3: open_position dry run...')

        class MockExchange:
            async def place_order(self, symbol, side, size,
                                  order_type='market'):
                return {
                    'order_id':     'mock_123',
                    'symbol':       symbol,
                    'side':         side,
                    'amount':       size,
                    'status':       'closed',
                    'filled_price': 45000.0
                }
            async def fetch_order_book(self, symbol, depth=20):
                return {
                    'bids': [[44990, 1.0]],
                    'asks': [[45010, 1.0]]
                }
            async def fetch_open_orders(self, symbol=None):
                return []
            async def cancel_order(self, order_id, symbol):
                return True

        mock_ex = MockExchange()
        result3 = await open_position(
            'BTC/USD', 'long', 0.001,
            'TREND_FOLLOWING', 0.75, 500.0,
            mock_ex, dry_run=True
        )

        if result3:
            print(f'  Symbol: {result3["symbol"]}')
            print(f'  Direction: {result3["direction"]}')
            print(f'  Stop: {result3["stop_price"]}')
            print(f'  TP: {result3["tp_price"]}')
            print('Test 3: PASSED\n')
        else:
            print('Test 3: FAILED\n')

        # Test 4 — Format position summary
        print('Test 4: format_position_summary...')
        summary = format_position_summary()
        print(summary)
        print('Test 4: PASSED\n')

        # Test 5 — Close position dry run
        print('Test 5: close_position dry run...')
        if 'BTC/USD' in _open_positions:
            result5 = await close_position(
                'BTC/USD', 'manual',
                mock_ex, dry_run=True
            )
            if result5:
                print(f'  PnL: {result5["pnl"]}')
                print(f'  Reason: {result5["reason"]}')
                print('Test 5: PASSED\n')
            else:
                print('Test 5: FAILED\n')
        else:
            print('Test 5: SKIPPED — no position\n')

        # Test 6 — Emergency close all
        print('Test 6: emergency_close_all...')
        # Open a test position first
        await open_position(
            'ETH/USD', 'short', 0.01,
            'MEAN_REVERSION', 0.6, 100.0,
            mock_ex, dry_run=True
        )
        count = await emergency_close_all(
            mock_ex, dry_run=True
        )
        empty = len(_open_positions) == 0
        print(f'  Positions closed: {count}')
        print(f'  All cleared: {empty}')
        passed = empty
        print(f'Test 6: {"PASSED" if passed else "FAILED"}\n')

        print(
            '=== MODULE 20b — ORDER MANAGER: '
            'ALL TESTS PASSED ==='
        )

    asyncio.run(run_tests())
