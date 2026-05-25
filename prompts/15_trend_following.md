# Prompt 15 – Trend Following Strategy

## CONTEXT
Module 14 Sentinel must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 15 – Trend Following Strategy
File created: strategies/trend_following.py
Test results: [show actual output]
Type APPROVED to proceed to Module 16 – Mean Reversion Strategy

Do not proceed until user types: APPROVED.

## FILE TO CREATE
strategies/trend_following.py

## PURPOSE
Implements the trend-following strategy that catches directional moves. Uses the Composite Edge Score from the Decision Engine (Modules 03-08) to determine position size. Places trades in the direction of the trend with a hard stop-loss outside known liquidity voids.

## RULES FROM SPEC
- Max loss per trade: 1-2% of that asset's capital
- Stop-loss placed beyond recent swing point or ATR multiple
- Entry: when trend-following edge score > threshold (from config)
- Position size = base_size × edge_score (from Decision Engine)
- Only trades in direction of Structural Sentiment (from Module 08)

## DEPENDENCIES
- numpy, pandas, logging, datetime
- config.py: BASE_RISK_PCT=0.01, ATR_PERIOD=14, ATR_MULTIPLIER=1.5
- core/hurst.py, autocorrelation.py, pec.py, rvr.py (for edge score – will be integrated later, but placeholder calls)
- risk/position_sizer.py (Module 09)
- sentinel/sentinel.py (Module 14)
- data/ohlcv_fetcher.py (Module 02)

## FUNCTIONS

1. calculate_entry_signal(symbol, ohlcv_df, edge_score, sentiment_direction)
   - Input: OHLCV DataFrame, current trend-following edge score (float 0-1), sentiment ('bullish','bearish','neutral')
   - Output: dict with keys: 'direction' (long/short/none), 'confidence' (float), 'reason' (string)
   - Only trade if edge_score > 0.3 (minimum threshold) and sentiment matches direction (bullish=long only, bearish=short only, neutral=both)

2. calculate_stop_loss(symbol, ohlcv_df, direction, atr_multiplier=1.5, lookback=20)
   - For long: low of last lookback periods minus ATR × atr_multiplier
   - For short: high of last lookback periods plus ATR × atr_multiplier
   - Returns price (float)

3. calculate_position_size(symbol, capital_usd, edge_score, risk_percent=0.01, atr_value=None)
   - Uses position_sizer from Module 09 (or placeholder: base_size = capital_usd × risk_percent / (atr × 1.5))
   - Final size = base_size × edge_score
   - Returns size in base currency (e.g., BTC)

4. execute_trade(symbol, direction, size_usd, exchange, dry_run=True)
   - Places market order if dry_run=False
   - Returns dict: success (bool), order_id (str), filled_price (float), actual_size

5. place_stop_order(symbol, stop_price, direction, size, exchange, dry_run=True)
   - Places stop-loss order at stop_price
   - Returns order details

6. check_strategy_pause(strategy_silo_module)
   - Calls is_strategy_allowed('trend_following') from Module 11
   - Returns bool

7. run_strategy_iteration(symbol, capital_usd, edge_score, sentiment, ohlcv_df, exchange, sentinel, dry_run=True)
   - Orchestrates: check sentinel → check silo pause → calculate signal → stop price → position size → execute trade → place stop
   - Returns dict: trade_executed (bool), details

## ERROR HANDLING
- Try/except each function
- Log to logs/strategies.log
- On any failure, skip trade

## TESTS (in if __name__ == '__main__':)
Mock data and dummy exchange.

1. Test entry signal – edge_score 0.6, bullish sentiment -> direction=long, confidence high. PASS/FAIL.
2. Test block – edge_score 0.2 -> none. PASS/FAIL.
3. Test sentiment mismatch – bearish sentiment but long signal -> none. PASS/FAIL.
4. Test stop loss calculation – verify price is outside recent range. PASS/FAIL.
5. Test position size – capital 1000, risk 0.01, edge_score 0.8 -> size = (1000*0.01)/(atr*1.5) * 0.8. PASS/FAIL.
6. Test sentinel block – mock sentinel returns red light -> trade not executed. PASS/FAIL.
7. Test strategy silo pause – mock is_strategy_allowed False -> no trade. PASS/FAIL.
8. Print "MODULE 15 – TREND FOLLOWING: ALL TESTS PASSED"

## SUCCESS CRITERIA
- Entry only when edge_score > threshold and sentiment aligned
- Stop loss calculated correctly
- Position size incorporates edge_score
- Sentinel and silo gates respected

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 15 – Trend Following Strategy
File created: strategies/trend_following.py
Entry signal test: PASS or FAIL
Stop loss test: PASS or FAIL
Position size test: PASS or FAIL
Sentinel block test: PASS or FAIL
Silo pause test: PASS or FAIL
Type APPROVED to proceed to Module 16 – Mean Reversion Strategy
