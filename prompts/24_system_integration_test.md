# Prompt 24 — System Integration Test

## CONTEXT
This is the final module — Module 24 of 24.
Module 23 Orchestrator must be complete and APPROVED
before starting this module.

This module does not create new code. It runs the
complete assembled system end to end and verifies
every component works together correctly before
any real money is deployed.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 24 — System Integration Test
All integration tests: [show results]
System cleared for live trading: YES or NO

Do not proceed to live trading until user types:
APPROVED — GO LIVE

## PURPOSE
Run a complete end to end verification of the entire
trading system. Test every module working together
as one unified system. Identify any integration
issues before real money is at risk.

## INTEGRATION TEST SEQUENCE
Run all tests in this exact order.
Every test must pass before proceeding to the next.
If any test fails stop and report the exact failure.

## PHASE 1 — ENVIRONMENT VERIFICATION

### Test 1.1 — Environment Variables
Verify all required .env variables are present:
- KRAKEN_API_KEY
- KRAKEN_API_SECRET
- KRAKEN_CANCEL_KEY
- KRAKEN_CANCEL_SECRET
- TELEGRAM_BOT_TOKEN
- TELEGRAM_AUTHORISED_USER_ID
- ENVIRONMENT
Print each variable as PRESENT or MISSING
All must be PRESENT to continue

### Test 1.2 — Package Imports
Import every module in the system:
- All core modules (hurst, autocorr, pec, rvr,
  edge_score, sentiment)
- All risk modules (position_sizer, drawdown_guard,
  strategy_silo, correlation_breaker, time_filters)
- All execution modules (kraken_client, order_manager,
  stop_placer)
- All strategy modules (trend_following,
  mean_reversion, scalper)
- All sentinel modules
- All backtest modules
- All telegram modules
- All dead mans switch modules
- orchestrator and scheduler
Print each import as PASS or FAIL
All must be PASS to continue

### Test 1.3 — Database Initialisation
Run init_db for all modules that use databases:
- drawdown_guard.init_db
- strategy_silo.init_db
- correlation_breaker.init_db
- ohlcv_fetcher.init_database
Print each as PASS or FAIL

## PHASE 2 — EXCHANGE CONNECTIVITY

### Test 2.1 — Public API Connection
Fetch BTC/USD OHLCV data
Fetch BTC/USD order book
Verify data returned correctly
Print PASS or FAIL

### Test 2.2 — Authenticated API Connection
Fetch account balance using KRAKEN_API_KEY
Verify balance returned without error
Print balance and PASS or FAIL

### Test 2.3 — Cancel Only API Connection
Connect using KRAKEN_CANCEL_KEY
Fetch open orders list
Verify connection works
Print PASS or FAIL
Note: this is the dead mans switch key

### Test 2.4 — Historical Data Check
Check how many candles exist in database
for each of the 5 assets
If fewer than 100 candles for any asset:
  Run fetch_historical for that asset (30 days)
Print candle counts per asset

## PHASE 3 — DECISION ENGINE VERIFICATION

### Test 3.1 — Individual Signal Tests
Load BTC/USD last 200 candles from database
Run each signal independently:
- hurst.calculate — print H value
- autocorrelation.calculate — print value
- pec.calculate — print value
- rvr.calculate — print value
Print each as PASS or FAIL

### Test 3.2 — Composite Edge Score
Run edge_score.calculate on BTC/USD data
Print full output dictionary
Verify primary_strategy is not None
Verify position_size_factor between 0 and 1
Print PASS or FAIL

### Test 3.3 — All Assets Edge Scores
Run edge_score.calculate_all for all 5 assets
Print get_summary output
Verify each asset returns a result
Print PASS or FAIL

### Test 3.4 — Structural Sentiment
Run sentiment.calculate_all for all 5 assets
Print get_summary output
Verify each asset returns BULLISH BEARISH or NEUTRAL
Print PASS or FAIL

## PHASE 4 — RISK SYSTEM VERIFICATION

