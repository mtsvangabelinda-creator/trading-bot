# Prompt 22 — Dead Mans Switch

## CONTEXT
This is Module 22 of 24. Module 21 Telegram Bot must be
complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 22 — Dead Mans Switch
Files created: dead_mans_switch/heartbeat_monitor.py
dead_mans_switch/emergency_cancel.py
Test results: [show actual output]
Type APPROVED to proceed to Module 23 — Orchestrator

Do not proceed until user types: APPROVED

## FILES TO CREATE
dead_mans_switch/heartbeat_monitor.py
dead_mans_switch/emergency_cancel.py

## PURPOSE
A separate lightweight process that runs on a second
server instance and monitors the main trading bot via
a heartbeat signal. If the main bot stops sending
heartbeats for more than 5 minutes the dead mans switch
automatically cancels ALL open orders on Kraken using
a separate cancel-only API key. It never places trades.
It only kills orders.

## ARCHITECTURE
Two separate processes on two separate servers:

Main Server (Oracle VPS 1):
  Runs the full trading system
  Sends heartbeat signal every 60 seconds
  Heartbeat = writes current timestamp to a shared
  location (file or simple HTTP endpoint)

Monitor Server (Oracle VPS 2):
  Runs only heartbeat_monitor.py
  Checks heartbeat every 30 seconds
  If no heartbeat for 300 seconds (5 minutes):
  Fires emergency_cancel.py
  Sends Telegram alert

## SECURITY
- Monitor server uses KRAKEN_CANCEL_KEY and
  KRAKEN_CANCEL_SECRET from .env
- This key has cancel-only permissions on Kraken
  It cannot place any trades
- Monitor server has NO access to main API key
- Heartbeat file path or URL configured in .env

## DEPENDENCIES
- ccxt for Kraken cancel-only connection
- python-dotenv for loading cancel API key
- requests for HTTP heartbeat checking
- asyncio, datetime, logging, time
- python-telegram-bot for sending alerts

## ENVIRONMENT VARIABLES NEEDED IN .env
KRAKEN_CANCEL_KEY=your_cancel_only_key
KRAKEN_CANCEL_SECRET=your_cancel_only_secret
TELEGRAM_BOT_TOKEN=same token as main bot
TELEGRAM_AUTHORISED_USER_ID=same user ID
HEARTBEAT_FILE_PATH=data/heartbeat.txt
HEARTBEAT_INTERVAL=60
HEARTBEAT_TIMEOUT=300

## dead_mans_switch/emergency_cancel.py

### PURPOSE
Uses cancel-only Kraken API key to cancel all open
orders when triggered. Never places trades.

### FUNCTIONS

#### 1. create_cancel_only_client
- Loads KRAKEN_CANCEL_KEY and KRAKEN_CANCEL_SECRET
  from .env
- Creates unauthenticated ccxt Kraken instance
  for public data
- Creates authenticated ccxt Kraken instance
  using cancel-only credentials
- Returns the authenticated instance
- Return None if credentials missing or invalid

#### 2. fetch_all_open_orders
- Input: exchange (cancel-only ccxt instance)
- Fetches all open orders across all trading pairs
- Returns list of order dictionaries
- Returns empty list if no open orders
- Return None on failure

#### 3. cancel_single_order
- Inputs: order_id (str), symbol (str),
  exchange (cancel-only ccxt instance)
- Cancels one specific order
- Logs the cancellation with order details
- Returns True if cancelled, False if failed

#### 4. cancel_all_orders
- Input: exchange (cancel-only ccxt instance)
- Fetches all open orders
- Cancels each one individually
- Logs every cancellation attempt
- Output: dictionary with keys:
  total_found (int)
  total_cancelled (int)
  failed (list of order IDs that failed)
  timestamp (datetime)

#### 5. send_emergency_alert
- Inputs: cancel_result (dictionary),
  reason (str)
- Sends Telegram alert to authorised user:
  DEAD MANS SWITCH TRIGGERED
  ──────────────────────────
  Reason: Main bot heartbeat lost (5 minutes)
  Time: 14:23 UTC
  Orders Cancelled: 3 of 3
  Assets: BTC/USD, ETH/USD, SOL/USD
  ──────────────────────────
  All positions are now unprotected.
  Log in to Kraken immediately to review.

#### 6. run_emergency_cancel
- Main function called when heartbeat fails
- Creates cancel-only client
- Cancels all orders
- Sends Telegram alert
- Logs everything to logs/dead_mans_switch.log
- Returns True if completed successfully

## dead_mans_switch/heartbeat_monitor.py

