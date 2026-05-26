# Prompt 21 — Telegram Bot

## CONTEXT
This is Module 21 of 24. Module 20 Order Manager must be
complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 21 — Telegram Bot
Files created: telegram_bot/bot.py
telegram_bot/commands.py
telegram_bot/alerts.py
Test results: [show actual output]
Type APPROVED to proceed to Module 22 — Dead Mans Switch

Do not proceed until user types: APPROVED

## FILES TO CREATE
telegram_bot/bot.py
telegram_bot/commands.py
telegram_bot/alerts.py

## PURPOSE
Full remote monitoring and control of the trading system
via Telegram. The bot is the only interface between the
trader and the live system. Only the authorised Telegram
user ID can send commands. All other messages are ignored.

## SECURITY
- Load TELEGRAM_BOT_TOKEN from .env
- Load TELEGRAM_AUTHORISED_USER_ID from .env
- Every incoming message checked against authorised ID
- Reject all messages from unauthorised users silently
- Log all rejected attempts to logs/errors.log

## DEPENDENCIES
- python-telegram-bot==20.8 (async version)
- from execution.order_manager import get_open_positions
- from execution.order_manager import emergency_close_all
- from execution.order_manager import format_position_summary
- from execution.kraken_client import KrakenClient
- from core.edge_score import calculate_all
- from core.edge_score import get_summary
- from core.sentiment import calculate_all as sentiment_all
- from core.sentiment import get_summary as sentiment_summary
- from risk.drawdown_guard import get_status as dd_status
- from risk.drawdown_guard import is_trading_allowed
- from risk.drawdown_guard import resolve_halt
- from risk.strategy_silo import get_all_status
- from risk.strategy_silo import format_summary as silo_summary
- from risk.strategy_silo import resume_strategy
- from risk.correlation_breaker import get_status as corr_status
- from risk.correlation_breaker import get_size_multiplier
- from risk.time_filters import get_parameter_overrides
- from data.ohlcv_fetcher import OHLCVFetcher
- asyncio, logging, datetime, python-dotenv

## telegram_bot/alerts.py

### PURPOSE
Sends automatic notifications to the authorised user.
All alert functions are called by the orchestrator and
scheduler — not by the user.

### FUNCTIONS

#### 1. send_message
- Inputs: message (str), bot_token (str),
  chat_id (str)
- Sends plain text message to authorised user
- Returns True if sent, False if failed
- Log failures to logs/errors.log

#### 2. send_trade_signal
- Inputs: signal_text (str) — formatted signal
  from position_sizer.format_signal
- Sends trade signal alert
- Prepends with trading signal emoji

#### 3. send_trade_opened
- Inputs: position details dictionary
- Sends confirmation when trade is opened:
  TRADE OPENED — BTC/USD
  ──────────────────────
  Direction: LONG
  Size: 0.0987 BTC ($4,127.50)
  Entry Price: $45,000
  Stop Loss: $44,200
  Take Profit: $46,500
  Strategy: Trend-Following
  Edge Score: 0.74

#### 4. send_trade_closed
- Inputs: close details dictionary
- Sends confirmation when trade is closed:
  TRADE CLOSED — BTC/USD
  ──────────────────────
  Direction: LONG closed
  Entry: $45,000 Exit: $46,200
  PnL: +$118.41 (+2.63%)
  Reason: Take Profit hit
  Duration: 4h 22m
  Strategy: Trend-Following

#### 5. send_drawdown_alert
- Inputs: drawdown_result dictionary
- Sends alert when drawdown limit breached:
  DRAWDOWN ALERT
  ──────────────
  Peak Drawdown: 15.2% — HALT TRIGGERED
  Account: $8,480 (peak: $10,000)
  All new entries blocked
  Mandatory 24h cool-off begins now

#### 6. send_strategy_paused_alert
- Inputs: asset (str), strategy (str), reason (str)
- Sends alert when strategy silo pauses

#### 7. send_correlation_alert
- Inputs: correlation_result dictionary
- Sends alert when correlation breaker fires

#### 8. send_chaotic_tripwire_alert
- Inputs: asset (str), ratio (float)
- Sends alert when Chaotic Tripwire fires

#### 9. send_status_update
- Inputs: full system status dictionary
- Sends 4-hourly automatic status update:
  SYSTEM STATUS — 14:00 UTC
  ──────────────────────────
  Account: $10,247.83
  Daily PnL: +$127.50 (+1.26%)
  Open Positions: 1 (BTC/USD long)
  ──────────────────────────
  EDGE SCORES:
  BTC/USD: TREND_FOLLOWING (0.74)
  ETH/USD: MEAN_REVERSION (0.52)
  SOL/USD: SCALPER (dead zone)
  BNB/USD: BLOCKED (chaotic)
  XRP/USD: MEAN_REVERSION (0.61)
  ──────────────────────────
  SENTIMENT:
  BTC: BULLISH | ETH: NEUTRAL
  SOL: BEARISH | BNB: NEUTRAL
  XRP: BULLISH
  ──────────────────────────
  Risk Status: ACTIVE
  Correlation: NORMAL (0.43)

