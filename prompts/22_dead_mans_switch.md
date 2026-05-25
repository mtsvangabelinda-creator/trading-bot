# Prompt 22 – Dead Man's Switch

## CONTEXT
Module 21 Telegram Bot must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 22 – Dead Man's Switch
Files created: dead_mans_switch/heartbeat_monitor.py, dead_mans_switch/emergency_cancel.py
Test results: [show actual output]
Type APPROVED to proceed to SYSTEM INTEGRATION AND LIVE TESTING

Do not proceed until user types: APPROVED.

## FILES TO CREATE
dead_mans_switch/heartbeat_monitor.py
dead_mans_switch/emergency_cancel.py

## PURPOSE
Implements the dead man's switch – a separate lightweight monitor that watches the main bot's heartbeat. If the heartbeat stops for 5 minutes, the backup cancels all open orders using a second API key with cancel‑only permissions. The backup never places trades – it only kills orders. This is a critical safety mechanism per spec.

## RULES FROM SPEC
- Separate lightweight cloud instance (or separate thread/process) monitors main bot via heartbeat signal.
- Heartbeat interval: every 60 seconds (main bot writes timestamp to database or sends ping).
- Heartbeat timeout: 5 minutes (300 seconds) – if no heartbeat seen, trigger emergency cancel.
- Backup uses a second Kraken API key with **cancel‑only permissions** (withdrawals disabled, no trading permissions).
- Emergency cancel: cancels all open orders for all symbols.
- After emergency cancel, backup sends Telegram alert (via main bot's token or separate) and optionally writes log.
- The backup never places new orders or closes positions – only cancels open orders.

## DEPENDENCIES
- time, logging, threading (or separate process), sqlite3 (or aiohttp for remote heartbeat)
- config.py: HEARTBEAT_INTERVAL=60, HEARTBEAT_TIMEOUT=300, KRAKEN_CANCEL_KEY, KRAKEN_CANCEL_SECRET (from .env)
- kraken_client (modified to support cancel‑only key) or separate minimal CCXT instance.
- telegram_bot/alerts.py for sending alert.

## heartbeat_monitor.py

### FUNCTIONS
1. init_heartbeat_db(db_path='data/heartbeat.db')
   - Creates table heartbeat: id INTEGER PRIMARY KEY, last_heartbeat TIMESTAMP, status TEXT, message TEXT.
   - Returns True.

2. write_heartbeat(db_path='data/heartbeat.db', status='alive', message='')
   - Called by main bot every HEARTBEAT_INTERVAL seconds.
   - Inserts new record or updates a single row (e.g., id=1 always).

3. read_last_heartbeat(db_path='data/heartbeat.db')
   - Returns datetime of last heartbeat, status, message.

4. start_heartbeat_sender(interval_seconds=60, db_path='data/heartbeat.db')
   - Runs in a background thread (or as part of main loop). Infinite loop: write_heartbeat(), sleep(interval_seconds).
   - For testing, can be started manually.

5. check_heartbeat(timeout_seconds=300, db_path='data/heartbeat.db')
   - Compares last_heartbeat with current UTC time. If difference > timeout_seconds, returns False (heartbeat dead). Else True.

## emergency_cancel.py

### FUNCTIONS
1. get_cancel_only_exchange()
   - Creates CCXT Kraken (or Binance) instance using KRAKEN_CANCEL_KEY and KRAKEN_CANCEL_SECRET.
   - Withdrawals must be disabled on this key; permissions should be "cancel orders only".
   - Returns exchange object.

2. cancel_all_open_orders(exchange, symbol=None)
   - Cancels all orders for all symbols (or specific symbol if provided).
   - Uses exchange.cancel_all_orders() if available, else loops through fetch_open_orders.
   - Returns count of cancelled orders.

3. run_emergency_cancel(telegram_bot=None, chat_id=None, db_path='data/heartbeat.db')
   - Called when heartbeat timeout detected.
   - Steps:
        a. Log "EMERGENCY: Heartbeat lost, initiating emergency cancel."
        b. Get cancel‑only exchange.
        c. Cancel all open orders.
        d. Send Telegram alert: "⚠️ DEAD MAN'S SWITCH ACTIVATED: All open orders cancelled due to heartbeat timeout (5 minutes without signal)."
        e. Write to log file logs/dead_man.log.
        f. Optionally set a flag in database to prevent re‑triggering for a while.
   - Returns dict: success (bool), orders_cancelled (int), alert_sent (bool).

4. monitor_loop(check_interval=60, timeout_seconds=300, telegram_bot=None, chat_id=None)
   - Runs in a separate thread or as a simple loop in a separate process.
   - Infinite loop: check_heartbeat(timeout_seconds). If heartbeat dead and not already triggered, call run_emergency_cancel(). Sleep check_interval.
   - To avoid duplicate triggers, store a state "emergency_triggered" in DB or memory, reset when heartbeat resumes? Usually after trigger, manual restart required. So once triggered, keep cancelled until admin intervenes.

## INTEGRATION WITH MAIN BOT
- In orchestrator.py (or main.py), start the heartbeat sender thread before main loop.
- Also start the monitor thread (dead man's switch) – this could be in a separate lightweight process, but for simplicity, another thread.
- The monitor should be as independent as possible – minimal dependencies, does not rely on main bot's health.

## ERROR HANDLING
- All functions try/except, log to logs/dead_man.log.
- If cancel‑only exchange fails to initialise, log critical and retry.
- If Telegram alert fails, log but continue – safety first.

## TESTS (in if __name__ == '__main__':)
Use test database and mock exchange (or real sandbox with cancel‑only key).

1. Test heartbeat write and read – write_heartbeat, read_last_heartbeat returns recent timestamp. PASS/FAIL.
2. Test heartbeat detection – write heartbeat, wait 1 sec, check_heartbeat(timeout=2) returns True. PASS/FAIL.
3. Test timeout – no write for 3 seconds, timeout=2 returns False. PASS/FAIL.
4. Test emergency cancel (dry run or sandbox) – cancel_all_open_orders returns count (0 if none). PASS/FAIL.
5. Test full monitor loop simulation: start heartbeat sender in background, then simulate main bot crash (stop sending). Monitor should trigger after timeout. Use shorter intervals for test (heartbeat_interval=2, timeout=6). PASS/FAIL.
6. Test duplicate trigger prevention: after first emergency, second call should not repeat or should be idempotent. PASS/FAIL.
7. Print "MODULE 22 – DEAD MAN'S SWITCH: ALL TESTS PASSED"

## SUCCESS CRITERIA
- Heartbeat writes every 60 seconds (configurable)
- Monitor detects missing heartbeat after timeout
- Emergency cancel cancels all open orders using cancel‑only key
- Telegram alert sent on activation
- No orders are ever placed by dead man's switch
- Does not trigger repeatedly

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 22 – Dead Man's Switch
Files created: dead_mans_switch/heartbeat_monitor.py, emergency_cancel.py
Heartbeat write/read: PASS or FAIL
Timeout detection: PASS or FAIL
Emergency cancel (dry run): PASS or FAIL
Monitor loop simulation: PASS or FAIL
Duplicate prevention: PASS or FAIL
Type APPROVED to proceed to SYSTEM INTEGRATION AND LIVE TESTING
