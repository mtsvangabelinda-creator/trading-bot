# Prompt 19 — Stress Tester

## CONTEXT
This is Module 19 of 24. Module 18 Backtest Engine must be
complete and APPROVED before starting this module.

IMPORTANT: Do NOT modify any existing modules. This module
only imports and tests them under extreme conditions.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 19 — Stress Tester
File created: backtest/stress_test.py
Test results: [show actual output]
Type APPROVED to proceed to Module 20 — Order Manager

Do not proceed until user types: APPROVED

## FILE TO CREATE
backtest/stress_test.py

## PURPOSE
Injects artificial market shocks into the system to verify
all safety mechanisms fire correctly before real money is
at risk. Tests the system under extreme conditions that
real backtesting may never encounter. If any safety system
fails a stress test the system must NOT go live.

## STRESS SCENARIOS TO TEST

### Scenario 1 — Flash Crash
30% BTC price drop in 10 minutes
Tests: Chaotic Tripwire fires, drawdown guard halts,
position sizer reduces to zero

### Scenario 2 — Sustained Crash
BTC drops 20% over 24 hours steadily
Tests: Peak drawdown halt fires at 15%, weekly loss
limit tracks correctly, strategy silos pause

### Scenario 3 — Exchange Downtime
Simulated 2 hour gap in price data
Tests: System handles missing candles gracefully,
does not crash, resumes correctly after gap

### Scenario 4 — Correlation Collapse
All 5 assets move together with correlation above 0.9
Tests: Correlation breaker halves exposure, then pauses
after 24 hours of sustained high correlation

### Scenario 5 — Liquidity Crisis
Bid-ask spread widens to 10x normal
Order book depth drops to near zero
Tests: Sentinel blocks all entries, no trades placed

### Scenario 6 — Consecutive Loss Streak
Trend-Following loses 4 trades in a row
Mean Reversion loses 6 trades in a row
Tests: Strategy silos pause correctly, other strategies
continue unaffected

### Scenario 7 — Black Swan
50% price drop in one candle
Tests: All safety systems fire simultaneously,
system does not crash, recovery mode activates

### Scenario 8 — News Blackout
High impact economic event in news calendar
Tests: Time filters block all entries during blackout
window, resume correctly after

## DEPENDENCIES
- from backtest.simulator import simulate_market_order
- from backtest.simulator import calculate_pnl
- from backtest.metrics import calculate_all_metrics
- from core.edge_score import calculate as edge_calc
- from core.rvr import chaotic_tripwire
- from risk.drawdown_guard import update as dd_update
- from risk.drawdown_guard import is_trading_allowed
- from risk.strategy_silo import register_trade_outcome
- from risk.strategy_silo import is_active
- from risk.correlation_breaker import check
- from risk.time_filters import is_trading_allowed as tf_allowed
- from sentinel.sentinel import check_all_filters
- numpy, pandas, logging, datetime
- config.py for all constants

## NO CLASS — plain functions only

## FUNCTIONS TO BUILD

### 1. generate_flash_crash
- Inputs:
  base_price (float) = 45000
  candles_before (int) = 100
  crash_pct (float) = 0.30
  crash_candles (int) = 10
- Generates realistic OHLCV DataFrame:
  Normal trending prices for candles_before
  Then drops crash_pct in crash_candles candles
  Then stabilises
- Output: pandas DataFrame with columns:
  timestamp, open, high, low, close, volume

### 2. generate_sustained_crash
- Inputs:
  base_price (float) = 45000
  candles_before (int) = 100
  crash_pct (float) = 0.20
  crash_candles (int) = 1440
- Steady decline over crash_candles candles
- Output: pandas DataFrame

### 3. generate_data_gap
- Inputs:
  base_price (float) = 45000
  gap_candles (int) = 120
- Normal data with gap_candles missing in middle
- Output: pandas DataFrame with NaN rows for gap

### 4. generate_high_correlation_data
- Inputs:
  base_price (float) = 45000
  candles (int) = 200
  correlation (float) = 0.95
- Generates 5 asset price series all moving together
- Output: dictionary of asset name to pandas Series

### 5. generate_liquidity_crisis
- Inputs:
  base_price (float) = 45000
  candles (int) = 50
- Wide spreads and thin order book
- Output: dictionary with:
  ohlcv (DataFrame)
  order_book (dict with bids and asks nearly empty)
  spread_ratio (float) — how many times normal spread

