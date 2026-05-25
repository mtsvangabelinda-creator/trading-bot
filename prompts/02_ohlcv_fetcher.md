# Prompt 02 — OHLCV Fetcher

## CONTEXT
This is Module 2 of 22. Module 01 Kraken Client must be
complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE — AWAITING APPROVAL
Module: 02 — OHLCV Fetcher
File created: data/ohlcv_fetcher.py
Test results: [show actual output]
Type APPROVED to proceed to Module 03 — Hurst Exponent

Do not proceed until user types: APPROVED

## FILE TO CREATE
data/ohlcv_fetcher.py

## PURPOSE
Fetches and stores historical and live OHLCV candle data
for all 5 assets. Saves everything to SQLite database so
the system always has clean price data without repeated
API calls. Backtesting requires 5 years of historical data.

## DEPENDENCIES
- KrakenClient from execution/kraken_client.py
- aiosqlite
- pandas
- asyncio
- logging
- python-dotenv

## DATABASE
- Path: data/trading_data.db
- Create automatically if not exists

## CLASS NAME
OHLCVFetcher

## FUNCTIONS TO BUILD

### 1. init_database
- Creates table ohlcv if not exists
- Columns: id, asset, timestamp, open, high,
  low, close, volume, timeframe
- Unique constraint on asset, timestamp, timeframe
- Returns True if successful

### 2. fetch_historical
- Inputs: asset (str), timeframe (str) = '1h',
  days (int) = 1825 (5 years)
- Fetches data using KrakenClient.fetch_ohlcv
- Stores every candle using INSERT OR IGNORE
- Logs how many new candles saved
- Returns integer count of new candles saved

### 3. fetch_all_historical
- Inputs: timeframe (str) = '1h',
  days (int) = 1825 (5 years)
- Loops through all 5 assets sequentially
- Waits 1 second between each asset
- Logs progress for each asset
- Returns dictionary: asset name → candle count

### 4. update_live
- Inputs: asset (str), timeframe (str) = '1h'
- Fetches latest 10 candles
- Inserts any new candles not already in database
- Returns integer count of new candles added

### 5. load_ohlcv
- Inputs: asset (str), timeframe (str) = '1h',
  limit (int) = 500
- Returns pandas DataFrame:
  timestamp, open, high, low, close, volume
- Sorted oldest to newest
- This is what all other modules call for price data

### 6. get_stats
- No inputs
- Returns dictionary showing for each asset:
  total candles, earliest date, latest date

## ERROR HANDLING
- Every function wrapped in try/except
- Return None on failure
- Log all errors to logs/errors.log
- Never crash

## TEST
At bottom in if __name__ == '__main__': block:
1. Initialise database — print confirmed
2. Fetch 7 days BTC/USD only (days=7 for speed)
3. Print candle count saved
4. Load data back and print first 3 and last 3 rows
5. Print database statistics
6. Print MODULE 02 — OHLCV FETCHER: ALL TESTS PASSED

## SUCCESS CRITERIA
- Database created at data/trading_data.db
- 168 candles saved for 7 days hourly BTC/USD
- Data loads back correctly sorted oldest to newest
- Statistics show correct date range

## APPROVAL GATE
Display when complete:

TASK COMPLETE — AWAITING APPROVAL
Module: 02 — OHLCV Fetcher
File created: data/ohlcv_fetcher.py
Test results: [show actual output]
Type APPROVED to proceed to Module 03 — Hurst Exponent
