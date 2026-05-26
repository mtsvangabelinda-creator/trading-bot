# Prompt 20 — Order Manager

## CONTEXT
This is Module 20 of 24. Module 19 Stress Tester must be
complete and APPROVED before starting this module.

IMPORTANT: This module restores full automated execution.
The Kraken API keys are verified and working. This module
adds back order placement and cancellation that was
temporarily removed from Module 01.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 20 — Order Manager
File created: execution/order_manager.py
execution/stop_placer.py
kraken_client.py updated with place_order
and cancel_order
Test results: [show actual output]
Type APPROVED to proceed to Module 21 — Telegram Bot

Do not proceed until user types: APPROVED

## FILES TO CREATE OR UPDATE

### UPDATE: execution/kraken_client.py
Add these two functions to the existing KrakenClient
class. Do NOT change any existing functions.

#### place_order
- Inputs:
  symbol (str)
  side (str) — buy or sell
  amount (float) — quantity to trade
  order_type (str) = 'market'
- Output: dictionary with keys:
  order_id (str)
  symbol (str)
  side (str)
  amount (float)
  status (str)
  timestamp (datetime)
  filled_price (float)
- Use authenticated ccxt instance
- Retry up to RETRY_COUNT times on failure
- Log every order to logs/trades.log
- Return None on failure

#### cancel_order
- Inputs: order_id (str), symbol (str)
- Output: True if cancelled, False if failed
- Use authenticated ccxt instance
- Log every cancellation to logs/trades.log
- Return False on failure

### CREATE: execution/stop_placer.py

#### PURPOSE
Places stop-loss orders outside known liquidity voids.
Ensures stops are never placed inside thin order book
areas where price can gap through without filling.

#### FUNCTIONS

##### 1. find_liquidity_void
- Inputs:
  order_book (dict from kraken_client.fetch_order_book)
  direction (str) — long or short
  current_price (float)
  search_range_pct (float) = 0.05
- For long positions look at bids below current price
- For short positions look at asks above current price
- Find the largest gap between consecutive price levels
- Output: dictionary with keys:
  void_price (float) — price of the gap
  void_size_pct (float) — size of gap as percentage
  safe_stop_price (float) — recommended stop price
    placed just beyond the void

##### 2. calculate_safe_stop
- Inputs:
  symbol (str)
  direction (str)
  entry_price (float)
  atr (float)
  exchange — KrakenClient instance
- Fetches order book
- Finds liquidity void
- Compares void-based stop with ATR-based stop
- Takes the more conservative (wider) stop
- Output: float — the safe stop price

##### 3. place_stop_loss
- Inputs:
  symbol (str)
  stop_price (float)
  size (float)
  direction (str)
  exchange — KrakenClient instance
  dry_run (bool) = False
- Places stop-market order on Kraken
- For long: sell stop at stop_price
- For short: buy stop at stop_price
- Output: dictionary with order details
- Return None on failure

##### 4. place_take_profit
- Inputs:
  symbol (str)
  tp_price (float)
  size (float)
  direction (str)
  exchange — KrakenClient instance
  dry_run (bool) = False
- Places limit order at take profit price
- For long: sell limit at tp_price
- For short: buy limit at tp_price
- Output: dictionary with order details
- Return None on failure

##### 5. cancel_all_stops
- Inputs:
  symbol (str)
  exchange — KrakenClient instance
- Fetches all open orders for symbol
- Cancels all stop orders
- Used by emergency close function
- Output: integer count of cancelled orders

### CREATE: execution/order_manager.py

#### PURPOSE
Orchestrates the complete trade lifecycle from signal
to execution to exit. Connects the Decision Engine
output directly to Kraken order placement. Manages
open positions and monitors for exit conditions.

#### POSITION TRACKING
Maintain an in-memory dictionary of open positions:
{
  'BTC/USD': {
    'direction': 'long',
    'entry_price': 45000.0,
    'size': 0.0987,
    'stop_price': 44200.0,
    'tp_price': 46500.0,
    'strategy': 'TREND_FOLLOWING',
    'entry_time': datetime,
    'stop_order_id': str,
    'tp_order_id': str,
    'edge_score': 0.74
  }
}

#### FUNCTIONS

##### 1. open_position
- Inputs:
  symbol (str)
  direction (str) — long or short
  size (float)
  strategy (str)
  edge_score (float)
  atr (float)
  exchange — KrakenClient instance
  tp_multiplier (float) = 2.0
