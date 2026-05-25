# Prompt 04 — Autocorrelation

## CONTEXT
This is Module 4 of 22. Module 03 Hurst Exponent must be
complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 04 — Autocorrelation
File created: core/autocorrelation.py
Test results: [show actual output]
Type APPROVED to proceed to Module 05 — PEC

Do not proceed until user types: APPROVED

## FILE TO CREATE
core/autocorrelation.py

## PURPOSE
Calculates Autocorrelation for a price series. Confirms
the Hurst Exponent from a different mathematical angle.
Measures whether the last price move predicts the next one.
Second of four signals feeding into the Composite Edge Score.

## WHAT AUTOCORRELATION MEANS
- Positive > 0.05 = TREND_EDGE — moves continue
- Negative < -0.05 = REVERSION_EDGE — moves reverse
- Between -0.05 and 0.05 = NEUTRAL — no prediction

## DEPENDENCIES
- numpy
- pandas
- scipy.stats
- logging

## NO CLASS — plain functions only

## FUNCTIONS TO BUILD

### 1. calculate
- Inputs: prices (pandas Series or numpy array),
  lag (int) = 1
- Output: float between -1 and 1, rounded to 4
  decimal places
- Method:
  Step 1: returns = price[t] - price[t-1]
  Step 2: Pearson correlation between
    returns[:-lag] and returns[lag:]
  Step 3: Return correlation coefficient
- Return None if fewer than 20 prices
- Return None if calculation fails

### 2. calculate_with_signal
- Input: prices (pandas Series or numpy array)
- Output: dictionary with keys:
  autocorr (float)
  signal (string) — TREND_EDGE, REVERSION_EDGE,
    or NEUTRAL
  strength (float) — absolute value of autocorr
  trend_factor (float):
    max(0, autocorr) clipped to 0 to 1
  reversion_factor (float):
    max(0, -autocorr) clipped to 0 to 1

### 3. multi_lag
- Inputs: prices (pandas Series or numpy array),
  lags (list) = [1, 2, 3, 5]
- Output: dictionary with lag as key and
  autocorrelation as value
  Example: {1: 0.23, 2: 0.18, 3: 0.11, 5: 0.07}

### 4. rolling_autocorr
- Inputs: prices (pandas Series),
  window (int) = 50, lag (int) = 1
- Output: pandas Series of autocorrelation values

## ERROR HANDLING
- Every function wrapped in try/except
- Return None on failure
- Never raise exceptions
- Log errors to logs/errors.log

## TEST
At bottom in if __name__ == '__main__': block:

1. Create TRENDING series — 200 points:
   Same as Module 03 trending series
   Expected: positive autocorr above 0.05
   Print result and PASS or FAIL

2. Create MEAN REVERTING series — 200 points:
   Same as Module 03 reverting series
   Expected: negative autocorr below -0.05
   Print result and PASS or FAIL

3. Test calculate_with_signal on both series
   Print full dictionary for each

4. Test multi_lag on trending series
   Print full output — confirm decay across lags

5. Test rolling_autocorr on trending series
   Print last 5 values

6. Print MODULE 04 — AUTOCORRELATION: ALL TESTS PASSED
   only if trending is positive AND reverting is negative

## SUCCESS CRITERIA
- Trending series returns positive autocorrelation
- Mean reverting series returns negative autocorrelation
- calculate_with_signal returns all required keys
- multi_lag shows decay across lags
- rolling_autocorr returns pandas Series

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 04 — Autocorrelation
File created: core/autocorrelation.py
Trending autocorr: [value] — PASS or FAIL
Reverting autocorr: [value] — PASS or FAIL
Type APPROVED to proceed to Module 05 — PEC
