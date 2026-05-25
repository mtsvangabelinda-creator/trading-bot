# Prompt 17 – Micro Scalping Strategy

## CONTEXT
Module 16 Mean Reversion Strategy must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 17 – Micro Scalping Strategy
File created: strategies/scalper.py
Test results: [show actual output]
Type APPROVED to proceed to Module 18 – Decision Engine (Composite Edge Score)

Do not proceed until user types: APPROVED.

## FILE TO CREATE
strategies/scalper.py

## PURPOSE
Implements the micro scalping strategy that takes many small profits from short-term price fluctuations throughout the day. Runs even in dead zone (Hurst 0.45-0.55) with small directional bias from Structural Sentiment. No consecutive loss limit, but has daily loss limit (5% of scalper silo). Takes small, frequent trades with very tight stops.

## RULES FROM SPEC
- Max daily loss: 5% of scalper silo capital → pause for the day (handled by silo, but strategy should check)
- No consecutive loss limit
- Position size: very small (e.g., 0.1× normal base size, or configurable)
- Target profit: small (e.g., 0.2% – 0.5% per trade)
- Stop loss: very tight (e.g., 0.3% – 0.5%)
- In dead zone (when Decision Engine has no clear trend or MR edge): use small directional bias from Structural Sentiment (bullish = bias long, bearish = bias short, neutral = no bias)
- When edge exists (trend or MR), scalper can also run but with reduced size? Spec says "Scalper Augmentation Mode" – we'll keep scalper always active but with different bias.

## DEPENDENCIES
- numpy, pandas, logging, datetime, random (for small variation)
- config.py: SCALPER_DAILY_LOSS=0.05, BASE_RISK_PCT=0.002 (0.2% risk per scalp trade), SCALPER_SIZE_REDUCTION=0.1 (relative to normal base size)
- risk/strategy_silo.py (Module 11) for checking daily loss limit
- sentinel/sentinel.py (Module 14)
- data/ohlcv_fetcher.py (Module 02)

## FUNCTIONS

1. calculate_scalp_signal(symbol, ohlcv_df, sentiment_bias, dead_zone_flag=False, edge_score_trend=None)
   - Input: OHLCV DataFrame (last 10-20 candles), sentiment_bias ('bullish','bearish','neutral'), dead_zone_flag (bool), edge_score_trend (float 0-1, optional)
   - If dead_zone_flag and sentiment_bias != neutral:
        bias = sentiment_bias (long only if bullish, short only if bearish)
   - Else if not dead_zone and edge_score_trend is not None:
        if edge_score_trend > 0.5: bias direction = trend direction (from sentiment or price action)
        else: bias = neutral (scalp both sides)
   - Generate signal based on short-term price action (e.g., pullback to moving average, RSI extremes, or simple order flow)
   - Simplified approach: look at last 3 candles; if price down 0.1% and bias long → buy; if price up 0.1% and bias short → sell; else none.
   - Output dict: direction (long/short/none), confidence (0-1), price_level (current price), reason

2. calculate_position_size(symbol, capital_usd, scalper_size_reduction=0.1, risk_percent=0.002, atr_value=None)
   - Base size = capital_usd × risk_percent / (atr × 1.5) or fixed small notional (e.g., $10)
   - Final size = base_size × scalper_size_reduction
   - Returns size in base currency

3. calculate_stop_loss(symbol, entry_price, direction, atr_value=None, stop_percent=0.005)
   - Long: entry_price × (1 - stop_percent)
   - Short: entry_price × (1 + stop_percent)
   - Returns price

4. calculate_take_profit(entry_price, direction, target_percent=0.003)
   - Long: entry_price × (1 + target_percent)
   - Short: entry_price × (1 - target_percent)
   - Returns price

5. check_daily_loss_allowed(symbol_silo_module, db_path='data/trading_data.db')
   - Calls is_strategy_allowed('scalper') from Module 11
   - Returns bool

6. execute_scalp_trade(symbol, direction, size_usd, stop_price, take_profit_price, exchange, dry_run=True)
   - Places market order for size, then immediately places stop and limit take-profit orders
   - Returns dict: success, order_ids, filled_price

7. run_scalper_iteration(symbol, capital_usd, sentiment_bias, dead_zone_flag, edge_score_trend, ohlcv_df, exchange, sentinel, scalper_silo_module, dry_run=True)
   - Check sentinel (green light)
   - Check daily loss allowed via silo
   - Get signal
   - If signal direction != none:
        calculate position size, stop, take profit
        execute trade
   - Returns dict: trade_executed, details

## ERROR HANDLING
- Try/except each function
- Log to logs/strategies.log
- On any failure, skip trade

## TESTS (in if __name__ == '__main__':)
Mock data and dummy exchange.

1. Test dead zone with bullish bias – dead_zone_flag=True, sentiment='bullish' → signal can be long, not short. PASS/FAIL.
2. Test dead zone with neutral bias – no directional signal. PASS/FAIL.
3. Test non-dead zone with high trend edge – bias should follow trend direction. PASS/FAIL.
4. Test position size reduction – capital 1000, scalper_size_reduction=0.1 → size is 10% of normal base. PASS/FAIL.
5. Test stop and target calculation – verify percentages. PASS/FAIL.
6. Test daily loss block – mock silo returns False → no trade. PASS/FAIL.
7. Test sentinel block – red light → no trade. PASS/FAIL.
8. Print "MODULE 17 – MICRO SCALPING: ALL TESTS PASSED"

## SUCCESS CRITERIA
- Scalper only trades with directional bias in dead zone
- Position size small relative to other strategies
- Stop and target orders placed correctly
- Respects daily loss limit and sentinel

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 17 – Micro Scalping Strategy
File created: strategies/scalper.py
Dead zone bias test: PASS or FAIL
Non-dead zone test: PASS or FAIL
Position size test: PASS or FAIL
Daily loss block test: PASS or FAIL
Sentinel block test: PASS or FAIL
Type APPROVED to proceed to Module 18 – Decision Engine (Composite Edge Score)
