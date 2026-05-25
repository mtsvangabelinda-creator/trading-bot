# Prompt 06 — Realized Volatility Ratio

## CONTEXT
This is Module 6 of 22. Module 05 PEC must be complete
and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 06 — RVR
File created: core/rvr.py
Test results: [show actual output]
Type APPROVED to proceed to Module 07 — Edge Score

Do not proceed until user types: APPROVED

## FILE TO CREATE
core/rvr.py

## PURPOSE
Calculates the Realized Volatility Ratio. Measures whether
current market volatility is normal, dangerously high, or
suspiciously dead. Fourth and final signal feeding into the
Composite Edge Score. Controls position sizing safety.

## WHAT RVR MEANS
- RVR > 1.5 = DANGER — energy spiking, halve positions
- RVR 0.8 to 1.5 = NORMAL — strategies run freely
- RVR < 0.8 = DEAD — scalper only, no trend trades

## FORMULA
RVR = ATR(short period 5) / ATR(long period 20)

True Range per candle = max of:
  High - Low
  |High - Previous Close|
  |Low - Previous Close|
ATR = rolling average of True Range

## DEPENDENCIES
- numpy
- pandas
- logging
- config.py for:
  RVR_DANGER_THRESHOLD = 1.5
  RVR_DEAD_THRESHOLD = 0.8
  CHAOTIC_ATR_MULTIPLIER = 2.0

## NO CLASS — plain functions only

## FUNCTIONS TO BUILD

### 1. calculate_atr
- Inputs: high (pandas Series), low (pandas Series),
  close (pandas Series), period (int) = 14
- Output: pandas Series of ATR values
- Calculate True Range first then rolling mean
- Return None if fewer than period+1 values

### 2. calculate
- Inputs: high, low, close (pandas Series),
  short_period (int) = 5, long_period (int) = 20
- Output: float rounded to 4 decimal places
- Uses most recent ATR values from each period
- Return None if ATR calculation fails
- Return None if long ATR is zero

### 3. calculate_with_signal
- Inputs: high, low, close (pandas Series)
- Output: dictionary with keys:
  rvr (float)
  regime (string) — DANGER, NORMAL, or DEAD
  size_multiplier (float):
    DANGER = 0.5
    NORMAL = 1.0
    DEAD = 0.0
  atr_short (float)
  atr_long (float)
  interpretation (string):
    DANGER: Volatility spike — position sizes halved
    NORMAL: Normal volatility — full sizing active
    DEAD: Dead market — scalper only

### 4. chaotic_tripwire
- Inputs: high, low, close (pandas Series),
  multiplier (float) = CHAOTIC_ATR_MULTIPLIER
- Purpose: Always-on emergency override
  Fires when ATR spikes suddenly and dramatically
- Logic:
  current ATR = ATR period 5
  baseline ATR = ATR period 20
  If current > baseline × multiplier: CHAOTIC
- Output: dictionary with keys:
  triggered (boolean)
  current_atr (float)
  baseline_atr (float)
  ratio (float)
  message (string):
    If triggered: CHAOTIC TRIPWIRE FIRED —
      all new entries blocked
    If not: Normal — tripwire not triggered

### 5. rolling_rvr
- Inputs: high, low, close (pandas Series),
  window (int) = 50
- Output: pandas Series of RVR values over time

## ERROR HANDLING
- Every function wrapped in try/except
- Return None on failure
- Never raise exceptions
- Log errors to logs/errors.log

## TEST
At bottom in if __name__ == '__main__': block:

1. Create NORMAL volatility dataset — 200 candles:
   Close: trending upward with small noise
   High = close + small random amount
   Low = close - small random amount
   Expected RVR between 0.8 and 1.5
   Print result and PASS or FAIL

2. Create DANGER dataset:
   Normal for 190 candles then last 10 candles
   have very large high-low ranges (10x normal)
   Expected RVR above 1.5
   Print result and PASS or FAIL

3. Create DEAD dataset:
   Very tiny high-low ranges throughout
   Expected RVR below 0.8
   Print result and PASS or FAIL

4. Test calculate_with_signal on all three
   Print full dictionary for each

5. Test chaotic_tripwire:
   On DANGER dataset — Expected triggered = True
   On NORMAL dataset — Expected triggered = False
   Print both results and PASS or FAIL

6. Test rolling_rvr on normal dataset
   Print last 5 values

7. Print MODULE 06 — RVR: ALL TESTS PASSED
   only if all 4 criteria pass

## SUCCESS CRITERIA
- Normal RVR between 0.8 and 1.5
- Danger RVR above 1.5
- Dead RVR below 0.8
- Chaotic tripwire fires on danger not normal

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 06 — RVR
File created: core/rvr.py
Normal RVR: [value] — PASS or FAIL
Danger RVR: [value] — PASS or FAIL
Dead RVR: [value] — PASS or FAIL
Tripwire on danger: [triggered] — PASS or FAIL
Tripwire on normal: [triggered] — PASS or FAIL
Type APPROVED to proceed to Module 07 — Edge Score
