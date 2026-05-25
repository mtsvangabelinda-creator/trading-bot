# Prompt 10 — Drawdown Guard

## CONTEXT
This is Module 10 of 22. Module 09 Position Sizer must be
complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 10 — Drawdown Guard
File created: risk/drawdown_guard.py
Test results: [show actual output]
Type APPROVED to proceed to Module 11 — Strategy Silo

Do not proceed until user types: APPROVED

## FILE TO CREATE
risk/drawdown_guard.py

## PURPOSE
Monitors account-level drawdown and enforces hard halts
when loss limits are breached. Primary safety net for the
whole account. Tracks three independent drawdown measurements
simultaneously and fires the appropriate halt when any one
is breached.

## THE THREE MEASUREMENTS

1. PEAK DRAWDOWN — tracks from all-time high
   If account drops 15% from highest ever value
   all new entries stop immediately
   Requires 24 hour cool-off before reactivation

2. INTRADAY DRAWDOWN — resets every UTC midnight
   If account loses 5% in a single UTC day
   all new entries stop for rest of that day
   Automatically resets at UTC midnight

3. ROLLING WEEKLY LOSS — rolling 7 day window
   If account loses 10% over any 7 day period
   trading stops until next Monday UTC midnight

## HALT STATES
ACTIVE = trading normally
PEAK_HALT = peak drawdown limit breached
INTRADAY_HALT = intraday limit breached
WEEKLY_HALT = weekly limit breached
COOLOFF = mandatory 24 hour rest after peak halt

## DEPENDENCIES
- aiosqlite
- datetime
- logging
- config.py for:
  MAX_ACCOUNT_DRAWDOWN = 0.15
  INTRADAY_DRAWDOWN = 0.05
  WEEKLY_LOSS_LIMIT = 0.10

## NO CLASS — plain functions only
## Use 'data/test_drawdown.db' for all tests
## Use 'data/trading_data.db' for production

## FUNCTIONS TO BUILD

### 1. init_db
- Creates table drawdown_history if not exists
- Columns: id, timestamp, account_value,
  peak_value, daily_start_value,
  weekly_start_value, halt_state, note
- Creates table halt_log if not exists
- Columns: id, timestamp, halt_type,
  account_value, trigger_pct, resolved_at
- Returns True if successful

### 2. update
- Inputs: account_value (float),
  db_path (string) = 'data/trading_data.db'
- Process:
  Load most recent record from drawdown_history
  If no record: initialise all values to current
  Update peak if account_value is higher
  Check if UTC date changed: reset daily_start
  Check if 7 days passed: reset weekly_start
  Calculate all three drawdown percentages:
    peak_dd = (peak - current) / peak
    intraday_dd = (daily_start - current) /
      daily_start
    weekly_dd = (weekly_start - current) /
      weekly_start
  Determine halt_state
  Save new record
- Output: dictionary with keys:
  account_value (float)
  peak_value (float)
  peak_drawdown_pct (float)
  intraday_drawdown_pct (float)
  weekly_drawdown_pct (float)
  halt_state (string)
  peak_halt_triggered (boolean)
  intraday_halt_triggered (boolean)
  weekly_halt_triggered (boolean)
  cooloff_active (boolean)
  cooloff_ends_at (datetime or None)
  alert_message (string or None)

### 3. is_trading_allowed
- Input: db_path (string)
- Output: dictionary with keys:
  allowed (boolean)
  halt_state (string)
  reason (string)
  resume_at (datetime or None)
- Called before every signal generation

### 4. record_halt
- Inputs: halt_type (string),
  account_value (float),
  trigger_pct (float), db_path (string)
- Saves halt event to halt_log
- Returns True if saved

### 5. resolve_halt
- Inputs: halt_type (string), db_path (string)
- Updates most recent unresolved halt with
  resolved_at = current UTC time
- Returns True if resolved

### 6. get_status
- Input: db_path (string)
- Output: formatted Telegram string:
  Current Account: $X,XXX.XX
  Peak Value: $X,XXX.XX
  Peak Drawdown: X.XX% (limit 15%)
  Intraday Loss: X.XX% (limit 5%)
  Weekly Loss: X.XX% (limit 10%)
  Status: ACTIVE or HALTED
  Resume At: [time if halted]

### 7. simulate
- Inputs: values (list of floats),
  db_path (string)
- Runs update() for each value in sequence
- Returns list of halt states produced
- Used for testing only

## ERROR HANDLING
- Every function wrapped in try/except
- Return None on failure
- Log critical events to logs/risk.log
- Log errors to logs/errors.log
- All datetime operations use UTC timezone

## TEST
At bottom in if __name__ == '__main__': block:
Use db_path = 'data/test_drawdown.db'

1. Initialise test database
   Print Database initialised

2. Test normal trading — no halts:
   Simulate values: 1000, 1010, 1020, 1015, 1025
   All should return ACTIVE
   Print PASS or FAIL

3. Test intraday halt:
   Start at 1000, drop to 949
   That is 5.1% loss — should trigger INTRADAY_HALT
   Print halt state and alert message
   Print PASS or FAIL

4. Test peak drawdown halt:
   Start at 1000, rise to 1100 (new peak)
   Then drop to 930 (15.45% from peak of 1100)
   Should trigger PEAK_HALT
   Print halt state and alert message
   Print PASS or FAIL

5. Test is_trading_allowed after peak halt:
   Expected: allowed = False
   Print result and PASS or FAIL

6. Test get_status:
   Print full formatted status string

7. Test resolve_halt:
   Resolve the PEAK_HALT
   Call is_trading_allowed again
   Print result

8. Print MODULE 10 — DRAWDOWN GUARD: ALL TESTS PASSED
   only if all criteria pass

9. Delete test database after all tests complete

## SUCCESS CRITERIA
- Normal sequence all return ACTIVE
- 5.1% intraday drop triggers INTRADAY_HALT
- 15.5% peak drop triggers PEAK_HALT
- is_trading_allowed returns False when halted
- Test database deleted after tests

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 10 — Drawdown Guard
File created: risk/drawdown_guard.py
Normal sequence: PASS or FAIL
Intraday halt: PASS or FAIL
Peak halt: PASS or FAIL
Trading blocked when halted: PASS or FAIL
Type APPROVED to proceed to Module 11 — Strategy Silo
