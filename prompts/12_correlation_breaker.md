# Prompt 12 – Correlation Breaker

## CONTEXT
Module 11 Strategy Silo must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 12 – Correlation Breaker
File created: risk/correlation_breaker.py
Test results: [show actual output]
Type APPROVED to proceed to Module 13 – Time Filters

Do not proceed until user types: APPROVED.

## FILE TO CREATE
risk/correlation_breaker.py

## PURPOSE
Monitors pairwise correlations between all five assets (BTC, ETH, SOL, BNB, XRP) using 4-hour returns. Reduces total exposure or pauses trading when diversification collapses, per spec rules.

## RULES FROM SPEC
- Average pairwise correlation > 0.8 → total exposure halved. Send alert.
- Correlation stays above 0.8 for 24 hours → all trading pauses until correlation drops below 0.7.
- Check every 4 hours.

## DEPENDENCIES
- numpy, pandas, aiosqlite, datetime, logging
- config.py: CORR_HALVE_THRESHOLD=0.8, CORR_PAUSE_THRESHOLD=0.7, CORR_CHECK_INTERVAL=14400
- data/trading_data.db (for price history)
- data/test_corr.db (testing)

## FUNCTIONS

1. init_db(db_path='data/trading_data.db')
   Creates table correlation_state with columns: last_check_time, avg_correlation, exposure_multiplier, pause_until, alert_sent_24h. Returns True.

2. fetch_4h_returns(db_path='data/trading_data.db')
   Gets latest 4-hour returns for all 5 assets from ohlcv data. Output: pandas DataFrame with assets as columns, returns as values.

3. calculate_pairwise_correlation(returns_df)
   Computes correlation matrix. Output: correlation matrix (numpy array) and average of all unique pairwise correlations.

4. update_and_check(db_path='data/trading_data.db')
   Main function called every 4 hours.
   - Fetch returns, compute avg correlation.
   - Load current state from correlation_state table.
   - If avg > 0.8: set exposure_multiplier = 0.5. If already >0.8 for 24 consecutive hours, set pause_until = now + until correlation <0.7.
   - If avg < 0.7 and pause active: lift pause.
   - Save new state.
   - Output dict: avg_correlation, exposure_multiplier, is_paused, pause_until, alert_message.

5. get_exposure_multiplier(db_path='data/trading_data.db')
   Returns current multiplier (1.0 normal, 0.5 halved). Used by position_sizer.

6. is_trading_allowed(db_path='data/trading_data.db')
   Returns bool – False if pause_until > now.

7. get_status(db_path='data/trading_data.db')
   Returns formatted string: "Avg Correlation: X.XX | Exposure: 50% | Paused: No" etc.

## ERROR HANDLING
- Try/except each function
- Log to logs/risk.log and logs/errors.log
- On fetch failure, use last known correlation (don't halt trading)

## TESTS (in if __name__ == '__main__':)
Use db_path='data/test_corr.db'

1. Init DB – print "Database initialised"
2. Test normal correlation (0.4) – exposure_multiplier should be 1.0, not paused. PASS/FAIL.
3. Test high correlation (0.85) – after first check, exposure_multiplier = 0.5, alert sent. PASS/FAIL.
4. Test sustained high correlation – simulate 24 hours (by manipulating timestamps) – should pause trading. PASS/FAIL.
5. Test recovery – correlation drops to 0.65 – pause lifts, exposure returns to 1.0. PASS/FAIL.
6. Print "MODULE 12 – CORRELATION BREAKER: ALL TESTS PASSED"
7. Delete test database after tests.

## SUCCESS CRITERIA
- Halves exposure at 0.8 threshold
- Pauses after 24h sustained high correlation
- Resumes when correlation <0.7
- All tests pass, test db deleted

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 12 – Correlation Breaker
File created: risk/correlation_breaker.py
Normal correlation test: PASS or FAIL
Halve exposure test: PASS or FAIL
24h pause test: PASS or FAIL
Recovery test: PASS or FAIL
Type APPROVED to proceed to Module 13 – Time Filters
