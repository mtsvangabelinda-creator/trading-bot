# Prompt 09 — Position Sizer

## CONTEXT
This is Module 9 of 22. Module 08 Sentiment must be
complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 09 — Position Sizer
File created: risk/position_sizer.py
Test results: [show actual output]
Type APPROVED to proceed to Module 10 — Drawdown Guard

Do not proceed until user types: APPROVED

## FILE TO CREATE
risk/position_sizer.py

## PURPOSE
Calculates the exact position size for every trade signal.
Combines three layers — ATR base sizing, Edge Score
multiplier, and RVR safety multiplier — into one final
number that tells the trader exactly how much to buy or
sell. Turns analysis into a precise actionable size.

## THE FORMULA
Final Size = Base Size × Edge Score × RVR Multiplier

Base Size = (Asset Capital × Risk%) / (ATR × ATR_MULTIPLIER)
Edge Score = winning strategy score from Module 07
RVR Multiplier = from Module 06:
  NORMAL = 1.0
  DANGER = 0.5
  DEAD = 0.0

## EXAMPLE
Asset capital = $1,000
Risk% = 1% = $10 at risk
ATR = 50
ATR_MULTIPLIER = 1.5
Base Size = $10 / (50 × 1.5) = 0.1333 units
Edge Score = 0.74
RVR Multiplier = 1.0
Final Size = 0.1333 × 0.74 × 1.0 = 0.0987 units

## DEPENDENCIES
- from core.rvr import calculate_atr
- numpy
- pandas
- logging
- config.py for:
  ATR_PERIOD = 14
  ATR_MULTIPLIER = 1.5
  BASE_RISK_PCT = 0.01
  ASSETS dictionary

## NO CLASS — plain functions only

## FUNCTIONS TO BUILD

### 1. calculate_base_size
- Inputs:
  asset_capital (float)
  close (pandas Series)
  high (pandas Series)
  low (pandas Series)
  risk_pct (float) = BASE_RISK_PCT
- Output: dictionary with keys:
  base_size (float)
  dollar_risk (float)
  atr (float)
  atr_multiplier (float)
- Return None if ATR fails

### 2. calculate
- Inputs:
  asset_capital (float)
  close (pandas Series)
  high (pandas Series)
  low (pandas Series)
  edge_score (float) — winning strategy score
  rvr_multiplier (float) — 1.0, 0.5, or 0.0
  risk_pct (float) = BASE_RISK_PCT
- Output: dictionary with keys:
  final_size (float) — rounded to 4 decimal places
  final_size_usd (float)
  base_size (float)
  dollar_risk (float)
  atr (float)
  edge_score (float)
  rvr_multiplier (float)
  current_price (float)
  size_breakdown (string) — plain English:
    Base: 0.1333 units × Edge 0.74 × RVR 1.0
    = 0.0987 units ($4,127.50 at $41,800)
- If final_size rounds to 0.0000 return None
- If position would exceed 10% of asset capital
  log warning and cap at 10%
- Return None if calculation fails

### 3. calculate_all
- Inputs:
  total_capital (float)
  market_data (dict — asset to close/high/low)
  edge_scores (dict — asset to edge score dict)
  rvr_results (dict — asset to RVR result dict)
- For each asset:
  asset_capital = total_capital × allocation
  from config ASSETS dictionary
  Extract edge_score and rvr_multiplier
  Call calculate()
- Output: dict of asset to position size result

### 4. format_signal
- Inputs:
  asset (string)
  direction (string) — long or short
  strategy (string)
  size_result (dict from calculate)
  sentiment (string)
  edge_result (dict from Module 07)
- Output: formatted Telegram string:

  TRADE SIGNAL — BTC/USD
  ──────────────────────
  Strategy: Trend-Following
  Direction: LONG
  Position Size: 0.0987 BTC
  Position Value: $4,127.50
  Dollar Risk: $41.28 (1% of $4,127.50)
  Entry: Market order now
  Stop Loss Distance: 1.5 × ATR ($62.70)
  ──────────────────────
  Edge Score: 0.74 (strong)
  Hurst: 0.61 (TRENDING)
  RVR: NORMAL — full size
  Sentiment: BULLISH — long only
  ──────────────────────
  Manually place this order on Kraken now.

## ERROR HANDLING
- Every function wrapped in try/except
- Return None on failure
- Log errors to logs/errors.log

## TEST
At bottom in if __name__ == '__main__': block:
Use BTC-like prices: close trending 40000 to 45000
High = close × 1.002, Low = close × 0.998
200 candles total

1. Test calculate_base_size:
   Asset capital = $1,000
   Print full output
   Verify dollar_risk is approximately $10

2. Test calculate with strong edge:
   Edge score = 0.80, RVR = 1.0 (NORMAL)
   Asset capital = $1,000
   Print full output including size_breakdown

3. Test calculate with weak edge:
   Edge score = 0.25, RVR = 1.0
   Verify final_size smaller than test 2

4. Test calculate with DANGER RVR:
   Edge score = 0.80, RVR = 0.5
   Verify final_size exactly half of test 2

5. Test calculate with DEAD RVR:
   Edge score = 0.80, RVR = 0.0
   Expected: returns None

6. Test format_signal:
   Use result from test 2
   Direction = long, Strategy = TREND_FOLLOWING
   Sentiment = BULLISH
   Print full formatted Telegram signal

7. Print MODULE 09 — POSITION SIZER: ALL TESTS PASSED
   only if all criteria pass

## SUCCESS CRITERIA
- dollar_risk in test 1 between $9 and $11
- test 3 final_size less than test 2
- test 4 final_size exactly half of test 2
- test 5 returns None
- format_signal includes Manually place this
  order on Kraken now at the bottom

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 09 — Position Sizer
File created: risk/position_sizer.py
Dollar risk test: [value] — PASS or FAIL
Weak edge smaller: PASS or FAIL
Danger half size: PASS or FAIL
Dead returns None: PASS or FAIL
Type APPROVED to proceed to Module 10 — Drawdown Guard
