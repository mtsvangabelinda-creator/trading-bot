# Prompt 11 – Strategy Silo

## CONTEXT
Module 10 Drawdown Guard must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 11 – Strategy Silo
File created: risk/strategy_silo.py
Test results: [show actual output]
Type APPROVED to proceed to Module 12 – Correlation Breaker

Do not proceed until user types: APPROVED.

## FILE TO CREATE
risk/strategy_silo.py

## PURPOSE
Manages three independent strategy silos (trend_following, mean_reversion, scalper). Each silo tracks its own capital, peak equity, consecutive losses, daily losses, and pause state. Enforces self-destruct rules from spec.

## RULES
- Trend-following: 4 consecutive losses → pause 24h, 10% drawdown from peak → pause 24h
- Mean reversion: 6 consecutive losses → pause 24h, 10% drawdown from peak → pause 24h
- Scalper: 5% daily loss → pause until next UTC midnight, no consecutive loss limit

## DEPENDENCIES
- aiosqlite, datetime, logging
- config.py: STRATEGY_DRAWDOWN=0.10, MR_CONSEC_LOSS_LIMIT=6, TF_CONSEC_LOSS_LIMIT=4, SCALPER_DAILY_LOSS=0.05
- data/trading_data.db, data/test_silo.db

## FUNCTIONS

1. init_db(db_path)
   Creates tables: strategy_silos, silo_trades. Returns True if success.

2. register_trade_outcome(strategy_name, pnl, db_path)
   Updates consecutive losses, daily loss, peak equity, checks pause conditions. Returns dict with paused, pause_reason, paused_until.

3. is_strategy_allowed(strategy_name, db_path)
   Returns bool – True if not paused.

4. get_silo_status(strategy_name, db_path)
   Returns dict: allocated_capital, peak_equity, drawdown_pct, consecutive_losses, daily_loss, paused_until, is_paused, pause_reason.

5. reset_daily_losses(db_path)
   Resets daily_loss for all silos if date changed. Called by scheduler.

6. update_equity(strategy_name, new_equity, db_path)
   Updates peak_equity and re-evaluates drawdown pause.

7. simulate_trade_sequence(strategy_name, pnls, db_path)
   Runs register_trade_outcome for each pnl, returns list of pause states.

## ERROR HANDLING
Try/except each function. Log to logs/risk.log and logs/errors.log.

## TESTS (in if __name__ == '__main__':)
Use db_path='data/test_silo.db'
1. Init DB – print "Database initialised"
2. Trend-following: 4 losses of -20 each → should pause after 4th. Print PASS/FAIL.
3. Mean reversion drawdown: from peak 1000 to 895 (10.5%) → pause. PASS/FAIL.
4. Scalper daily loss: losses totalling 6% of capital → pause until next UTC midnight. PASS/FAIL.
5. Win resets consecutive losses: 3 losses then win → consecutive=0. PASS/FAIL.
6. Isolation: pause trend_following but mean_reversion active. PASS/FAIL.
7. Print "MODULE 11 – STRATEGY SILO: ALL TESTS PASSED"
8. Delete test database after tests.

## SUCCESS CRITERIA
All tests pass, test db deleted.

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 11 – Strategy Silo
File created: risk/strategy_silo.py
Consecutive loss pause: PASS or FAIL
Drawdown pause: PASS or FAIL
Scalper daily limit: PASS or FAIL
Win reset: PASS or FAIL
Isolation: PASS or FAIL
Type APPROVED to proceed to Module 12 – Correlation Breaker