### 6. generate_consecutive_losses
- Inputs:
  strategy (str) — TREND_FOLLOWING or MEAN_REVERSION
  loss_count (int)
  loss_amount (float) = 50.0
- Returns list of PnL values all negative

### 7. generate_black_swan
- Inputs:
  base_price (float) = 45000
  drop_pct (float) = 0.50
- Single candle 50% drop
- Output: pandas DataFrame

### 8. run_flash_crash_test
- Generates flash crash data
- Runs chaotic_tripwire on the data
- Runs drawdown_guard update with simulated losses
- Runs edge_score calculate on crash candles
- Checks all safety systems fired correctly
- Output: dictionary with keys:
  tripwire_fired (boolean)
  drawdown_halted (boolean)
  position_size_zero (boolean)
  passed (boolean)
  details (string)

### 9. run_sustained_crash_test
- Simulates 20% sustained crash over 24 hours
- Tracks drawdown through entire period
- Verifies peak halt fires at 15%
- Verifies weekly loss limit tracks correctly
- Output: dictionary with passed (boolean) and details

### 10. run_data_gap_test
- Generates data with gap
- Runs edge_score on gapped data
- Verifies no crash — graceful handling
- Output: dictionary with passed (boolean) and details

### 11. run_correlation_test
- Generates high correlation data
- Runs correlation_breaker.check
- Verifies exposure halved at 0.8 threshold
- Output: dictionary with passed (boolean) and details

### 12. run_consecutive_loss_test
- Generates 4 TF losses and 6 MR losses
- Runs register_trade_outcome for each
- Verifies silos pause at correct thresholds
- Verifies other strategies unaffected
- Output: dictionary with passed (boolean) and details

### 13. run_black_swan_test
- Generates 50% single candle drop
- Runs all safety systems
- Verifies system does not crash
- Output: dictionary with passed (boolean) and details

### 14. run_all_stress_tests
- Runs all stress test functions in sequence
- Prints results for each scenario
- Output: dictionary of scenario name to result
- Prints final summary:

  STRESS TEST RESULTS
  ───────────────────
  Flash Crash: PASSED
  Sustained Crash: PASSED
  Data Gap: PASSED
  Correlation Collapse: PASSED
  Consecutive Losses: PASSED
  Black Swan: PASSED
  ───────────────────
  ALL STRESS TESTS PASSED
  System cleared for live trading

### 15. generate_stress_report
- Input: results from run_all_stress_tests
- Output: formatted string suitable for saving
  as a report file
- Include timestamp, all results, recommendations

## ERROR HANDLING
- Every function wrapped in try/except
- If a stress test itself crashes that is a FAIL
- Log all results to logs/stress_test.log
- Never modify production database during tests
- Use separate test database if needed:
  data/test_stress.db

## TEST
At bottom in if __name__ == '__main__': block:

1. Run generate_flash_crash and print:
   Number of candles generated
   Lowest price in crash period
   Confirm 30% drop achieved
   Print PASS or FAIL

2. Run run_flash_crash_test and print:
   tripwire_fired value
   drawdown_halted value
   passed value
   Full details string

3. Run generate_black_swan and print:
   The crash candle OHLCV values
   Confirm 50% drop in single candle

4. Run run_consecutive_loss_test and print:
   Whether TF paused after 4 losses
   Whether MR paused after 6 losses
   Whether Scalper remained active

5. Run run_all_stress_tests:
   Print complete results for all scenarios
   Print final summary

6. Run generate_stress_report and save to:
   logs/stress_test_report.txt
   Print Report saved successfully

7. Print MODULE 19 — STRESS TESTER:
   ALL TESTS PASSED only if all scenarios pass

## SUCCESS CRITERIA
ALL of the following must pass before system
is cleared for live trading:

- Chaotic Tripwire fires on flash crash
- Drawdown guard halts at 15% peak loss
- Strategy silos pause at correct thresholds
- Correlation breaker halves exposure at 0.8
- System handles data gaps without crashing
- Black swan does not crash the system
- Stress report saved to logs folder

## IMPORTANT FINAL INSTRUCTIONS
- Create file at exactly this path:
  backtest/stress_test.py
- Do NOT modify any existing modules
- Use synthetic generated data only
  never use production database for stress tests
- All stress scenarios must run automatically
  no manual intervention required
- If ANY scenario fails print clearly which
  scenario failed and why
- System must NOT be cleared for live trading
  if any stress test fails
