# Prompt 08 — Structural Sentiment

## CONTEXT
This is Module 8 of 22. Module 07 Edge Score must be
complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 08 — Structural Sentiment
File created: core/sentiment.py
Test results: [show actual output]
Type APPROVED to proceed to Module 09 — Position Sizer

Do not proceed until user types: APPROVED

## FILE TO CREATE
core/sentiment.py

## PURPOSE
Calculates the Market Structural Sentiment for each asset.
This is the higher-timeframe directional bias — it tells
the system the macro trend direction regardless of which
strategy is active. Prevents the system from fighting the
bigger trend with small-timeframe counter-trades.

## WHAT SENTIMENT MEANS
- BULLISH = macro trend up — only LONG entries allowed
- BEARISH = macro trend down — only SHORT entries allowed
- NEUTRAL = no clear direction — both directions allowed

## HOW SENTIMENT IS CALCULATED
Three indicators must agree:

Indicator 1 — EMA Trend:
  Fast EMA period 20, Slow EMA period 50
  Fast > Slow AND positive slope = BULLISH
  Fast < Slow AND negative slope = BEARISH
  Otherwise = NEUTRAL

Indicator 2 — Price Position:
  Close > EMA50 by more than 1% = BULLISH
  Close < EMA50 by more than 1% = BEARISH
  Otherwise = NEUTRAL

Indicator 3 — Hurst Confirmation:
  Hurst > 0.55 AND EMA = BULLISH = confirms BULLISH
  Hurst > 0.55 AND EMA = BEARISH = confirms BEARISH
  Hurst < 0.55 = weakens conviction = may push NEUTRAL

FINAL RULE:
  All three BULLISH = BULLISH high conviction
  All three BEARISH = BEARISH high conviction
  Two of three BULLISH = BULLISH moderate conviction
  Two of three BEARISH = BEARISH moderate conviction
  Any other = NEUTRAL

## DEPENDENCIES
- from core.hurst import calculate_with_confidence
- numpy
- pandas
- logging
- config.py for SENTIMENT_INTERVAL

## NO CLASS — plain functions only

## CONSTANTS AT TOP OF FILE
EMA_FAST = 20
EMA_SLOW = 50
PRICE_POSITION_THRESHOLD = 0.01
BULLISH = 'BULLISH'
BEARISH = 'BEARISH'
NEUTRAL = 'NEUTRAL'

## FUNCTIONS TO BUILD

### 1. calculate_ema
- Inputs: prices (pandas Series), period (int)
- Output: pandas Series of EMA values
- Use pandas ewm method
- Return None if fewer than period values

### 2. calculate
- Inputs: close (pandas Series),
  high (pandas Series) optional = None,
  low (pandas Series) optional = None
- Output: dictionary with keys:
  sentiment (string) — BULLISH, BEARISH, NEUTRAL
  conviction (string) — HIGH, MODERATE, or LOW
  ema_fast (float)
  ema_slow (float)
  ema_signal (string)
  price_signal (string)
  hurst_signal (string)
  hurst_value (float)
  bullish_count (int)
  bearish_count (int)
  allowed_directions (list):
    BULLISH: ['long']
    BEARISH: ['short']
    NEUTRAL: ['long', 'short']
  reasoning (string) — plain English explanation

### 3. calculate_all
- Input: dictionary of asset name to close/high/low
- Output: dictionary of asset name to sentiment result
- Process each asset independently
- If one fails continue to next

### 4. get_summary
- Input: output from calculate_all
- Output: formatted Telegram string:
  BTC/USD: BULLISH (HIGH conviction) — LONG only
  ETH/USD: BEARISH (MODERATE conviction) — SHORT only
  SOL/USD: NEUTRAL — both directions allowed

### 5. direction_allowed
- Inputs: sentiment_result (dict from calculate),
  direction (string) — long or short
- Output: boolean
- True if direction is in allowed_directions
- Called before every trade signal

## ERROR HANDLING
- Every function wrapped in try/except
- If Hurst fails use NEUTRAL for that indicator
- Return None on total failure
- Log errors to logs/errors.log

## TEST
At bottom in if __name__ == '__main__': block:

1. Create strongly BULLISH dataset — 200 candles:
   Close trending steadily from 100 to 150
   Expected: sentiment = BULLISH
   Print result and PASS or FAIL

2. Create strongly BEARISH dataset — 200 candles:
   Close trending steadily from 150 to 100
   Expected: sentiment = BEARISH
   Print result and PASS or FAIL

3. Create NEUTRAL dataset — 200 candles:
   Close moving sideways around 100 with noise
   Expected: sentiment = NEUTRAL
   Print result and PASS or FAIL

4. Test direction_allowed on BULLISH result:
   direction_allowed(result, 'long') = True
   direction_allowed(result, 'short') = False
   Print both and PASS or FAIL

5. Test calculate_all with three assets:
   BTC/USD = bullish data
   ETH/USD = bearish data
   SOL/USD = neutral data
   Print all results

6. Test get_summary and print output

7. Print MODULE 08 — SENTIMENT: ALL TESTS PASSED
   only if all four criteria pass

## SUCCESS CRITERIA
- Bullish dataset returns BULLISH
- Bearish dataset returns BEARISH
- Neutral dataset returns NEUTRAL
- direction_allowed correctly blocks short on bullish

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 08 — Structural Sentiment
File created: core/sentiment.py
Bullish test: [result] — PASS or FAIL
Bearish test: [result] — PASS or FAIL
Neutral test: [result] — PASS or FAIL
Direction filter: PASS or FAIL
Type APPROVED to proceed to Module 09 — Position Sizer
