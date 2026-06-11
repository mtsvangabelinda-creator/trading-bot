# Autonomous Multi-Strategy Trading System
# Master Configuration File
# All system constants live here
# Never hardcode these values in other modules

# ── Assets and capital allocation ─────────────────────────────
ASSETS = {
    'BTC/USD': 0.25,
    'ETH/USD': 0.25,
    'SOL/USD': 0.20,
    'BNB/USD': 0.15,
    'XRP/USD': 0.15,
}

# ── Decision Engine ───────────────────────────────────────────
HURST_LOOKBACK         = 100
EDGE_SCORE_WEIGHTS     = {
    'hurst':   0.35,
    'autocorr': 0.25,
    'pec':     0.25,
    'rvr':     0.15
}
REGIME_CHECK_INTERVAL  = 900
SENTIMENT_INTERVAL     = 3600
CHAOTIC_ATR_MULTIPLIER = 2.0

# ── Multi-Timeframe Bias ───────────────────────────────────────
BIAS_SMA_PERIOD        = 50
BIAS_NEUTRAL_BAND      = 0.005

# ── Position Sizing ───────────────────────────────────────────
ATR_PERIOD             = 14
ATR_MULTIPLIER         = 1.5
BASE_RISK_PCT          = 0.01
RVR_DANGER_THRESHOLD   = 1.5
RVR_DEAD_THRESHOLD     = 0.8

# ── Risk Limits ───────────────────────────────────────────────
MAX_ACCOUNT_DRAWDOWN   = 0.15
INTRADAY_DRAWDOWN      = 0.05
WEEKLY_LOSS_LIMIT      = 0.10
STRATEGY_DRAWDOWN      = 0.10
MR_CONSEC_LOSS_LIMIT   = 6
TF_CONSEC_LOSS_LIMIT   = 4
SCALPER_DAILY_LOSS     = 0.05

# ── Correlation Circuit Breaker ───────────────────────────────
CORR_HALVE_THRESHOLD   = 0.8
CORR_PAUSE_THRESHOLD   = 0.7
CORR_CHECK_INTERVAL    = 14400

# ── Sentinel ──────────────────────────────────────────────────
SPREAD_MULTIPLIER      = 2.0
SLIPPAGE_TOLERANCE     = 0.003
LIQUIDITY_DEPTH_PCT    = 0.005
VOLUME_DRYUP_SECS      = 300

# ── Time Filters ──────────────────────────────────────────────
SETTLEMENT_START           = '23:45'
SETTLEMENT_END             = '00:15'
SETTLEMENT_SIZE_REDUCTION  = 0.5

# ── Dead Mans Switch ──────────────────────────────────────────
HEARTBEAT_INTERVAL     = 60
HEARTBEAT_TIMEOUT      = 300

# ── Backtesting ───────────────────────────────────────────────
BACKTEST_YEARS         = 5
BACKTEST_START_DATE    = '2020-01-01'
BACKTEST_END_DATE      = '2025-01-01'
MAKER_FEE              = 0.0016
TAKER_FEE              = 0.0026

# ── Walk-Forward Backtesting ───────────────────────────────────
WALK_FORWARD_MONTHS           = 18
WALK_FORWARD_LOOKBACK_MONTHS  = 3

# ── Logging ───────────────────────────────────────────────────
LOG_MAX_BYTES          = 10485760
LOG_BACKUP_COUNT       = 7
