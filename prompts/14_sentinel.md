# Prompt 14 – Sentinel (Order Book Monitor)

## CONTEXT
Module 13 Time Filters must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 14 – Sentinel
File created: sentinel/sentinel.py, sentinel/spoof_detector.py, sentinel/liquidity_monitor.py
Test results: [show actual output]
Type APPROVED to proceed to Module 15 – Trend Following Strategy

Do not proceed until user types: APPROVED.

## FILES TO CREATE
sentinel/sentinel.py
sentinel/spoof_detector.py
sentinel/liquidity_monitor.py

## PURPOSE
Real-time order book monitor that gives green/red light before any trade. Checks for spoofing, liquidity gaps, abnormal spread, depth sufficiency, and volume dry-up. Red light = position size zero regardless of other signals.

## RULES FROM SPEC
- Fake orders (spoofing): large orders that disappear before execution
- Liquidity gaps: thin areas where price can crash through
- Abnormal spread: bid-ask spread exceeds 2x its 4-hour average
- Depth check: enough depth within 0.5% of price for <0.3% slippage
- Volume dry-up: no entries within 5 minutes of sudden liquidity collapse

## DEPENDENCIES
- ccxt (kraken client from Module 01)
- numpy, time, logging, collections.deque
- config.py: SPREAD_MULTIPLIER=2.0, SLIPPAGE_TOLERANCE=0.003, LIQUIDITY_DEPTH_PCT=0.005, VOLUME_DRYUP_SECS=300
- data/trading_data.db (optional logging)

## spoof_detector.py

### FUNCTIONS
1. detect_spoof_orderbook(symbol, exchange, threshold_ratio=0.3, lookback_seconds=10)
   - Fetches order book snapshot
   - Tracks large orders (>2x median size) that appear then disappear within lookback seconds
   - Returns dict: {'spoof_detected': bool, 'suspicious_orders': int, 'confidence': float}

## liquidity_monitor.py

### FUNCTIONS
1. check_liquidity_gaps(symbol, exchange, depth_pct=0.005)
   - Fetches order book bids/asks
   - Finds largest price gap between consecutive levels within depth_pct of mid price
   - Returns dict: {'has_gap': bool, 'gap_percent': float, 'gap_location': str}

2. check_spread_abnormal(symbol, exchange, spread_multiplier=2.0, lookback_hours=4)
   - Gets current spread (ask-bid)/mid
   - Fetches historical spread from last 4h (store in deque)
   - Returns dict: {'is_abnormal': bool, 'current_spread': float, 'avg_spread': float, 'ratio': float}

3. check_depth_sufficiency(symbol, exchange, order_amount_usd, slippage_tolerance=0.003, depth_pct=0.005)
   - Simulates market order of order_amount_usd
   - Checks cumulative depth within depth_pct of mid price
   - Calculates expected slippage
   - Returns dict: {'sufficient': bool, 'expected_slippage': float, 'depth_available_usd': float}

4. check_volume_dryup(symbol, exchange, lookback_seconds=300, volume_threshold_pct=0.2)
   - Trades volume from last lookback_seconds via exchange.fetch_trades()
   - Compares to average volume (same time window previous day)
   - Dry-up if current < volume_threshold_pct of normal
   - Returns dict: {'dryup': bool, 'current_volume': float, 'normal_volume': float}

## sentinel.py

### FUNCTIONS
1. init_sentinel_state(db_path='data/trading_data.db')
   - Optional: table for sentinel blocks logging
   - Returns True

2. check_all_filters(symbol, exchange, order_amount_usd, spoof_lookback_sec=10)
   - Runs all four monitors: spoof, gaps, spread, depth, volume dry-up
   - Returns dict: {
        'green_light': bool,
        'multiplier': float,  # 1.0 if green, 0.0 if red
        'alerts': list of strings (reasons for red),
        'details': {...}
     }

3. is_trade_allowed(symbol, exchange, order_amount_usd)
   - Wrapper that returns bool (True if green_light)

4. get_sentinel_status(symbol)
   - Returns formatted string for Telegram: "Sentinel: GREEN | Spread: 0.02% | Depth sufficient | No spoofing"

5. log_sentinel_block(symbol, reason, details, db_path='data/trading_data.db')
   - Logs every red light event

## ERROR HANDLING
- All functions try/except, return safe values (green_light=True only if confident)
- Log errors to logs/sentinel.log
- On exchange error, return neutral (green_light=True but log warning)

## TESTS (in if __name__ == '__main__':)
Use mock exchange or real testnet with fake data. For automated tests, create a mock order book.

1. Test spoof detection – inject fake large order that cancels – should detect. PASS/FAIL.
2. Test liquidity gap – build book with large gap – detects. PASS/FAIL.
3. Test spread abnormal – artificially widen spread >2x avg – detects. PASS/FAIL.
4. Test depth insufficient – small order book depth for given amount – returns sufficient=False. PASS/FAIL.
5. Test volume dry-up – simulate low volume period – detects. PASS/FAIL.
6. Test all clear – normal book – green_light=True, multiplier=1.0. PASS/FAIL.
7. Test any red light – green_light=False, multiplier=0.0. PASS/FAIL.
8. Print "MODULE 14 – SENTINEL: ALL TESTS PASSED"

## SUCCESS CRITERIA
- Each detector works independently
- Sentinel combines results correctly (red if any fails)
- Multiplier 0 on red, 1 on green
- Logs blocks

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 14 – Sentinel
Files created: sentinel/sentinel.py, spoof_detector.py, liquidity_monitor.py
Spoof detection: PASS or FAIL
Gap detection: PASS or FAIL
Spread abnormal: PASS or FAIL
Depth check: PASS or FAIL
Volume dry-up: PASS or FAIL
Combined green/red: PASS or FAIL
Type APPROVED to proceed to Module 15 – Trend Following Strategy
