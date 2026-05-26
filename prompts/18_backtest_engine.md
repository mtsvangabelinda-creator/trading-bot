# Prompt 18 — Backtest Engine

## CONTEXT
This is Module 18 of 24. Module 17 Micro Scalping must be
complete and APPROVED before starting this module.

IMPORTANT: Modules 03 through 08 already contain the complete
Decision Engine — hurst.py, autocorrelation.py, pec.py,
rvr.py, edge_score.py, and sentiment.py. Do NOT rebuild or
modify any of those files. The backtest engine imports and
uses them as they are.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 18 — Backtest Engine
File created: backtest/engine.py, backtest/simulator.py,
backtest/metrics.py
Test results: [show actual output]
Type APPROVED to proceed to Module 19 — Stress Tester

Do not proceed until user types: APPROVED

## FILES TO CREATE
backtest/engine.py
backtest/simulator.py
backtest/metrics.py

## PURPOSE
Runs historical backtests across all 5 assets using 5 years
of OHLCV data. Simulates all three strategies simultaneously
using the real Decision Engine, real risk management, and
real position sizing. Produces performance metrics to validate
the system before going live.

## BACKTESTING RULES
- Use 5 years of historical data minimum
- Run all 5 assets sequentially to manage memory
- Simulate all three strategies simultaneously per asset
- Apply all risk rules during backtest:
  Drawdown halts, strategy silo pauses, correlation
  breaker, time filters, sentinel (simplified)
- Include realistic fees: Kraken maker 0.16%, taker 0.26%
- No lookahead bias — decisions made only on data
  available at that point in time
- Walk-forward validation: train on first 4 years,
  test on final year

## DEPENDENCIES
- from core.edge_score import calculate
- from core.sentiment import calculate as sentiment_calc
- from risk.position_sizer import calculate as size_calc
- from risk.drawdown_guard import update as dd_update
- from risk.strategy_silo import register_trade_outcome
- from risk.correlation_breaker import calculate_matrix
- from risk.time_filters import get_size_multiplier
- from data.ohlcv_fetcher import OHLCVFetcher, load_ohlcv
- pandas, numpy, logging, datetime
- config.py for all constants

## backtest/simulator.py

### PURPOSE
Simulates order fills with realistic fees and slippage.
No real exchange connection — all simulated.

### FUNCTIONS

#### 1. simulate_market_order
- Inputs: direction (str), size (float),
  current_price (float), fee_rate (float) = 0.0026
- Simulates taker fill with fee
- Output: dictionary with keys:
  filled_price (float)
  fee_paid (float)
  net_cost (float)
  slippage (float) = 0.0005 simulated

#### 2. simulate_stop_hit
- Inputs: stop_price (float), candle_low (float),
  candle_high (float), direction (str)
- Returns True if stop was hit on this candle
- Long stop hit if candle_low <= stop_price
- Short stop hit if candle_high >= stop_price

#### 3. simulate_take_profit_hit
- Inputs: tp_price (float), candle_low (float),
  candle_high (float), direction (str)
- Returns True if take profit was hit on this candle

#### 4. calculate_pnl
- Inputs: direction (str), entry_price (float),
  exit_price (float), size (float),
  entry_fee (float), exit_fee (float)
- Returns float — net PnL in USD after fees

## backtest/metrics.py

### PURPOSE
Calculates performance statistics from backtest results.

### FUNCTIONS

#### 1. calculate_sharpe
- Inputs: returns (list of floats),
  risk_free_rate (float) = 0.0
- Output: float — annualised Sharpe ratio

#### 2. calculate_max_drawdown
- Input: equity_curve (list of floats)
- Output: dictionary with keys:
  max_drawdown_pct (float)
  max_drawdown_usd (float)
  drawdown_start (int — index)
  drawdown_end (int — index)
  recovery_index (int or None)

#### 3. calculate_win_rate
- Input: trades (list of dicts with pnl key)
- Output: dictionary with keys:
  win_rate (float)
  total_trades (int)
  winning_trades (int)
  losing_trades (int)
  avg_win (float)
  avg_loss (float)
  profit_factor (float)

#### 4. calculate_all_metrics
- Input: trades (list), equity_curve (list)
- Output: dictionary with all metrics combined:
  sharpe_ratio, max_drawdown_pct,
  max_drawdown_usd, win_rate, total_trades,
  winning_trades, losing_trades, avg_win,
  avg_loss, profit_factor, total_return_pct,
  total_return_usd, avg_trades_per_day