- Process:
  Place market order via kraken_client.place_order
  Calculate safe stop via stop_placer.calculate_safe_stop
  Calculate take profit: entry ± (ATR × tp_multiplier)
  Place stop loss via stop_placer.place_stop_loss
  Place take profit via stop_placer.place_take_profit
  Store position in open positions dictionary
- Output: dictionary with full position details
- Return None if any step fails

##### 2. close_position
- Inputs:
  symbol (str)
  reason (str) — stop_hit, take_profit, manual,
    emergency
  exchange — KrakenClient instance
- Process:
  Cancel existing stop and take profit orders
  Place market order in opposite direction to close
  Calculate final PnL
  Remove from open positions dictionary
  Record trade in strategy silo
  Update drawdown guard
- Output: dictionary with keys:
  pnl (float)
  reason (str)
  entry_price (float)
  exit_price (float)
  duration (timedelta)

##### 3. check_open_positions
- Input: exchange — KrakenClient instance
- For each open position:
  Fetch latest price
  Check if stop or take profit has been hit
  If hit: call close_position
- Returns list of positions closed this cycle

##### 4. get_open_positions
- No inputs
- Returns copy of open positions dictionary
- Used by Telegram bot for status reporting

##### 5. emergency_close_all
- Input: exchange — KrakenClient instance
- Closes ALL open positions immediately
- Cancels ALL open orders
- Clears open positions dictionary
- Logs emergency close event
- Returns count of positions closed

##### 6. format_position_summary
- No inputs
- Output: formatted string for Telegram:

  OPEN POSITIONS
  ──────────────
  BTC/USD: LONG 0.0987 BTC
  Entry: $45,000 | Stop: $44,200
  Current PnL: +$127.50
  Strategy: Trend-Following
  Duration: 2h 34m
  ──────────────
  ETH/USD: No position
  SOL/USD: No position
  BNB/USD: No position
  XRP/USD: No position

## ERROR HANDLING
- Every function wrapped in try/except
- If order placement fails log error and return None
- Never leave a position open without a stop loss
- If stop placement fails after entry:
  immediately close the position and log critical error
- Log all orders to logs/trades.log
- Log all errors to logs/errors.log

## LOGGING
- Every order placed logged with full details
- Every position opened and closed logged
- PnL logged for every closed trade
- Emergency closes logged as CRITICAL level

## TEST
At bottom of order_manager.py in
if __name__ == '__main__': block:

1. Test kraken_client place_order addition:
   Initialise KrakenClient
   Verify place_order function exists
   Print place_order function found: PASS or FAIL

2. Test find_liquidity_void with mock order book:
   Create mock order book with obvious gap
   Run find_liquidity_void
   Print void_price and safe_stop_price
   Print PASS or FAIL

3. Test calculate_safe_stop with mock data:
   ATR = 500 (BTC-like)
   Entry = 45000
   Direction = long
   Print recommended stop price

4. Test open_position with dry_run simulation:
   Create mock exchange that returns fake order IDs
   Call open_position with test parameters
   Print position details
   Verify stop and take profit calculated

5. Test format_position_summary:
   Add mock position to open positions dict
   Print formatted summary

6. Test emergency_close_all with mock exchange:
   Add 2 mock positions
   Call emergency_close_all
   Verify open positions dict is empty
   Print PASS or FAIL

7. Print MODULE 20 — ORDER MANAGER:
   ALL TESTS PASSED if all criteria met

## SUCCESS CRITERIA
- place_order successfully added to KrakenClient
- cancel_order successfully added to KrakenClient
- find_liquidity_void correctly identifies gaps
- open_position places entry, stop, and take profit
- close_position calculates correct PnL
- emergency_close_all empties all positions
- No position ever left without a stop loss

## IMPORTANT FINAL INSTRUCTIONS
- Create files at exactly these paths:
  execution/order_manager.py
  execution/stop_placer.py
- Update execution/kraken_client.py by ADDING
  place_order and cancel_order to existing class
  Do NOT rewrite the existing file
- dry_run parameter defaults to False for
  live trading
- All order placement must use authenticated
  Kraken API via KrakenClient
- Stop loss placement is MANDATORY after every
  entry — never skip it
- If stop placement fails after a successful
  entry immediately close the position
