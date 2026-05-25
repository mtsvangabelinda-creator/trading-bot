# Prompt 21 – Telegram Bot & Alerts

## CONTEXT
Module 20 Scheduler & Orchestrator must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 21 – Telegram Bot & Alerts
Files created: telegram_bot/bot.py, telegram_bot/commands.py, telegram_bot/alerts.py
Test results: [show actual output]
Type APPROVED to proceed to Module 22 – Dead Man's Switch

Do not proceed until user types: APPROVED.

## FILES TO CREATE
telegram_bot/bot.py
telegram_bot/commands.py
telegram_bot/alerts.py

## PURPOSE
Provides remote monitoring and control via Telegram. Sends automatic alerts for trades, risk events, and system status. Accepts commands from an authorised user to check status, pause trading, emergency close, and override regime. Implements all alerts and commands listed in the spec (Pages 7-8 of Trading_System_Plan_V2.pdf).

## RULES FROM SPEC

### Automatic Alerts (send to authorised user)
- Status update every 4 hours: Edge Scores per asset, open positions, daily P&L
- Trade alerts on every entry and exit, including the Edge Score that triggered the trade
- Sentinel warnings when order book becomes dangerous
- Correlation circuit breaker activation alerts
- Drawdown limit alerts at intraday, weekly, and peak levels
- Strategy self-destruct alerts
- Chaotic Tripwire activation and deactivation
- News blackout start and end notices
- Dead zone alerts when all assets enter ambiguous regime simultaneously
- Daily summary with total P&L and number of trades per strategy

### Commands (from spec)
- /status – current account, open positions, drawdowns, edge scores
- /pause – pause trading for X minutes (default 30)
- /resume – resume trading
- /emergency_close – cancel all orders and close all positions (requires second confirmation)
- /silo_status – per-strategy silo status (paused, drawdown, consecutive losses)
- /override_regime [trend|reversion|scalper] [duration_minutes] – force a specific regime (auto-expires after 2 hours)
- /cancel_overrides – remove all manual overrides
- /sentinel_status – current sentinel green/red and latest warnings
- /correlation_status – current avg correlation and exposure multiplier
- /drawdown_status – peak, intraday, weekly drawdowns
- /help – list all commands

## DEPENDENCIES
- python-telegram-bot (v20.x)
- asyncio (if using async, or use sync wrapper)
- logging, datetime, json
- config.py: TELEGRAM_BOT_TOKEN, TELEGRAM_AUTHORISED_USER_ID (from .env)
- All previous modules to fetch status: drawdown_guard, strategy_silo, correlation_breaker, sentinel, decision_engine, order_manager

## alerts.py

### FUNCTIONS
1. send_alert(bot, chat_id, message, parse_mode='HTML')
   - Wrapper to send message via bot.

2. format_trade_alert(strategy, symbol, side, size, edge_score, filled_price, pnl=None)
   - Returns formatted string.

3. format_status_summary(account_value, drawdown_status, silos_status, edge_scores, open_positions)
   - Builds rich text summary.

4. send_trade_alert(bot, chat_id, trade_details)
5. send_sentinel_alert(bot, chat_id, symbol, warnings)
6. send_correlation_alert(bot, chat_id, avg_corr, exposure_multiplier, is_paused)
7. send_drawdown_alert(bot, chat_id, drawdown_type, trigger_pct, limit_pct)
8. send_self_destruct_alert(bot, chat_id, strategy_name, reason)
9. send_chaotic_alert(bot, chat_id, active, current_atr, atr_slow)
10. send_news_blackout_alert(bot, chat_id, start_or_end, event_name)
11. send_dead_zone_alert(bot, chat_id, assets_list)
12. send_daily_summary(bot, chat_id, daily_pnl, trade_counts_per_strategy)

## commands.py

### FUNCTIONS
Each command handler receives update, context. Checks that user_id matches TELEGRAM_AUTHORISED_USER_ID. If not, reply "Unauthorised".

1. cmd_status(update, context)
   - Gathers: account value, drawdown status (peak/intraday/weekly), open orders/positions, current edge scores per asset, sentinel status summary.
   - Sends formatted message.

2. cmd_pause(update, context)
   - Parse optional minutes (default 30). Sets global pause flag with expiry.
   - Logs to db.

3. cmd_resume(update, context)
   - Clears global pause flag.

4. cmd_emergency_close(update, context)
   - First call asks for confirmation phrase (e.g., "CONFIRM_EMERGENCY"). Second call with phrase triggers: cancel all orders, close all open positions (market orders opposite side). Uses order_manager.cancel_all_orders and close_positions function.
   - Requires two-step confirmation.

5. cmd_silo_status(update, context)
   - For each strategy, get silo status from strategy_silo module: allocated capital, current equity, drawdown pct, consecutive losses, daily loss, paused_until.

6. cmd_override_regime(update, context)
   - Parse arguments: regime (trend/reversion/scalper), duration minutes.
   - Overrides decision engine output for that duration. Stores in memory or db with expiry.
   - Auto-expires after duration.

7. cmd_cancel_overrides(update, context)
   - Clears any active regime overrides.

8. cmd_sentinel_status(update, context)
   - Returns latest sentinel checks per symbol (green/red, reasons).

9. cmd_correlation_status(update, context)
   - Returns avg correlation, exposure multiplier, pause state.

10. cmd_drawdown_status(update, context)
    - Returns peak, intraday, weekly drawdown percentages and limits.

11. cmd_help(update, context)
    - Lists all commands with brief description.

## bot.py

### FUNCTIONS
1. setup_bot(token)
   - Creates Application instance, adds command handlers.
   - Returns bot application.

2. run_bot(bot_app)
   - Starts polling (or webhook if deployed).

3. send_heartbeat(bot_app, chat_id)
   - Optionally send periodic "Bot alive" message – not in spec but useful.

## ERROR HANDLING
- All handlers wrapped in try/except, log to logs/telegram.log
- If bot fails to send, log but don't crash main bot loop.

## TESTS (in if __name__ == '__main__':)
Use mock bot and mock modules, or run with real test token in sandbox (user must provide token). For automated test, we simulate command responses.

1. Test /status – returns non-empty formatted message. PASS/FAIL.
2. Test /pause – sets global pause flag, returns confirmation. PASS/FAIL.
3. Test /resume – clears pause. PASS/FAIL.
4. Test /emergency_close – first call asks confirmation, second with correct phrase triggers close. PASS/FAIL.
5. Test /override_regime – sets override with expiry. PASS/FAIL.
6. Test /cancel_overrides – clears override. PASS/FAIL.
7. Test authorisation – wrong user id returns "Unauthorised". PASS/FAIL.
8. Test alert sending – send_trade_alert produces valid message. PASS/FAIL.
9. Print "MODULE 21 – TELEGRAM BOT: ALL TESTS PASSED"

## SUCCESS CRITERIA
- All commands functional and authorised
- Alerts format correctly
- Emergency close works (test in sandbox only)
- Override regime auto-expires after duration
- Bot starts and polls without errors

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 21 – Telegram Bot & Alerts
Files created: telegram_bot/bot.py, commands.py, alerts.py
Status command: PASS or FAIL
Pause/resume: PASS or FAIL
Emergency close: PASS or FAIL
Override regime: PASS or FAIL
Authorisation: PASS or FAIL
Alert formatting: PASS or FAIL
Type APPROVED to proceed to Module 22 – Dead Man's Switch
