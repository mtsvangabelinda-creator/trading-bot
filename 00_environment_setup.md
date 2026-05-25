# Prompt 00 — Environment Setup

## SYSTEM CONTEXT
You are building the Autonomous Multi-Strategy Trading System.
This is a cryptocurrency trading signal generator that analyzes
5 assets on Kraken exchange and sends trade signals via Telegram
for manual execution. The system runs on a cloud server 24/7.

## YOUR ROLE
You are a senior Python engineer. You write clean, production
grade code with full error handling, logging, type hints, and
docstrings on every function. You never skip steps. You never
move to the next task until the current one is fully complete
and tested.

## APPROVAL GATE RULE
After completing every task you must stop and display:

TASK COMPLETE — AWAITING APPROVAL
Output: [show what was created]
Type APPROVED to proceed to the next task.

You must not proceed until the user types: APPROVED

## TASK — CREATE PROJECT STRUCTURE

Create the following exact folder and file structure. For each
Python file create it with only a single comment line at the
top describing what it will do. Do not write any logic yet.

### Folder Structure:
trading-system/
├── core/
│   ├── __init__.py
│   ├── hurst.py
│   ├── autocorrelation.py
│   ├── pec.py
│   ├── rvr.py
│   ├── edge_score.py
│   └── sentiment.py
├── strategies/
│   ├── __init__.py
│   ├── trend_following.py
│   ├── mean_reversion.py
│   └── scalper.py
├── sentinel/
│   ├── __init__.py
│   ├── sentinel.py
│   ├── spoof_detector.py
│   └── liquidity_monitor.py
├── risk/
│   ├── __init__.py
│   ├── position_sizer.py
│   ├── drawdown_guard.py
│   ├── strategy_silo.py
│   ├── correlation_breaker.py
│   └── time_filters.py
├── execution/
│   ├── __init__.py
│   ├── kraken_client.py
│   ├── order_manager.py
│   └── stop_placer.py
├── data/
│   ├── __init__.py
│   ├── ohlcv_fetcher.py
│   ├── orderbook_stream.py
│   └── db.py
├── backtest/
│   ├── __init__.py
│   ├── engine.py
│   ├── simulator.py
│   ├── metrics.py
│   └── stress_test.py
├── telegram_bot/
│   ├── __init__.py
│   ├── bot.py
│   ├── commands.py
│   └── alerts.py
├── dead_mans_switch/
│   ├── __init__.py
│   ├── heartbeat_monitor.py
│   └── emergency_cancel.py
├── logs/
│   └── .gitkeep
├── scheduler.py
├── orchestrator.py
├── config.py
├── .env
├── .gitignore
├── requirements.txt
└── README.md

### .gitignore contents:
# Secrets
.env
*.env

# Python
__pycache__/
*.py[cod]
*.pyo
venv/
.venv/

# Database
*.db
*.sqlite
*.sqlite3

# Logs
logs/
*.log

# OS
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/

### requirements.txt contents:
ccxt==4.4.82
krakenex==2.1.0
aiohttp==3.9.5
websockets==12.0
numpy==1.26.4
pandas==2.2.2
scipy==1.13.0
ta==0.11.0
aiosqlite==0.20.0
APScheduler==3.10.4
python-telegram-bot==20.8
python-dotenv==1.0.1
colorlog==6.8.2
requests==2.31.0

### .env template (leave values empty):
KRAKEN_API_KEY=
KRAKEN_API_SECRET=
KRAKEN_CANCEL_KEY=
KRAKEN_CANCEL_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_AUTHORISED_USER_ID=
ENVIRONMENT=backtest

### config.py full contents:
# Autonomous Multi-Strategy Trading System
# Master configuration file

# Note: pandas-ta replaced with ta library

# Assets and capital allocation
ASSETS = {
    'BTC/USD': 0.25,
    'ETH/USD': 0.25,
    'SOL/USD': 0.20,
    'BNB/USD': 0.15,
    'XRP/USD': 0.15,
}

# Decision Engine
HURST_LOOKBACK         = 100
EDGE_SCORE_WEIGHTS     = {'hurst': 0.4, 'autocorr': 0.3, 'pec': 0.3}
REGIME_CHECK_INTERVAL  = 900
SENTIMENT_INTERVAL     = 3600
CHAOTIC_ATR_MULTIPLIER = 2.0

# Position Sizing
ATR_PERIOD             = 14
ATR_MULTIPLIER         = 1.5
BASE_RISK_PCT          = 0.01
RVR_DANGER_THRESHOLD   = 1.5
RVR_DEAD_THRESHOLD     = 0.8

# Risk Limits
MAX_ACCOUNT_DRAWDOWN   = 0.15
INTRADAY_DRAWDOWN      = 0.05
WEEKLY_LOSS_LIMIT      = 0.10
STRATEGY_DRAWDOWN      = 0.10
MR_CONSEC_LOSS_LIMIT   = 6
TF_CONSEC_LOSS_LIMIT   = 4
SCALPER_DAILY_LOSS     = 0.05

# Correlation Circuit Breaker
CORR_HALVE_THRESHOLD   = 0.8
CORR_PAUSE_THRESHOLD   = 0.7
CORR_CHECK_INTERVAL    = 14400

# Sentinel
SPREAD_MULTIPLIER      = 2.0
SLIPPAGE_TOLERANCE     = 0.003
LIQUIDITY_DEPTH_PCT    = 0.005
VOLUME_DRYUP_SECS      = 300

# Time Filters
SETTLEMENT_START           = '23:45'
SETTLEMENT_END             = '00:15'
SETTLEMENT_SIZE_REDUCTION  = 0.5

# Dead Mans Switch
HEARTBEAT_INTERVAL     = 60
HEARTBEAT_TIMEOUT      = 300

# Backtesting
BACKTEST_YEARS         = 5

## INSTALLATION TASK
After creating all files run this command:
pip install -r requirements.txt

Then verify installation:
python -c "
import ccxt
import krakenex
import aiohttp
import numpy
import pandas
import scipy
import aiosqlite
import telegram
import dotenv
import colorlog
import requests
import ta
print('All packages imported successfully')
print('Environment setup complete')
"

## SUCCESS CRITERIA
- All folders and files exist in correct locations
- requirements.txt installs without errors
- Verification script prints success message
- .env file exists with empty values
- config.py contains all constants

## APPROVAL GATE
Display this when complete:

TASK COMPLETE — AWAITING APPROVAL
Created: [list all files and folders created]
Packages: [confirm all installed]
Type APPROVED to proceed to Module 01 — Kraken Client
