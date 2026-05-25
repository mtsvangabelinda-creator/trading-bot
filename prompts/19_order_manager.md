# Prompt 19 – Order Manager & Execution

## CONTEXT
Module 18 Decision Engine must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 19 – Order Manager & Execution
Files created: execution/order_manager.py, execution/stop_placer.py, execution/kraken_client.py (if not already from Module 01 – but here we enhance)
Test results: [show actual output]
Type APPROVED to proceed to Module 20 – Scheduler & Orchestrator

Do not proceed until user types: APPROVED.

## FILES TO CREATE
execution/order_manager.py
execution/stop_placer.py
execution/kraken_client.py (or augment existing if Module 01 was created)

## PURPOSE
Manages order placement, cancellation, and modification for all strategies. Handles market orders, limit orders, stop-loss orders, and take-profit orders. Implements rate limiting and error recovery for Kraken exchange. Provides a unified interface for strategy modules to place trades without worrying about exchange-specific details.

## RULES FROM SPEC
- API keys: withdrawals disabled, IP whitelisted to server only
- Orders must respect exchange rate limits (ccxt handles but we add local queue)
- Stop-loss always placed outside known liquidity voids (already handled by strategy)
- Dead man's switch (Module 22) will have separate cancel-only key; order manager should support cancelling all open orders.

## DEPENDENCIES
- ccxt (kraken client)
- logging, time, threading (or asyncio – we'll use synchronous for simplicity, but can be async later)
- config.py: exchange settings (name, sandbox_mode, api keys via .env)
- data/trading_data.db for order logging

## kraken_client.py

### FUNCTIONS
1. get_exchange(sandbox=True)
   - Returns configured ccxt binance (or kraken) instance with API keys from environment.
   - For Kraken testnet: use kraken futures testnet? Or just use sandbox mode via ccxt's enableRateLimit and set_sandbox_mode.
   - We'll use ccxt.binance testnet as earlier but adapt to kraken if needed. For simplicity, use binance testnet for development (more stable). User can change config.
   - Output: exchange object.

2. fetch_balance_safe(exchange, retries=3)
   - Wrapper with error handling and retries.

3. market_order_safe(exchange, symbol, side, amount, retries=2)
   - Returns order dict or None on failure.

4. limit_order_safe(exchange, symbol, side, amount, price, retries=2)
   - Returns order dict.

5. cancel_order_safe(exchange, order_id, symbol, retries=2)

6. fetch_open_orders_safe(exchange, symbol=None)

## order_manager.py

### FUNCTIONS
1. init_order_db(db_path='data/trading_data.db')
   - Creates table orders: id, timestamp, strategy, symbol, side, order_type, size, price, status, filled_size, filled_price, exchange_order_id.

2. log_order(order_details, db_path)
   - Inserts order into database.

3. update_order_status(order_id, new_status, filled_price=None, filled_size=None, db_path)

4. place_market_order(strategy, symbol, side, size_usd, exchange, db_path, dry_run=True)
   - Converts USD to asset amount using current market price.
   - Places order, logs result.
   - Returns dict: success, order_id, filled_price, actual_size, error.

5. place_limit_order(strategy, symbol, side, size_usd, limit_price, exchange, db_path, dry_run=True)

6. place_stop_order(strategy, symbol, side, stop_price, size_usd, exchange, db_path, dry_run=True)
   - For stop-loss: usually a stop-market order. Kraken supports stop-loss orders via `stopLoss` order type.
   - Returns order details.

7. cancel_all_orders(symbol=None, exchange, db_path)
   - Cancels all open orders, optionally for a specific symbol.
   - Returns count cancelled.

8. get_open_orders_summary(symbol=None, exchange, db_path)
   - Returns list of open orders with details.

## stop_placer.py

### FUNCTIONS
1. attach_stop_loss(primary_order_id, stop_price, side, size, exchange, db_path, dry_run=True)
   - Places a stop-loss order linked to an existing position. In practice, you can place stop-loss immediately after market order.
   - Returns stop order details.

2. attach_take_profit(primary_order_id, target_price, side, size, exchange, db_path, dry_run=True)

3. update_stop_loss(order_id, new_stop_price, exchange, db_path)

4. remove_stop_loss(order_id, exchange, db_path)

## ERROR HANDLING
- Every order function wraps in try/except, logs error, returns failure dict.
- Retry logic on temporary exchange errors (rate limits, connection issues).
- Log all order events to logs/execution.log.

## TESTS (in if __name__ == '__main__':)
Use dry_run=True (no real orders) or use sandbox exchange.

1. Test kraken_client initialization – exchange object created, sandbox mode True. PASS/FAIL.
2. Test market order dry run – returns success with mock filled price. PASS/FAIL.
3. Test limit order dry run. PASS/FAIL.
4. Test stop order creation. PASS/FAIL.
5. Test cancel all orders dry run. PASS/FAIL.
6. Test order logging and retrieval – insert order, query by id, verify status update. PASS/FAIL.
7. Print "MODULE 19 – ORDER MANAGER & EXECUTION: ALL TESTS PASSED"

## SUCCESS CRITERIA
- Exchange client connects to sandbox
- Market, limit, stop orders can be placed (dry-run or sandbox)
- Orders logged to database
- Cancel functionality works
- Stop/take-profit attachments functional

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 19 – Order Manager & Execution
Files created: execution/order_manager.py, stop_placer.py, kraken_client.py
Client init test: PASS or FAIL
Market order test: PASS or FAIL
Stop order test: PASS or FAIL
Cancel test: PASS or FAIL
DB logging test: PASS or FAIL
Type APPROVED to proceed to Module 20 – Scheduler & Orchestrator
