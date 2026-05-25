# Prompt 20 – Scheduler & Orchestrator

## CONTEXT
Module 19 Order Manager must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 20 – Scheduler & Orchestrator
Files created: scheduler.py, orchestrator.py
Test results: [show actual output]
Type APPROVED to proceed to Module 21 – Telegram Bot & Alerts

Do not proceed until user types: APPROVED.

## FILES TO CREATE
scheduler.py
orchestrator.py

## PURPOSE
The scheduler runs all periodic tasks (Decision Engine every 15 min per asset, Structural Sentiment every hour, Correlation Breaker every 4 hours, Daily reset at UTC midnight, Heartbeat for dead man's switch). The orchestrator coordinates the entire system: loads config, initializes modules, calls the correct strategy based on edge scores, respects risk gates, and manages the main loop.

## RULES FROM SPEC
- Decision Engine runs every 15 minutes per asset (can be sequential, not parallel)
- Structural Sentiment updates every hour
- Correlation Breaker every 4 hours
- Daily reset at UTC midnight (reset intraday drawdown, daily losses, etc.)
- Chaotic Tripwire runs on every cycle (part of Decision Engine)
- The orchestrator should check all risk gates before any trade: Drawdown Guard, Strategy Silo, Sentinel, Correlation Breaker, Time Filters (news blackout)
- If any risk gate blocks trading, skip all strategies for that cycle

## DEPENDENCIES
- time, logging, threading or asyncio (we'll use simple time.sleep loop for simplicity)
- datetime, pytz
- config.py for intervals and asset list
- All previously built modules: decision_engine (core/*), strategies (trend_following, mean_reversion, scalper), risk modules (drawdown_guard, strategy_silo, correlation_breaker, time_filters), sentinel, execution/order_manager, data/ohlcv_fetcher

## scheduler.py

### FUNCTIONS
1. run_at_interval(interval_seconds, func, *args, **kwargs)
   - Runs func in a loop, sleeping interval_seconds between runs.
   - Can be used for simple polling. For production, use APScheduler, but for simplicity we'll implement a while True loop with sleep.

2. run_daily_at(target_time_utc, func, *args, **kwargs)
   - Runs func once per day at specified UTC time (e.g., "00:05" for daily reset).
   - Calculates seconds until next target, sleeps, runs, then repeats every 24 hours.

3. run_asset_cycle(symbol, ohlcv_fetcher, decision_engine, strategies, risk_gates, exchange, dry_run)
   - Single iteration for one asset: fetch latest OHLCV, run decision engine, get edge scores, check risk gates, then decide which strategy to run.
   - Returns dict with results.

## orchestrator.py

### FUNCTIONS
1. load_all_modules()
   - Imports and initializes:
     - Kraken client (exchange)
     - OHLCV fetcher
     - Decision Engine (hurst, autocorr, pec, rvr, edge_score, sentiment)
     - Strategies (trend_following, mean_reversion, scalper)
     - Risk modules: drawdown_guard, strategy_silo, correlation_breaker, time_filters
     - Sentinel
     - Order manager
   - Returns a dict of module instances/objects.

2. check_all_risk_gates(symbol, order_amount_usd, db_path='data/trading_data.db')
   - Checks: drawdown_guard.is_trading_allowed(), strategy_silo.is_strategy_allowed(strategy_name), correlation_breaker.is_trading_allowed(), time_filters.is_trading_allowed(), sentinel.is_trade_allowed(symbol, order_amount_usd)
   - Returns dict: {'allowed': bool, 'blocked_by': list of module names, 'details': {...}}

3. run_strategy_for_asset(symbol, capital_usd, edge_scores, sentiment, ohlcv_df, exchange, sentinel, risk_gates, order_manager, dry_run)
   - edge_scores contains tf_edge, mr_edge, dead_zone flag, rvr_multiplier.
   - Determine which strategy to run (or multiple – spec says all three run simultaneously? Actually they compete: only the one with highest edge? But spec says "system has three strategies ready to deploy" and "Decision Engine scores them continuously". To simplify, we run all three but each has its own silo and size. However, overlapping positions on same symbol could be messy. Safer: run only the strategy with highest edge score (if >0.3). If dead_zone, run scalper with bias only.
   - Implementation: if dead_zone: run scalper (with bias from sentiment). Else: if tf_edge > mr_edge and tf_edge > 0.3: run trend_following; if mr_edge > tf_edge and mr_edge > 0.3: run mean_reversion; always run scalper in addition? Spec ambiguous. To avoid over-trading, we'll run only the dominant strategy per asset per cycle. Scalper runs as separate process on shorter timeframe? Simpler: orchestrator runs Decision Engine every 15min, then calls the selected strategy (trend or MR) and also calls scalper separately if configured. We'll let scalper run on a faster cadence (e.g., every 1 minute) in a separate thread – but for MVP, run scalper in same cycle but with smaller size.
   - For this prompt, implement simple logic: call the strategy whose edge is higher and above threshold.

4. update_account_value(db_path='data/trading_data.db')
   - Fetch total account value from exchange (sum of all free balances + value of open positions).
   - Call drawdown_guard.update(account_value).

5. main_loop(dry_run=True)
   - Initialize all modules.
   - Start background threads or tasks:
        - Daily reset thread (reset_daily_losses, reset_intraday_drawdown)
        - Correlation Breaker thread (every 4 hours)
        - Structural Sentiment thread (every hour)
        - Heartbeat thread (every 60 seconds, update dead man's switch – Module 22)
   - Main loop: for each asset in config.ASSETS:
        - Fetch latest OHLCV (1h or appropriate timeframe for Decision Engine – spec says 15min cycle but uses hurst on lookback of 100 candles, any timeframe? We'll use 1h candles for stability).
        - Run Decision Engine for that asset (get edge scores, chaotic flag, sentiment, rvr_multiplier).
        - If chaotic or any risk gate blocks: skip trading for this asset this cycle, log.
        - Else:
            - Get the selected strategy and edge score.
            - Compute position size (using position_sizer with edge score and rvr_multiplier).
            - Check sentinel for this size.
            - If all green, call strategy's execute_trade method.
   - Loop repeats every 15 minutes (config.DECISION_ENGINE_INTERVAL).
   - Log all actions.

6. emergency_stop()
   - Triggered by dead man's switch or manual command: cancel all open orders, set global halt flag.

## ERROR HANDLING
- All loops try/except, log errors, continue.
- If exchange connection lost, retry with backoff.
- Critical errors: emergency stop.

## TESTS (in if __name__ == '__main__':)
Use dry_run=True, mock modules.

1. Test risk gate aggregation – mock one gate returning False, verify orchestrator blocks trade. PASS/FAIL.
2. Test strategy selection – tf_edge=0.7, mr_edge=0.3 → select trend_following. PASS/FAIL.
3. Test dead zone selection – dead_zone=True → skip trend/MR, run scalper only. PASS/FAIL.
4. Test chaotic tripwire – chaotic=True → no trading. PASS/FAIL.
5. Test daily reset thread – mock date change, verify drawdown_guard.reset_intraday called. PASS/FAIL.
6. Test main loop runs one iteration without errors. PASS/FAIL.
7. Print "MODULE 20 – SCHEDULER & ORCHESTRATOR: ALL TESTS PASSED"

## SUCCESS CRITERIA
- Orchestrator loads all modules without errors
- Risk gates checked before each trade
- Decision Engine outputs used to select strategy
- Main loop cycles every 15 minutes (simulated in test)
- Emergency stop cancels orders

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 20 – Scheduler & Orchestrator
Files created: scheduler.py, orchestrator.py
Risk gate test: PASS or FAIL
Strategy selection test: PASS or FAIL
Dead zone test: PASS or FAIL
Chaotic test: PASS or FAIL
Main loop test: PASS or FAIL
Type APPROVED to proceed to Module 21 – Telegram Bot & Alerts
