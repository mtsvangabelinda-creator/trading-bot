# Prompt 18 – Decision Engine (Composite Edge Score)

## CONTEXT
Module 17 Micro Scalping Strategy must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 18 – Decision Engine
Files created: core/hurst.py, core/autocorrelation.py, core/pec.py, core/rvr.py, core/edge_score.py, core/sentiment.py
Test results: [show actual output]
Type APPROVED to proceed to Module 19 – Order Manager & Execution

Do not proceed until user types: APPROVED.

## FILES TO CREATE
core/hurst.py
core/autocorrelation.py
core/pec.py
core/rvr.py
core/edge_score.py
core/sentiment.py

## PURPOSE
Implements the Mathematical Decision Engine from spec. Runs every 15 minutes per asset, calculates four market signals, blends them into a Composite Edge Score for Trend-Following, and determines Structural Sentiment (macro bias). Also includes the Chaotic Tripwire that overrides everything when ATR spikes >2× its 20-period average.

## RULES FROM SPEC

### Signal 1: Hurst Exponent (H)
- H > 0.5 = trending (momentum persists)
- H < 0.5 = mean-reverting
- H = 0.5 = random walk (no edge)
- Formula: H = log(R/S) / log(n) where R = range of cumulative deviations, S = standard deviation

### Signal 2: Autocorrelation (lag 1)
- Positive = trend-following edge
- Negative = mean reversion edge
- Near zero = scalper only

### Signal 3: Price Efficiency Coefficient (PEC)
- PEC = |Price_end - Price_start| / sum of absolute moves
- PEC near 1.0 = efficient directional move → trend-following edge
- PEC near 0 = inefficient (lots of movement, little progress) → mean reversion edge

### Signal 4: Realized Volatility Ratio (RVR)
- RVR = ATR(5) / ATR(20)
- RVR > 1.5 = energy spiking → reduce exposure (multiplier 0.5)
- RVR 0.8–1.5 = normal
- RVR < 0.8 = dead market → scalper only (but still allow small positions)

### Composite Edge Score (spec formula)
- TF_edge = (hurst_factor × 0.4) + (autocorr_factor × 0.3) + (pec_factor × 0.3)
- MR_edge = 1 - TF_edge (inverse)

### Dead Zone Solution
- Hurst 0.45–0.55: no clear regime → deploy small positions scaled by weak edge, use Structural Sentiment as tiebreaker.

### Chaotic Tripwire (always on, bypasses cycle)
- Current ATR > 2 × ATR(20) → Chaotic mode → block all new entries.
- Stays blocked until ATR normalises for 2 consecutive candles.

### Structural Sentiment (updated every hour)
- Bullish: allow only long entries for MR and Scalper, TF can go long or short? Spec says MR and Scalper only long, TF can also follow trend both ways? We'll implement: sentiment affects all strategies: bullish → TF can take longs only (or both? safer to restrict all to long only), bearish → all short only, neutral → both.
- Updated hourly using higher timeframe trend (e.g., 4h EMA slope or price vs 200-period MA).

## DEPENDENCIES
- numpy, pandas, scipy.stats (for Hurst), math, logging, datetime
- config.py: HURST_LOOKBACK=100, EDGE_SCORE_WEIGHTS, REGIME_CHECK_INTERVAL=900, SENTIMENT_INTERVAL=3600, CHAOTIC_ATR_MULTIPLIER=2.0, ATR_PERIOD=14, ATR_PERIOD_FAST=5, ATR_PERIOD_SLOW=20
- data/ohlcv_fetcher.py (Module 02)
- data/trading_data.db (for storing latest edge scores, sentiment, tripwire state)

## FILE SPECIFICATIONS

### core/hurst.py
1. compute_hurst(price_series, lookback=None)
   - Input: list or array of prices, lookback (default config.HURST_LOOKBACK)
   - Compute R/S over log returns, return H (float 0-1)
2. hurst_factor(hurst_value)
   - Convert H to factor for TF_edge: if H > 0.55 → factor = (H-0.5)*2 (0 to 1), if H < 0.45 → factor = 0 (since negative gives MR edge), else factor = small based on proximity to 0.5.
   - Simpler: factor = max(0, min(1, (hurst_value - 0.5) * 5)) giving 0 at 0.5, 1 at 0.7.

### core/autocorrelation.py
1. compute_autocorrelation(price_series, lag=1)
   - Returns Pearson correlation of price series with shifted version.
2. autocorr_factor(autocorr_value)
   - Positive: factor = autocorr_value (clamped 0-1). Negative: factor = 0 (since negative gives MR edge, not TF). For TF_edge, we only want positive autocorrelation.

