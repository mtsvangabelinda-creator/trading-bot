# Prompt 05 — Price Efficiency Coefficient

## CONTEXT
This is Module 5 of 22. Module 04 Autocorrelation must be
complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 05 — PEC
File created: core/pec.py
Test results: [show actual output]
Type APPROVED to proceed to Module 06 — RVR

Do not proceed until user types: APPROVED

## FILE TO CREATE
core/pec.py

## PURPOSE
Calculates the Price Efficiency Coefficient. Measures whether
price moved efficiently in one direction or wasted energy
moving back and forth. Third of four signals feeding into
the Composite Edge Score.

## WHAT PEC MEANS
- PEC near 1.0 = price moved in straight line = TREND_SIGNAL
- PEC near 0.0 = price went nowhere = REVERSION_SIGNAL
- PEC always between 0 and 1

## FORMULA
PEC = |Price_End - Price_Start| / Sum of |all individual moves|

Example:
Prices: 100, 102, 101, 103, 105
Net move = |105 - 100| = 5
Individual moves = |2| + |-1| + |2| + |2| = 7
PEC = 5 / 7 = 0.714

## DEPENDENCIES
- numpy
- pandas
- logging

## NO CLASS — plain functions only

## CONSTANTS AT TOP OF FILE
TREND_THRESHOLD = 0.6
REVERSION_THRESHOLD = 0.4

## FUNCTIONS TO BUILD

### 1. calculate
- Input: prices (pandas Series or numpy array)
- Output: float between 0 and 1, rounded to 4
  decimal places
- Use formula above exactly
- Return None if fewer than 3 prices
- Return None if sum of moves is zero
- Return None if calculation fails

### 2. calculate_with_signal
- Input: prices (pandas Series or numpy array)
- Output: dictionary with keys:
  pec (float)
  signal (string) — TREND_SIGNAL if pec > 0.6,
    REVERSION_SIGNAL if pec < 0.4, else NEUTRAL
  trend_factor (float):
    max(0, (pec - 0.5) / 0.5) clipped 0 to 1
  reversion_factor (float):
    max(0, (0.5 - pec) / 0.5) clipped 0 to 1
  interpretation (string) — plain English:
    pec > 0.6: Price moving efficiently — trend likely
    pec < 0.4: Price churning — mean reversion likely
    else: Price movement inconclusive

### 3. rolling_pec
- Inputs: prices (pandas Series),
  window (int) = 20
- Output: pandas Series of PEC values over time

### 4. multi_window_pec
- Inputs: prices (pandas Series or numpy array),
  windows (list) = [10, 20, 50]
- Output: dictionary with window as key and
  PEC value as value
  Example: {10: 0.82, 20: 0.71, 50: 0.65}

## ERROR HANDLING
- Every function wrapped in try/except
- Return None on failure
- Never raise exceptions
- Log errors to logs/errors.log

## TEST
At bottom in if __name__ == '__main__': block:

1. Test perfectly efficient series:
   Prices: 100, 101, 102, 103, 104, 105
   Expected PEC = 1.0
   Print result and PASS or FAIL

2. Test perfectly inefficient series:
   Prices: 100, 102, 100, 102, 100, 102, 100
   Expected PEC near 0.0
   Print result and PASS or FAIL

3. Create TRENDING series — 200 points
   Expected PEC above 0.6
   Print result and PASS or FAIL

4. Create MEAN REVERTING series — 200 points
   Expected PEC below 0.4
   Print result and PASS or FAIL

5. Test calculate_with_signal on both series
   Print full dictionary including interpretation

6. Test multi_window_pec on trending series
   Print full output

7. Test rolling_pec on trending series
   Print last 5 values

8. Print MODULE 05 — PEC: ALL TESTS PASSED
   only if all 4 criteria pass

## SUCCESS CRITERIA
- Straight line returns PEC = 1.0
- Zigzag returns PEC near 0.0
- Trending series returns PEC above 0.6
- Reverting series returns PEC below 0.4

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 05 — PEC
File created: core/pec.py
Straight line PEC: [value] — PASS or FAIL
Zigzag PEC: [value] — PASS or FAIL
Trending PEC: [value] — PASS or FAIL
Reverting PEC: [value] — PASS or FAIL
Type APPROVED to proceed to Module 06 — RVR
