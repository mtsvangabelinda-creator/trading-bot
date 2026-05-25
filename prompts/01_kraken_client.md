# Prompt 01 — Kraken Client

## CONTEXT
This is Module 1 of 22 of the Autonomous Multi-Strategy Trading
System. The environment setup from Prompt 00 must be complete
and APPROVED before starting this module.

## YOUR ROLE
You are a senior Python engineer. Write clean production grade
code with full error handling, logging, type hints, and
docstrings on every function. Never skip steps. Never move
to the next task without explicit APPROVED from the user.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 01 — Kraken Client
Tests: [show test results]
Type APPROVED to proceed to Module 02 — OHLCV Fetcher

Do not proceed until user types: APPROVED

## FILE TO CREATE
execution/kraken_client.py

## PURPOSE
This module is the sole connection point between the trading
system and Kraken exchange. Every other module that needs
market data imports and uses this client. Nothing talks to
Kraken directly except this file. The system runs in manual
execution mode — it generates signals sent via Telegram and
the user places trades manually on Kraken.

## DEPENDENCIES
- ccxt==4.4.82
- krakenex==2.1.0
- aiohttp==3.9.5
- asyncio (built into Python)
- python-dotenv
- logging

## ENVIRONMENT VARIABLES (from .env file)
- KRAKEN_API_KEY
- KRAKEN_API_SECRET

## ASSETS
- BTC/USD
- ETH/USD
- SOL/USD
- BNB/USD
- XRP/USD

## CONSTANTS AT TOP OF FILE
RETRY_COUNT = 3
RETRY_DELAY = 2

## CLASS NAME
KrakenClient

## FUNCTIONS TO BUILD

### 1. __init__
- Load API keys from .env using python-dotenv
- Create authenticated ccxt Kraken instance
- Create unauthenticated ccxt Kraken instance
  for public data
- Set up rotating file logger:
  logs/errors.log
  Max 10MB per file, keep 7 files
  Format: timestamp | level | function | message
- Create logs/ directory if it does not exist

### 2. fetch_ohlcv
- Inputs: symbol (str), timeframe (str) = '1h',
  limit (int) = 500
- Output: pandas DataFrame with columns:
  timestamp, open, high, low, close, volume
  timestamp must be proper datetime not raw number
- Use unauthenticated instance
- Retry up to RETRY_COUNT times on failure
- Return None on failure after all retries

### 3. fetch_order_book
- Inputs: symbol (str), depth (int) = 20
- Output: dictionary with keys:
  bids: list of [price, quantity] pairs
  asks: list of [price, quantity] pairs
- Use unauthenticated instance
- Retry up to RETRY_COUNT times on failure
- Return None on failure

### 4. fetch_balance
- No inputs
- Output: dictionary of currencies with
  balance greater than zero only
- Use authenticated instance
- Retry up to RETRY_COUNT times on failure
- Return None on failure

### 5. fetch_open_orders
- Inputs: symbol (str) optional = None
  If None return all open orders
- Output: list of dictionaries each with:
  order_id, symbol, side, amount, price,
  timestamp
- Use authenticated instance
- Return empty list if no open orders
- Return None on failure

## ERROR HANDLING
- Every function wrapped in try/except
- Retry up to RETRY_COUNT times with
  RETRY_DELAY seconds between retries
- Log all errors to logs/errors.log
- Never crash the system
- Never log API keys or secrets anywhere

## LOGGING
- Create logs/ directory automatically
- Rotating file handler
- Log every successful data fetch at DEBUG level
- Log all errors at ERROR level
- Log format: timestamp | level | function | message

## NOTE ON MANUAL EXECUTION
This system does NOT place orders automatically.
The place_order and cancel_order functions are
NOT included. The system generates signals sent
via Telegram and the user places trades manually
on Kraken. Do not add any order placement code.

## TEST
At bottom of file in if __name__ == '__main__': block:

1. Initialise KrakenClient
2. Fetch BTC/USD OHLCV — print first 5 rows
   Expected: DataFrame with proper datetime timestamps
3. Fetch BTC/USD order book — print top 3 bids and asks
   Expected: dictionary with bids and asks lists
4. Fetch account balance — print result
   Expected: dictionary with currency balances
   Note: requires valid API keys in .env file
5. Print MODULE 01 — KRAKEN CLIENT: ALL TESTS PASSED
   if steps 2 and 3 pass (step 4 needs valid keys)

## SUCCESS CRITERIA
- KrakenClient class exists in execution/kraken_client.py
- fetch_ohlcv returns proper DataFrame with datetime index
- fetch_order_book returns bids and asks
- fetch_balance returns None gracefully if no keys set
- All functions have docstrings and type hints
- No hardcoded API keys anywhere

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 01 — Kraken Client
File created: execution/kraken_client.py
Test results: [show actual output]
Type APPROVED to proceed to Module 02 — OHLCV Fetcher