### core/pec.py
1. compute_pec(price_series)
   - Sum of absolute price changes denominator, net change absolute numerator.
   - Returns float 0-1.
2. pec_factor(pec_value)
   - Direct mapping: factor = pec_value (since high PEC = trending). For TF_edge.

### core/rvr.py
1. compute_rvr(ohlcv_df, fast_period=5, slow_period=20)
   - Compute ATR for fast and slow, return ratio = ATR_fast / ATR_slow.
2. get_rvr_multiplier(rvr_value)
   - RVR > 1.5 → 0.5, else 1.0 (safety multiplier for position sizing).
3. is_dead_market(rvr_value) → bool (rvr < 0.8)

### core/edge_score.py
1. compute_tf_edge(hurst, autocorr, pec)
   - tf_edge = (hurst_factor*0.4) + (autocorr_factor*0.3) + (pec_factor*0.3)
2. compute_mr_edge(tf_edge)
   - mr_edge = max(0, min(1, 1 - tf_edge))  # inverse, clamp
3. get_dead_zone_flag(hurst) → bool (0.45 <= H <= 0.55)
4. get_chaotic_tripwire(ohlcv_df, atr_multiplier=2.0, slow_period=20)
   - Compute current ATR and ATR(20). If current > atr_multiplier * ATR_slow, return (True, current_atr, atr_slow). Also track consecutive normal candles to deactivate.
   - This function should be stateful (store in DB or memory). We'll implement a simple class or use global variables for demo; for production, store in DB.

### core/sentiment.py
1. compute_structural_sentiment(ohlcv_df_4h, ema_period=200, lookback=20)
   - Determine higher timeframe trend: if price > EMA(200) and recent price action making higher highs → bullish. If price < EMA(200) → bearish. Else neutral.
   - Returns 'bullish', 'bearish', or 'neutral'.
2. update_sentiment(symbol, db_path='data/trading_data.db')
   - Store sentiment with timestamp, call every hour.

## FUNCTIONS IN edge_score.py (orchestration)
- run_decision_cycle(symbol, ohlcv_df, db_path='data/trading_data.db')
   - Compute hurst, autocorr, pec, rvr.
   - Get chaotic flag from tripwire.
   - If chaotic: return {'chaotic': True, 'trading_allowed': False}
   - Compute tf_edge, mr_edge.
   - Get dead_zone_flag.
   - Get sentiment.
   - Return dict: {
        'timestamp': now,
        'symbol': symbol,
        'hurst': float,
        'autocorr': float,
        'pec': float,
        'rvr': float,
        'tf_edge': float,
        'mr_edge': float,
        'dead_zone': bool,
        'chaotic': bool,
        'sentiment': str,
        'trading_allowed': not chaotic,
        'rvr_multiplier': float (0.5 or 1.0)
     }

## ERROR HANDLING
- Every function try/except, log to logs/decision_engine.log
- On failure, return safe defaults (e.g., tf_edge=0, trading_allowed=False)

## TESTS (in each file's __main__ and a combined test)
Use sample price data (sine wave for trending, random for mean-reverting).

1. Test hurst trending (sine wave) -> H > 0.5. PASS/FAIL.
2. Test hurst random -> H ~0.5. PASS/FAIL.
3. Test autocorrelation positive -> factor >0. PASS/FAIL.
4. Test PEC trending -> near 1.0. PASS/FAIL.
5. Test RVR calculation -> ratio correct. PASS/FAIL.
6. Test chaotic tripwire: create series with huge ATR spike -> chaotic True. PASS/FAIL.
7. Test dead zone: H=0.5 -> dead_zone True. PASS/FAIL.
8. Test sentiment: price above 200EMA -> bullish. PASS/FAIL.
9. Test TF_edge from sample values: expected range 0-1. PASS/FAIL.
10. Print "MODULE 18 – DECISION ENGINE: ALL TESTS PASSED"

## SUCCESS CRITERIA
- All four signals computed correctly
- Edge scores within [0,1]
- Chaotic tripwire blocks trading when ATR spikes
- Dead zone flag correctly identified
- Sentiment updated hourly (stub for scheduler)
- RVR multiplier applied

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 18 – Decision Engine
Files created: core/hurst.py, autocorrelation.py, pec.py, rvr.py, edge_score.py, sentiment.py
Hurst test: PASS or FAIL
Autocorr test: PASS or FAIL
PEC test: PASS or FAIL
RVR test: PASS or FAIL
Chaotic tripwire: PASS or FAIL
Edge score composition: PASS or FAIL
Type APPROVED to proceed to Module 19 – Order Manager & Execution
