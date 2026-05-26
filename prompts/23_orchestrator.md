# Prompt 23 — Orchestrator

## CONTEXT
This is Module 23 of 24. All previous modules must be
complete and APPROVED before starting this module.

This is the final assembly module. It connects every
module built so far into one unified system that runs
continuously 24/7.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 23 — Orchestrator
Files created: orchestrator.py, scheduler.py
Test results: [show actual output]
Type APPROVED to proceed to Module 24 —
System Integration Test

Do not proceed until user types: APPROVED

## FILES TO CREATE
orchestrator.py
scheduler.py

## PURPOSE
The orchestrator is the master control program.
It initialises every module, starts all scheduled
tasks, runs the main trading loop, and coordinates
all components into one unified system. It is the
single entry point for the entire trading system.

## SYSTEM STARTUP SEQUENCE
When orchestrator.py is started it must do these
steps in exact order:

Step 1 — Load environment:
  Load all variables from .env
  Verify all required keys present
  Set ENVIRONMENT flag (backtest or live)

Step 2 — Initialise database:
  Run OHLCVFetcher.init_database
  Run drawdown_guard.init_db
  Run strategy_silo.init_db
  Run correlation_breaker.init_db
  If any fails: log CRITICAL and exit

Step 3 — Initialise exchange connection:
  Create KrakenClient instance
  Test connection with fetch_order_book BTC/USD
  If fails: log CRITICAL and exit

Step 4 — Initialise Telegram bot:
  Create bot instance
  Send startup alert:
    TRADING SYSTEM ONLINE
    ─────────────────────
    Environment: LIVE
    Assets: BTC ETH SOL BNB XRP
    Time: [current UTC time]
    All systems initialised successfully
  If fails: log WARNING but continue
    (system can run without Telegram)

Step 5 — Start scheduler:
  Start all scheduled jobs defined in scheduler.py
  Log all jobs registered

Step 6 — Start main trading loop:
  Begin continuous operation

## DEPENDENCIES
- from execution.kraken_client import KrakenClient
- from execution.order_manager import OrderManager
- from data.ohlcv_fetcher import OHLCVFetcher
- from core.edge_score import calculate_all
- from core.edge_score import get_summary
- from core.sentiment import calculate_all as sent_all
- from core.sentiment import get_summary as sent_summary
- from risk.drawdown_guard import update as dd_update
- from risk.drawdown_guard import is_trading_allowed
- from risk.drawdown_guard import init_db as dd_init
- from risk.strategy_silo import is_active
- from risk.strategy_silo import init_db as silo_init
- from risk.strategy_silo import reset_daily_losses
- from risk.correlation_breaker import check as corr_check
- from risk.correlation_breaker import get_size_multiplier
- from risk.correlation_breaker import init_db as corr_init
- from risk.time_filters import is_trading_allowed as tf_check
- from risk.time_filters import get_size_multiplier as tf_size
- from risk.time_filters import get_parameter_overrides
- from sentinel.sentinel import check_all_filters
- from strategies.trend_following import run_strategy_iteration as tf_run
- from strategies.mean_reversion import run_strategy_iteration as mr_run
- from strategies.scalper import run_scalper_iteration as sc_run
- from telegram_bot.bot import start_bot, stop_bot
- from telegram_bot.alerts import send_status_update
- from telegram_bot.alerts import send_daily_summary
- from telegram_bot.alerts import send_error_alert
- from dead_mans_switch.heartbeat_monitor import write_heartbeat
- from backtest.engine import run_all_assets
- APScheduler, asyncio, logging, datetime
- python-dotenv, config.py

## scheduler.py

### PURPOSE
Defines all scheduled recurring tasks.
Uses APScheduler AsyncIOScheduler.

### JOBS TO SCHEDULE

#### Every 60 seconds:
- write_heartbeat — sends heartbeat to monitor

#### Every 15 minutes:
- main_regime_check — runs Decision Engine
  on all 5 assets and updates edge scores
- check_open_positions — checks if any stops
  or take profits have been hit

#### Every hour:
- update_sentiment — recalculates Structural
  Sentiment for all 5 assets
- update_live_data — fetches latest OHLCV
  candles for all assets

#### Every 4 hours:
- correlation_check — runs correlation breaker
- send_status_update — sends status to Telegram

#### Every day at UTC midnight:
- reset_daily_losses — resets strategy silo
  daily loss counters
- send_daily_summary — sends daily P&L summary

#### Every Monday at UTC midnight:
- check_weekly_limits — resets weekly drawdown
  tracking if applicable

### FUNCTIONS

#### 1. create_scheduler
- Creates APScheduler AsyncIOScheduler
- Registers all jobs listed above
- Returns scheduler instance

#### 2. start_scheduler
- Starts the scheduler
- Logs all registered jobs
- Returns True if started successfully