### Test 4.1 — Position Sizer
Load BTC/USD data
Run position_sizer.calculate with:
  asset_capital = 350.0 (test account size)
  edge_score = 0.70
  rvr_multiplier = 1.0
Print final_size and final_size_usd
Verify final_size_usd less than 350.0
Print PASS or FAIL

### Test 4.2 — Drawdown Guard
Run drawdown_guard.update with value 350.0
Run is_trading_allowed
Verify allowed = True on fresh account
Print PASS or FAIL

### Test 4.3 — Strategy Silos
Run is_active for all 15 silos:
  5 assets × 3 strategies
Verify all return active = True on fresh start
Print PASS or FAIL

### Test 4.4 — Correlation Breaker
Load last 100 candles for all 5 assets
Run correlation_breaker.check
Print avg_correlation and status
Print PASS or FAIL

### Test 4.5 — Time Filters
Run is_settlement_window
Run is_weekend
Run get_size_multiplier
Print current time filter status
Print PASS or FAIL

## PHASE 5 — SENTINEL VERIFICATION

### Test 5.1 — Order Book Monitor
Fetch live BTC/USD order book
Run sentinel.check_all_filters on real order book
Print green_light status and any alerts
Print PASS or FAIL

### Test 5.2 — Individual Sentinel Checks
Run each check independently:
- spoof_detector result
- liquidity_monitor gap check
- spread check
- depth check
Print each result
Print PASS or FAIL

## PHASE 6 — STRATEGY VERIFICATION

### Test 6.1 — Trend Following Signal
Load BTC/USD last 200 candles
Run trend_following.calculate_entry_signal with:
  edge_score from Test 3.2
  sentiment from Test 3.4
Print direction and confidence
Print PASS or FAIL

### Test 6.2 — Mean Reversion Signal
Load ETH/USD last 200 candles
Run mean_reversion.calculate_entry_signal
Print direction and confidence
Print PASS or FAIL

### Test 6.3 — Scalper Signal
Load BTC/USD last 20 candles
Run scalper.calculate_scalp_signal
Print direction and confidence
Print PASS or FAIL

## PHASE 7 — ORDER MANAGEMENT VERIFICATION

### Test 7.1 — Open Positions Check
Run order_manager.get_open_positions
Print current open positions
Should be empty on fresh start
Print PASS or FAIL

### Test 7.2 — Format Position Summary
Run order_manager.format_position_summary
Print output
Print PASS or FAIL

### Test 7.3 — Stop Placer
Fetch BTC/USD order book
Run stop_placer.find_liquidity_void
Print void_price and safe_stop_price
Print PASS or FAIL

## PHASE 8 — TELEGRAM VERIFICATION

### Test 8.1 — Send Integration Test Message
Send this exact message to Telegram:
  INTEGRATION TEST — [current UTC time]
  ─────────────────────────────────────
  All 24 modules loaded successfully
  Exchange connected: YES
  Database initialised: YES
  Decision Engine: OPERATIONAL
  Risk Systems: OPERATIONAL
  Strategies: OPERATIONAL
  Sentinel: OPERATIONAL
  Telegram: OPERATIONAL
  ─────────────────────────────────────
  System ready for live trading
  Awaiting APPROVED — GO LIVE command

Print Message sent to Telegram: PASS or FAIL

### Test 8.2 — Alert Functions
Test each alert function with mock data:
- send_trade_opened
- send_trade_closed
- send_drawdown_alert
- send_status_update
Print each as formatted correctly: PASS or FAIL

## PHASE 9 — BACKTEST VERIFICATION

### Test 9.1 — Run Short Backtest
Run backtest.engine.run_backtest on BTC/USD:
  start_date = 30 days ago
  end_date = today
  initial_capital = 10000.0
Print metrics:
  Total trades
  Win rate
  Sharpe ratio
  Max drawdown
Print PASS or FAIL

### Test 9.2 — Run Stress Tests
Run backtest.stress_test.run_all_stress_tests
Print results for each scenario
All must pass
Print PASS or FAIL

