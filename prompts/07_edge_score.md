# Prompt 07 — Composite Edge Score

## CONTEXT
This is Module 7 of 22. This is the most important module
in the entire system. Module 06 RVR must be complete and
APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 07 — Edge Score
File created: core/edge_score.py
Test results: [show actual output]
Type APPROVED to proceed to Module 08 — Sentiment

Do not proceed until user types: APPROVED

## FILE TO CREATE
core/edge_score.py

## PURPOSE
Combines all four signals — Hurst, Autocorrelation, PEC,
and RVR — into a single Composite Edge Score. This score
tells the system which strategy to run and exactly how
large the position should be. This is the brain that makes
every trading decision.

## HOW IT WORKS
Step 1: Calculate all four signals
Step 2: Check Chaotic Tripwire first
  If triggered: return zero for everything, block all
Step 3: Combine Hurst, Autocorr, PEC into strategy scores
  Using weights from config EDGE_SCORE_WEIGHTS:
  hurst: 0.4, autocorr: 0.3, pec: 0.3
Step 4: Multiply by RVR size multiplier
  DANGER: multiply by 0.5
  NORMAL: multiply by 1.0
  DEAD: multiply by 0.0 for trend and reversion
Step 5: Output final scores and decision

## SCORING FORMULAS
TF_raw = (hurst_trend_factor × 0.4) +
         (autocorr_trend_factor × 0.3) +
         (pec_trend_factor × 0.3)
TF_final = TF_raw × RVR_size_multiplier

MR_raw = (hurst_reversion_factor × 0.4) +
         (autocorr_reversion_factor × 0.3) +
         (pec_reversion_factor × 0.3)
MR_final = MR_raw × RVR_size_multiplier

Scalper base score = 0.5
  DEAD market: stays 0.5 (only active strategy)
  DANGER market: reduced to 0.25
  NORMAL market: stays 0.5
  Never zero unless Chaotic Tripwire fires

## STRATEGY SELECTION
- Chaotic Tripwire fired: ALL BLOCKED
- TF_final > MR_final AND TF_final > 0.3:
  PRIMARY = TREND_FOLLOWING
- MR_final > TF_final AND MR_final > 0.3:
  PRIMARY = MEAN_REVERSION
- Both <= 0.3: PRIMARY = SCALPER (dead zone)
- Scalper always runs alongside primary unless
  Chaotic Tripwire fired

## DEPENDENCIES
- from core.hurst import calculate_with_confidence
- from core.autocorrelation import calculate_with_signal
- from core.pec import calculate_with_signal as
  pec_calculate_with_signal
- from core.rvr import calculate_with_signal as
  rvr_calculate_with_signal
- from core.rvr import chaotic_tripwire
- numpy
- pandas
- logging
- config.py for EDGE_SCORE_WEIGHTS

## NO CLASS — plain functions only

## CONSTANTS AT TOP OF FILE
ACTIVATION_THRESHOLD = 0.3
SCALPER_BASE_SCORE = 0.5
SCALPER_DANGER_SCORE = 0.25

## FUNCTIONS TO BUILD

### 1. calculate
- Inputs: close (pandas Series),
  high (pandas Series), low (pandas Series)
- Output: dictionary with ALL these keys:

  RAW SIGNAL VALUES:
  hurst (float)
  hurst_regime (string)
  hurst_confidence (float)
  autocorr (float)
  autocorr_signal (string)
  pec (float)
  pec_signal (string)
  rvr (float)
  rvr_regime (string)

  CHAOTIC TRIPWIRE:
  chaotic (boolean)
  chaotic_ratio (float)

  EDGE SCORES:
  tf_score (float) 0 to 1
  mr_score (float) 0 to 1
  scalper_score (float) 0 to 0.5

  DECISION:
  primary_strategy (string) — TREND_FOLLOWING,
    MEAN_REVERSION, SCALPER, or BLOCKED
  position_size_factor (float) — multiply against
    base position size
  confidence (float) — overall confidence
  reasoning (string) — plain English explanation
    of exactly why this decision was made

- Return None if calculation fails

### 2. calculate_all
- Input: dictionary where keys are asset names
  and values are dictionaries with close, high,
  low pandas Series
- Output: dictionary where keys are asset names
  and values are full edge score dictionaries
- Process each asset independently
- If one fails continue to next and log error

### 3. get_summary
- Input: output from calculate_all
- Output: clean formatted string for Telegram:
  BTC/USD: TREND_FOLLOWING (score: 0.74) —
    Hurst=0.61, RVR=NORMAL
  ETH/USD: MEAN_REVERSION (score: 0.52) —
    Hurst=0.43, RVR=NORMAL
  SOL/USD: BLOCKED — Chaotic Tripwire fired

## ERROR HANDLING
- Every function wrapped in try/except
- If single signal fails use None and continue
- If more than 2 signals fail return None
- Log all errors to logs/errors.log

## TEST
At bottom in if __name__ == '__main__': block:

1. Build TRENDING dataset — 200 candles:
   Close: steady upward drift from 100
   High = close × 1.002
   Low = close × 0.998
   Run calculate() and print full output
   Expected: primary_strategy = TREND_FOLLOWING

2. Build MEAN REVERTING dataset — 200 candles:
   Close: sine wave oscillating around 100
   High and Low constructed same way
   Run calculate() and print full output
   Expected: primary_strategy = MEAN_REVERSION

3. Build CHAOTIC dataset:
   Normal for 190 candles then last 10 candles
   have extremely large ranges (20x normal)
   Expected: chaotic = True, strategy = BLOCKED

4. Build DEAD ZONE dataset:
   Pure random walk prices
   Small consistent volatility
   Expected: primary_strategy = SCALPER

5. Test calculate_all with two assets:
   BTC/USD = trending data
   ETH/USD = mean reverting data
   Print results for both

6. Test get_summary on calculate_all output
   Print formatted summary string

7. Print MODULE 07 — EDGE SCORE: ALL TESTS PASSED
   only if all four strategies correctly selected

## SUCCESS CRITERIA
- Trending data returns TREND_FOLLOWING
- Reverting data returns MEAN_REVERSION
- Chaotic data returns BLOCKED
- Dead zone data returns SCALPER
- reasoning string is descriptive not placeholder

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 07 — Edge Score
File created: core/edge_score.py
Trending: [strategy] — PASS or FAIL
Reverting: [strategy] — PASS or FAIL
Chaotic: [strategy] — PASS or FAIL
Dead zone: [strategy] — PASS or FAIL
Type APPROVED to proceed to Module 08 — Sentiment