#### 5. format_report
- Input: metrics dictionary, asset (str)
- Output: formatted string for display:

  BACKTEST REPORT — BTC/USD
  ─────────────────────────
  Period: 5 years
  Total Trades: 847
  Win Rate: 54.3%
  Profit Factor: 1.82
  Sharpe Ratio: 1.34
  Max Drawdown: 11.2% ($1,120)
  Total Return: 187.4% ($18,740)
  Avg Trades/Day: 0.46
  ─────────────────────────
  RESULT: PASSED — meets all criteria

## backtest/engine.py

### PURPOSE
Main backtest runner. Iterates through historical data
candle by candle, runs Decision Engine, generates signals,
simulates trades, tracks equity.

### FUNCTIONS

#### 1. run_backtest
- Inputs:
  asset (str)
  start_date (str) = '2020-01-01'
  end_date (str) = '2025-01-01'
  initial_capital (float) = 10000.0
  db_path (str) = 'data/trading_data.db'
- Process:
  Load OHLCV data for asset from database
  Initialise equity curve at initial_capital
  Iterate candle by candle from start to end:
    Run edge_score.calculate on last 200 candles
    Run sentiment.calculate on last 200 candles
    Check time_filters.get_size_multiplier
    Check drawdown_guard state
    Check strategy_silo state per strategy
    For each active strategy:
      Calculate signal
      If signal exists:
        Calculate position size
        Simulate order fill
        Track open position
    For each open position:
      Check if stop hit or take profit hit
      If exit triggered:
        Calculate PnL
        Record trade
        Update equity
        Update drawdown_guard
        Update strategy_silo
  Return dictionary with keys:
    trades (list of trade dicts)
    equity_curve (list of floats)
    metrics (from calculate_all_metrics)
    asset (str)
    start_date (str)
    end_date (str)

#### 2. run_all_assets
- Inputs:
  start_date (str) = '2020-01-01'
  end_date (str) = '2025-01-01'
  initial_capital (float) = 10000.0
- Runs run_backtest for each of 5 assets
  sequentially — not simultaneously
- Waits for each to complete before next
- Returns dictionary of asset to backtest result

#### 3. run_walk_forward
- Inputs:
  asset (str)
  initial_capital (float) = 10000.0
- Splits data: train on 2020-2024, test on 2024-2025
- Runs backtest on test period only
- Returns test period results

#### 4. print_summary
- Input: results from run_all_assets
- Prints formatted report for all 5 assets
- Flags any asset that fails success criteria

## SUCCESS CRITERIA FOR BACKTEST
Only proceed to live trading if ALL pass:
- Max drawdown below 15% on every asset
- Win rate above 45% on every asset
- Sharpe ratio above 1.0 on every asset
- Consecutive loss days under 7
- No single asset loses more than 20% of capital
- System does not breach 15% account halt in
  any backtest scenario

## ERROR HANDLING
- Every function wrapped in try/except
- If data missing for an asset log warning and skip
- Never crash entire backtest for one asset failure
- Log all errors to logs/errors.log
- Log backtest progress to logs/backtest.log

## TEST
At bottom in if __name__ == '__main__': block:

1. Test simulator — simulate_market_order:
   Price 45000, size 0.1 BTC, direction long
   Print filled_price, fee_paid, net_cost
   Verify fee equals approximately 0.26% of notional

2. Test simulate_stop_hit:
   Stop at 44000, candle low 43800
   Expected: True
   Stop at 44000, candle low 44200
   Expected: False
   Print both results and PASS or FAIL

3. Test metrics with sample trade list:
   Create 20 mock trades — 12 winners 8 losers
   Expected win rate 60%
   Print full metrics output

4. Test calculate_max_drawdown:
   Equity curve: 10000 11000 10500 9800 10200
   Print drawdown percentage

5. Test run_backtest on BTC/USD:
   Use last 30 days only for speed (start_date
   set to 30 days ago)
   Print number of trades generated
   Print equity curve start and end values
   Print metrics summary

6. Test format_report:
   Print formatted report from test 5

7. Print MODULE 18 — BACKTEST ENGINE:
   ALL TESTS PASSED if all criteria met

## IMPORTANT FINAL INSTRUCTIONS
- Create files at exactly these paths:
  backtest/engine.py
  backtest/simulator.py
  backtest/metrics.py
- Do NOT modify any existing modules
- Do NOT rebuild the Decision Engine —
  import it from core/edge_score.py
- Use 5 years of data for full backtest
  (2020-01-01 to 2025-01-01)
- Use only 30 days for the test run to
  keep testing fast
- No lookahead bias — never use future data
  to make past decisions
- Fees must be applied on every trade