### Test 9.3 — Walk Forward Validation
Run backtest.engine.run_walk_forward on BTC/USD
Print test period metrics
Print PASS or FAIL

## PHASE 10 — DEAD MANS SWITCH VERIFICATION

### Test 10.1 — Heartbeat Write and Read
Run write_heartbeat
Run read_heartbeat
Verify timestamp matches
Print PASS or FAIL

### Test 10.2 — Heartbeat Alive Check
Run check_heartbeat_alive
Verify returns True on fresh heartbeat
Print PASS or FAIL

### Test 10.3 — Cancel Only Connection
Verify KRAKEN_CANCEL_KEY connects correctly
Verify it can fetch open orders
Print PASS or FAIL

## PHASE 11 — FULL SYSTEM DRY RUN

### Test 11.1 — Single Asset Cycle
Run orchestrator.run_asset_cycle on BTC/USD
With dry_run = True throughout
Print every step completed
Print total cycle time in milliseconds
Print PASS or FAIL

### Test 11.2 — All Assets Cycle
Run orchestrator.run_main_loop once
With dry_run = True
Print results for all 5 assets
Print total loop time
Print PASS or FAIL

### Test 11.3 — Scheduler Registration
Create scheduler
List all registered jobs with their intervals
Verify all 8 scheduled jobs are registered
Stop scheduler
Print PASS or FAIL

## FINAL INTEGRATION REPORT

After all tests complete print this report:

SYSTEM INTEGRATION REPORT
══════════════════════════
Date: [current UTC date and time]
Environment: [BACKTEST or LIVE]
Account Size: $350.00

PHASE RESULTS:
Phase 1 — Environment: PASS or FAIL
Phase 2 — Exchange: PASS or FAIL
Phase 3 — Decision Engine: PASS or FAIL
Phase 4 — Risk Systems: PASS or FAIL
Phase 5 — Sentinel: PASS or FAIL
Phase 6 — Strategies: PASS or FAIL
Phase 7 — Order Management: PASS or FAIL
Phase 8 — Telegram: PASS or FAIL
Phase 9 — Backtest: PASS or FAIL
Phase 10 — Dead Mans Switch: PASS or FAIL
Phase 11 — Full System Dry Run: PASS or FAIL
══════════════════════════
OVERALL RESULT: ALL PASSED or FAILED

If ALL PASSED print:
══════════════════════════
SYSTEM CLEARED FOR LIVE TRADING
Change ENVIRONMENT=live in .env file
Run: python orchestrator.py
Monitor via Telegram
Good luck Belinda
══════════════════════════

If ANY FAILED print:
══════════════════════════
SYSTEM NOT CLEARED FOR LIVE TRADING
Failed phases: [list failed phases]
Fix all failures before going live
══════════════════════════

## SAVE REPORT
Save the complete integration report to:
logs/integration_test_report.txt
Print Report saved to logs/integration_test_report.txt

## SUCCESS CRITERIA
Every single phase must pass.
No exceptions. No partial passes.
The system either passes completely or it does not.

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 24 — System Integration Test
Overall result: ALL PASSED or FAILED
Failed phases: [list any failures]
Report saved: logs/integration_test_report.txt

Type APPROVED — GO LIVE to begin live trading
or
Type FIX [phase number] to address failures

## IMPORTANT FINAL INSTRUCTIONS
- This module creates no new Python files
- It only runs existing code end to end
- All tests use dry_run = True
- No real orders placed during integration test
- Real API calls are made for data fetching only
- If Phase 2 exchange tests fail check .env keys
- If Phase 3 decision engine fails check core modules
- If Phase 9 backtest fails ensure 5 years of data
  has been downloaded first using:
  python data/ohlcv_fetcher.py fetch_all_historical
- The integration test must be run fresh on the
  Oracle VPS or Railway deployment server
  not just on the development machine
- Only after APPROVED — GO LIVE is typed should
  ENVIRONMENT be changed to live in .env