#### 3. stop_scheduler
- Gracefully stops scheduler
- Waits for running jobs to complete
- Returns True if stopped cleanly

## orchestrator.py

### MAIN TRADING LOOP

#### run_asset_cycle
- Input: asset (str)
- Runs one complete decision and execution cycle
  for one asset
- Process:
  1. Load latest OHLCV data from database
  2. Check time_filters — get size multiplier
     and parameter overrides
  3. Check drawdown_guard — is trading allowed
     If not allowed: skip this asset
  4. Run chaotic_tripwire check
     If triggered: skip this asset, send alert
  5. Run edge_score.calculate for this asset
  6. Run sentiment.calculate for this asset
  7. Get correlation size multiplier
  8. Get sentinel green or red light
     If red: skip this asset
  9. Check each strategy silo — is it active
  10. For each active strategy:
      If edge score supports this strategy:
        Calculate final position size:
          base_size × edge_score × rvr_multiplier
          × correlation_multiplier × time_multiplier
        Check if position already open for asset
        If no position open:
          Run strategy iteration
          If trade signal generated:
            Open position via order_manager
            Send trade alert via Telegram
  11. Log cycle completion with timing

#### run_main_loop
- Runs run_asset_cycle for all 5 assets
- Runs sequentially not simultaneously
- Catches errors per asset — one failure does
  not stop other assets
- Logs total cycle time

#### initialise_system
- Runs the startup sequence steps 1 through 5
- Returns True if all critical steps pass
- Returns False if any critical step fails

#### shutdown_system
- Called on keyboard interrupt or signal
- Closes all open positions gracefully
- Stops scheduler
- Stops Telegram bot
- Logs shutdown complete
- Sends Telegram alert:
  TRADING SYSTEM OFFLINE
  ──────────────────────
  Reason: [shutdown reason]
  Open positions closed: [count]
  Time: [UTC time]

#### main
- Entry point called by if __name__ == '__main__'
- Calls initialise_system
- If initialisation fails: exit with error
- Starts Telegram bot in background
- Starts scheduler
- Runs main_loop continuously until interrupted
- On interrupt: calls shutdown_system

### ENVIRONMENT MODES

#### BACKTEST mode (ENVIRONMENT=backtest):
- Do not connect to live Kraken
- Do not send real orders
- Run backtest engine instead of live loop
- Print results and exit

#### LIVE mode (ENVIRONMENT=live):
- Full live trading
- Real orders on Kraken
- All safety systems active

## ERROR HANDLING
- Startup failures in critical modules: exit
- Runtime errors in individual assets: log and
  continue with other assets
- Telegram failures: log but never crash system
- Exchange connection loss: retry 3 times then
  pause trading and alert via Telegram
- All unhandled exceptions: log CRITICAL and
  attempt graceful shutdown

## LOGGING
- System startup logged in full detail
- Every cycle logged with timing
- Every module initialisation logged
- Shutdown sequence logged step by step
- Master log file: logs/system.log
- Rotating handler: 10MB max, keep 7 files

## TEST
At bottom of orchestrator.py in
if __name__ == '__main__': block:

When ENVIRONMENT=backtest:
1. Run initialise_system
   Print each step as it completes
   Print PASS or FAIL for each

2. Test run_asset_cycle on BTC/USD:
   Run one complete cycle
   Print edge scores generated
   Print sentiment result
   Print whether trade signal generated
   Print cycle time in milliseconds

3. Test scheduler creation:
   Create scheduler
   List all registered jobs
   Print job count
   Stop scheduler immediately

4. Test shutdown_system:
   Verify graceful shutdown completes
   Print PASS or FAIL

5. Run backtest engine on BTC/USD for 30 days:
   Print metrics summary

6. Print MODULE 23 — ORCHESTRATOR:
   ALL TESTS PASSED if all criteria met

When ENVIRONMENT=live:
- Run full system continuously
- All scheduled jobs active
- Real trading enabled

## SUCCESS CRITERIA
- System initialises all modules without errors
- Startup Telegram message received
- Scheduler registers all jobs correctly
- run_asset_cycle completes without errors
- Backtest mode runs correctly
- Live mode starts and runs continuously
- Shutdown is graceful — no open positions left
- All logs written correctly

## IMPORTANT FINAL INSTRUCTIONS
- Create files at exactly these paths:
  orchestrator.py
  scheduler.py
- This is the LAST module before integration test
- Do NOT modify any existing module code
- The orchestrator imports everything —
  if any import fails identify which module
  has the problem and report clearly
- In LIVE mode the system runs forever until
  manually stopped via Ctrl+C or Telegram /pause
- Always start in BACKTEST mode first to verify
  all imports and connections work
- Only switch ENVIRONMENT=live after confirming
  backtest mode runs without errors
- The main function must handle asyncio event loop
  correctly for python-telegram-bot v20.8