### PURPOSE
Runs continuously on the monitor server.
Watches for heartbeat from main bot.
Triggers emergency cancel if heartbeat stops.

### HEARTBEAT MECHANISM
Main bot writes current UTC timestamp to:
data/heartbeat.txt every 60 seconds

Monitor reads this file every 30 seconds
If timestamp is older than 300 seconds:
Emergency cancel fires

### FUNCTIONS

#### 1. write_heartbeat
- Called by main bot every 60 seconds
- Writes current UTC timestamp to heartbeat file
- Creates file if not exists
- Returns True if written successfully
- This function runs on the MAIN server

#### 2. read_heartbeat
- Reads timestamp from heartbeat file
- Returns datetime object
- Returns None if file missing or unreadable
- This function runs on the MONITOR server

#### 3. check_heartbeat_alive
- Input: timeout_seconds (int) = 300
- Reads heartbeat file
- If file missing: return False (dead)
- If timestamp older than timeout: return False
- Otherwise: return True (alive)

#### 4. monitor_loop
- Runs continuously on monitor server
- Checks heartbeat every 30 seconds
- Tracks consecutive failed checks
- If 10 consecutive failures (5 minutes):
  Calls run_emergency_cancel from emergency_cancel.py
  Sends Telegram alert
  Waits 60 seconds before checking again
  Does NOT fire repeatedly — only once per outage
- Logs every check to logs/dead_mans_switch.log

#### 5. start_monitor
- Entry point for monitor server
- Logs monitor started with timestamp
- Calls monitor_loop
- Handles KeyboardInterrupt gracefully

#### 6. get_monitor_status
- Returns dictionary with keys:
  last_heartbeat (datetime or None)
  seconds_since_heartbeat (float)
  status (str) — ALIVE or DEAD
  consecutive_failures (int)
  emergency_fired (bool)

## ERROR HANDLING
- Every function wrapped in try/except
- If cancel-only key is invalid log CRITICAL error
  and send Telegram alert immediately
- If Telegram alert fails log to file — never crash
- If heartbeat file cannot be read assume dead
  and trigger emergency cancel
- Log all events to logs/dead_mans_switch.log
  with timestamps

## LOGGING
- Separate log file: logs/dead_mans_switch.log
- Every heartbeat check logged at DEBUG level
- Every failed check logged at WARNING level
- Emergency cancel trigger logged at CRITICAL level
- Every order cancellation logged at INFO level

## TEST
At bottom of heartbeat_monitor.py in
if __name__ == '__main__': block:

1. Test write_heartbeat:
   Write heartbeat to test file
   Print Heartbeat written: PASS or FAIL

2. Test read_heartbeat:
   Read the file just written
   Print timestamp read back
   Print PASS or FAIL

3. Test check_heartbeat_alive with fresh heartbeat:
   Expected: True (alive)
   Print PASS or FAIL

4. Test check_heartbeat_alive with old timestamp:
   Write timestamp 10 minutes ago to file
   Expected: False (dead)
   Print PASS or FAIL

5. Test get_monitor_status:
   Print full status dictionary

6. Test create_cancel_only_client:
   Attempt to create client with .env credentials
   Print Connected: PASS or FAIL
   Note: only tests connection not actual cancellation

7. Test fetch_all_open_orders:
   Fetch current open orders using cancel-only key
   Print count of open orders found
   Print PASS or FAIL

8. Test cancel_all_orders in dry run mode:
   Do NOT actually cancel real orders during test
   Instead verify the function logic runs without
   errors using mock order list
   Print PASS or FAIL

9. Print MODULE 22 — DEAD MANS SWITCH:
   ALL TESTS PASSED if all criteria met

## SUCCESS CRITERIA
- write_heartbeat creates file correctly
- check_heartbeat_alive returns False on old timestamp
- cancel-only client connects to Kraken
- fetch_all_open_orders returns without error
- cancel_all_orders logic runs without crashing
- Emergency alert formatted correctly
- All events logged to dead_mans_switch.log

## IMPORTANT FINAL INSTRUCTIONS
- Create files at exactly these paths:
  dead_mans_switch/heartbeat_monitor.py
  dead_mans_switch/emergency_cancel.py
- The cancel-only API key MUST be different from
  the main trading API key
- NEVER use the main KRAKEN_API_KEY in this module
  Only use KRAKEN_CANCEL_KEY
- Do NOT actually cancel real open orders during
  testing — use mock data for cancel tests
- The monitor runs as a completely separate process
  from the main trading system
- write_heartbeat is called by the main bot
  read_heartbeat and monitor_loop run on second server
- Dead mans switch must NEVER place trades
  It can only cancel orders