#### 10. send_daily_summary
- Called at midnight UTC
- Sends full daily performance summary:
  DAILY SUMMARY — 25 May 2026
  ────────────────────────────
  Total Trades: 7
  Winners: 4 Losers: 3
  Daily PnL: +$247.80 (+2.48%)
  Best Trade: BTC/USD +$142.50
  Worst Trade: ETH/USD -$38.20
  Strategies: TF:3 MR:3 SC:1
  ────────────────────────────
  Account Balance: $10,247.83
  Peak Drawdown Today: 1.2%
  Status: ACTIVE

#### 11. send_error_alert
- Inputs: error_message (str), module (str)
- Sends critical error notification

## telegram_bot/commands.py

### PURPOSE
Handles all incoming commands from the authorised user.

### COMMANDS TO IMPLEMENT

#### /start
- Welcome message explaining available commands

#### /status
- Full system snapshot:
  Current account balance
  Open positions
  Edge scores per asset
  Sentiment per asset
  Drawdown status
  Correlation status
  Active strategy silos

#### /balance
- Fetches live balance from Kraken
- Displays all currency balances

#### /positions
- Shows all open positions with current PnL
- Uses format_position_summary

#### /edge_scores
- Shows current Hurst, PEC, RVR, Autocorr
  and Edge Score per asset

#### /sentiment
- Shows current Structural Sentiment for all assets

#### /drawdown_status
- Current drawdown from peak, daily, weekly

#### /correlation_status
- Current correlation matrix and circuit breaker state

#### /silo_status
- All 15 strategy silos and their current status

#### /pause
- Stops all new entries
- Keeps existing positions open
- Sends confirmation

#### /resume
- Resumes trading after manual pause
- Requires confirmation: reply YES to confirm

#### /emergency_close
- Closes ALL positions immediately
- Requires second confirmation phrase:
  CONFIRM EMERGENCY CLOSE
- Logs the emergency close with timestamp

#### /resolve_halt PEAK
- Manually resolves a specific halt type
- Allowed values: PEAK, INTRADAY, WEEKLY
- Requires confirmation

#### /resume_strategy BTC/USD TREND_FOLLOWING
- Manually reactivates a paused strategy silo
- Format: /resume_strategy ASSET STRATEGY

#### /sentinel_mode normal
- Changes Sentinel sensitivity
- Allowed values: normal, paranoid, relaxed

#### /correlation_status
- Shows current correlation matrix

#### /news_blackout off
- Temporarily disables news blackout
- Requires confirmation
- Logs the override with reason

#### /backtest BTC/USD 30
- Runs quick backtest on specified asset
- Second argument is number of days
- Returns metrics summary

#### /help
- Lists all available commands with descriptions

## telegram_bot/bot.py

### PURPOSE
Main bot entry point. Initialises the bot, registers
all command handlers, starts polling for messages.

### FUNCTIONS

#### 1. create_bot
- Loads TELEGRAM_BOT_TOKEN from .env
- Creates Application instance
- Returns application

#### 2. register_handlers
- Registers all command handlers from commands.py
- Registers a catch-all handler for unknown commands
- Registers security middleware to check user ID

#### 3. check_authorised
- Middleware function
- Checks message user ID against TELEGRAM_AUTHORISED_USER_ID
- Returns True if authorised
- Logs and silently ignores unauthorised attempts

#### 4. start_bot
- Calls create_bot and register_handlers
- Starts polling
- Logs bot started successfully

#### 5. stop_bot
- Gracefully stops the bot
- Called by orchestrator on shutdown

## ERROR HANDLING
- Every command handler wrapped in try/except
- If a command fails send error message to user
  do not crash the bot
- If bot loses connection retry automatically
- Log all errors to logs/errors.log
- Log all commands received to logs/commands.log

## LOGGING
- Every command received logged with timestamp
  and user ID
- Every alert sent logged at INFO level
- Failed sends logged at ERROR level

## TEST
At bottom of bot.py in
if __name__ == '__main__': block:

1. Test bot token loads from .env:
   Print Bot token loaded: PASS or FAIL

2. Test authorised user ID loads:
   Print Authorised user ID: [id] PASS or FAIL

3. Test send_message with real Telegram:
   Send test message to authorised user:
   TRADING SYSTEM — Bot test successful
   Module 21 Telegram Bot is online
   Print Message sent: PASS or FAIL

4. Test check_authorised:
   Mock message from authorised ID
   Expected: True
   Mock message from random ID 999999
   Expected: False
   Print both PASS or FAIL

5. Test send_status_update with mock data:
   Create mock system status dictionary
   Call send_status_update
   Print Formatted correctly: PASS or FAIL

6. Print MODULE 21 — TELEGRAM BOT:
   ALL TESTS PASSED if all criteria met

## SUCCESS CRITERIA
- Bot starts without errors
- Test message received on Telegram
- All commands registered and responding
- Unauthorised users rejected silently
- All alert functions send correct format
- Commands logged to logs/commands.log

## IMPORTANT FINAL INSTRUCTIONS
- Create files at exactly these paths:
  telegram_bot/bot.py
  telegram_bot/commands.py
  telegram_bot/alerts.py
- Use python-telegram-bot v20.8 async version only
- Never send messages to unauthorised users
- Emergency close MUST require double confirmation
- All monetary values formatted with commas
  and 2 decimal places
- All timestamps displayed in UTC
- Bot must continue running if one command fails
