# Prompt 03 — Hurst Exponent

## CONTEXT
This is Module 3 of 22. Module 02 OHLCV Fetcher must be
complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 03 — Hurst Exponent
File created: core/hurst.py
Test results: [show actual output]
Type APPROVED to proceed to Module 04 — Autocorrelation

Do not proceed until user types: APPROVED

## FILE TO CREATE
core/hurst.py

## PURPOSE
Calculates the Hurst Exponent for a price series. This is
the primary signal in the Decision Engine. It tells the
system whether a market is trending, mean-reverting, or
random. This single number drives which trading strategy
gets activated and how large the position size will be.

## WHAT HURST MEANS
- H > 0.55 = TRENDING — momentum persists
- H < 0.45 = MEAN_REVERTING — price snaps back
- H 0.45 to 0.55 = DEAD_ZONE — no strong edge
- Further from 0.5 in either direction = stronger edge

## DEPENDENCIES
- numpy
- pandas
- logging
- config.py for HURST_LOOKBACK = 100

## NO CLASS — plain functions only

## FUNCTIONS TO BUILD

### 1. calculate
- Input: prices (pandas Series or numpy array)
- Output: float between 0 and 1, rounded to 4
  decimal places
- Method: Rescaled Range R/S Analysis:
  Step 1: Calculate log returns
  Step 2: Split returns into chunks of n/2,
    n/4, n/8 — minimum chunk size 8
  Step 3: For each chunk size calculate R/S:
    Mean-adjust returns in each chunk
    Calculate cumulative deviation from mean
    R = max(cumulative) - min(cumulative)
    S = standard deviation of returns
    RS = R/S for each chunk
    Average RS across all chunks of that size
  Step 4: H = slope of log(chunk sizes) vs
    log(average RS) linear regression
- Return None if fewer than 20 prices
- Return None if calculation fails

### 2. calculate_with_confidence
- Input: prices (pandas Series or numpy array)
- Output: dictionary with keys:
  hurst (float)
  confidence (float) — R-squared of regression
  regime (string) — TRENDING, MEAN_REVERTING,
    or DEAD_ZONE
  trend_factor (float):
    max(0, (H - 0.5) / (0.7 - 0.5)) clipped 0 to 1
  reversion_factor (float):
    max(0, (0.5 - H) / (0.5 - 0.3)) clipped 0 to 1

### 3. rolling_hurst
- Inputs: prices (pandas Series),
  window (int) = HURST_LOOKBACK
- Output: pandas Series of Hurst values over time
- None for candles without enough data yet

## ERROR HANDLING
- Every function wrapped in try/except
- Return None on failure
- Never raise exceptions
- Log errors to logs/errors.log

## TEST
At bottom in if __name__ == '__main__': block:

1. Create TRENDING series — 200 points:
   Start at 100, small positive increment plus noise
   Expected H > 0.55
   Print result and PASS or FAIL

2. Create MEAN REVERTING series — 200 points:
   Oscillating around fixed mean of 100
   Expected H < 0.45
   Print result and PASS or FAIL

3. Create RANDOM WALK series — 200 points:
   numpy random cumulative sum
   Expected H near 0.5
   Print result

4. Test calculate_with_confidence on trending series
   Print full dictionary

5. Test rolling_hurst on trending series
   Print last 5 values

6. Print MODULE 03 — HURST EXPONENT: ALL TESTS PASSED
   only if trending H > 0.55 AND reverting H < 0.45

## SUCCESS CRITERIA
- Trending series returns H above 0.55
- Mean reverting series returns H below 0.45
- Random walk returns H near 0.5
- calculate_with_confidence returns all required keys
- rolling_hurst returns a pandas Series

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 03 — Hurst Exponent
File created: core/hurst.py
Trending H: [value] — PASS or FAIL
Reverting H: [value] — PASS or FAIL
Type APPROVED to proceed to Module 04 — Autocorrelation
