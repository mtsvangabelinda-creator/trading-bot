# Prompt 16 – Mean Reversion Strategy

## CONTEXT
Module 15 Trend Following Strategy must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 16 – Mean Reversion Strategy
File created: strategies/mean_reversion.py
Test results: [show actual output]
Type APPROVED to proceed to Module 17 – Micro Scalping Strategy

Do not proceed until user types: APPROVED.

## FILE TO CREATE
strategies/mean_reversion.py

## PURPOSE
Implements the mean reversion strategy that buys when price dips too low and sells when it rises too high within a stable range. Uses the Composite Edge Score from the Decision Engine, but inverted (high mean reversion edge = low trend edge). Places trades counter to short-term moves with tight stops.

## RULES FROM SPEC
- Max loss per trade: 1% of that asset's capital
- Stop-loss placed beyond recent extreme or 1.5× ATR
- Entry when price deviates by >1.5× ATR from short-term moving average
- Position size = base_size × mean_reversion_edge_score (where MR_edge = 1 - TF_edge roughly, but spec says MR_edge = inverse of TF_edge)
- Only trade in direction allowed by Structural Sentiment (bullish = only long entries for MR, bearish = only short entries, neutral = both)
- Consecutive loss limit: 6 losses → pause 24h (handled by silo, but strategy should track local consecutive losses for logging)

## DEPENDENCIES
- numpy, pandas, logging, datetime
- config.py: BASE_RISK_PCT=0.01, ATR_PERIOD=14, ATR_MULTIPLIER=1.5, MR_CONSEC_LOSS_LIMIT=6 (for info)
- core/hurst.py, autocorrelation.py, pec.py, rvr.py (via edge score)
- risk/position_sizer.py (Module 09)
- sentinel/sentinel.py (Module 14)
- data/ohlcv_fetcher.py (Module 02)

## FUNCTIONS

1. calculate_mr_edge_score(trend_edge_score)
   - Input: trend-following edge score (0-1 from Decision Engine)
   - Output: mean reversion edge score = 1 - trend_edge_score (clamped 0-1)
   - Simple inversion per spec

2. calculate_entry_signal(symbol, ohlcv_df, mr_edge_score, sentiment_direction, atr_multiplier=1.5, lookback=20)
   - Calculate short-term SMA (e.g., 20 periods)
   - Calculate deviation = (current_price - sma) / atr
   - If deviation < -1.5 and sentiment allows long → long entry signal
   - If deviation > 1.5 and sentiment allows short → short entry signal
   - Also require mr_edge_score > 0.3
   - Output dict: direction (long/short/none), confidence (based on deviation magnitude and edge_score), price_level (the entry trigger price)

3. calculate_stop_loss(symbol, ohlcv_df, direction, entry_price, atr_multiplier=1.5)
   - For long: entry_price - (ATR × 1.5) or lowest of last 10 periods
   - For short: entry_price + (ATR × 1.5) or highest of last 10 periods
   - Returns price

4. calculate_position_size(symbol, capital_usd, mr_edge_score, risk_percent=0.01, atr_value=None)
   - Uses position_sizer from Module 09
   - Final size = base_size × mr_edge_score
   - Returns size in base currency

5. execute_trade(symbol, direction, size_usd, exchange, dry_run=True)
   - Same as trend following: market order
   - Returns dict with success, order_id, filled_price, actual_size

6. place_stop_order(symbol, stop_price, direction, size, exchange, dry_run=True)
   - Places stop-loss order

7. check_strategy_pause()
   - Calls is_strategy_allowed('mean_reversion') from Module 11
   - Returns bool

8. run_strategy_iteration(symbol, capital_usd, trend_edge_score, sentiment, ohlcv_df, exchange, sentinel, dry_run=True)
   - Compute mr_edge_score = 1 - trend_edge_score
   - Check sentinel, silo pause
   - Get entry signal
   - If entry: calculate stop, position size, execute trade, place stop
   - Returns dict: trade_executed, details

## ERROR HANDLING
- Try/except each function
- Log to logs/strategies.log
- On failure, skip trade

## TESTS (in if __name__ == '__main__':)
Mock data and dummy exchange.

1. Test MR edge score inversion – trend_edge=0.8 → mr_edge=0.2. PASS/FAIL.
2. Test entry signal long – price 1.6 ATR below SMA, sentiment bullish, mr_edge=0.6 → direction=long. PASS/FAIL.
3. Test entry signal short – price 1.6 ATR above SMA, sentiment bearish → short. PASS/FAIL.
4. Test sentiment block – bullish sentiment but deviation positive (price > SMA) → no entry. PASS/FAIL.
5. Test low edge score – mr_edge=0.2 → no entry. PASS/FAIL.
6. Test stop loss calculation – verify stop is beyond recent extreme. PASS/FAIL.
7. Test position size – capital 1000, mr_edge=0.6 → size = base_size × 0.6. PASS/FAIL.
8. Test sentinel block – red light → no trade. PASS/FAIL.
9. Test silo pause – False → no trade. PASS/FAIL.
10. Print "MODULE 16 – MEAN REVERSION: ALL TESTS PASSED"

## SUCCESS CRITERIA
- MR edge correctly derived from trend edge
- Entry only when deviation >1.5 ATR and sentiment aligned
- Position size scaled by mr_edge_score
- Respects sentinel and silo gates

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 16 – Mean Reversion Strategy
File created: strategies/mean_reversion.py
Edge inversion test: PASS or FAIL
Entry long test: PASS or FAIL
Entry short test: PASS or FAIL
Sentiment block test: PASS or FAIL
Stop loss test: PASS or FAIL
Silo pause test: PASS or FAIL
Type APPROVED to proceed to Module 17 – Micro Scalping Strategy
