# Prompt 13 – Time Filters

## CONTEXT
Module 12 Correlation Breaker must be complete and APPROVED before starting this module.

## APPROVAL GATE RULE
After completing this module stop and display:

TASK COMPLETE – AWAITING APPROVAL
Module: 13 – Time Filters
File created: risk/time_filters.py
Test results: [show actual output]
Type APPROVED to proceed to Module 14 – Sentinel (Order Book Monitor)

Do not proceed until user types: APPROVED.

## FILE TO CREATE
risk/time_filters.py

## PURPOSE
Applies time-based trading restrictions: daily settlement window, weekend mode, and news blackout periods. Prevents trading during high-risk or low-liquidity times per spec.

## RULES FROM SPEC
- Daily settlement window 23:45 – 00:15 UTC: max position size reduced by 50%
- Weekend mode (Saturday and Sunday UTC): scalper loss limit halved, Sentinel sensitivity set to "paranoid" (not implemented here, just flag for Sentinel)
- News blackout: 15 minutes before and after high-impact events (FOMC, CPI, etc.) – all new entries frozen

## DEPENDENCIES
- datetime, pytz, logging, json (for news calendar)
- config.py: SETTLEMENT_START='23:45', SETTLEMENT_END='00:15', SETTLEMENT_SIZE_REDUCTION=0.5
- Optional: news_calendar.json (list of event datetimes – user provided)
- data/trading_data.db (optional, for logging)

## FUNCTIONS

1. is_settlement_window(now_utc=None)
   Returns bool – True if current UTC time is between 23:45 and 00:15 (crosses midnight). If now_utc is None, use datetime.now(pytz.UTC).

2. get_settlement_multiplier()
   Returns float: SETTLEMENT_SIZE_REDUCTION (0.5) if settlement window, else 1.0.

3. is_weekend(now_utc=None)
   Returns bool – True if Saturday or Sunday UTC.

4. get_weekend_mode_flag()
   Returns dict: {'active': bool, 'scalper_loss_halved': bool, 'sentinel_paranoid': bool}
   If weekend: scalper_loss_halved = True, sentinel_paranoid = True. Else both False.

5. is_news_blackout(event_calendar_path='config/news_calendar.json', now_utc=None, buffer_minutes=15)
   Loads news_calendar.json (list of ISO format datetimes). Returns True if now_utc is within buffer_minutes before or after any event. Assumes calendar is pre-loaded; if file missing, returns False and logs warning.

6. is_trading_allowed(news_calendar_path='config/news_calendar.json')
   Returns bool – False if is_news_blackout() true. Settlement window and weekend do NOT block trading – they only affect sizing/parameters. Only news blackout blocks entries.

7. get_size_multiplier()
   Combines settlement multiplier (0.5 or 1.0) – other filters (weekend) affect other modules via flags. Returns float.

8. get_parameter_overrides()
   Returns dict: {'scalper_loss_limit_halved': bool, 'sentinel_mode': 'normal' or 'paranoid'}
   Used by strategy_silo (scalper loss limit) and sentinel module.

## ERROR HANDLING
- Try/except each function
- Log to logs/risk.log
- Missing news calendar: log warning, assume no blackout

## TESTS (in if __name__ == '__main__':)
Create a temporary news_calendar.json for testing with one event: current UTC time + 30 minutes.

1. Test settlement window – mock datetime to 23:50 UTC – is_settlement_window should be True, get_settlement_multiplier returns 0.5. PASS/FAIL.
2. Test non-settlement – 12:00 UTC – multiplier 1.0. PASS/FAIL.
3. Test weekend – mock datetime to Saturday 12:00 UTC – get_weekend_mode_flag returns scalper_loss_halved=True, sentinel_paranoid=True. PASS/FAIL.
4. Test weekday – flag returns both False. PASS/FAIL.
5. Test news blackout – mock datetime to 10 minutes before event – is_news_blackout returns True. PASS/FAIL.
6. Test outside blackout – mock to 20 minutes after event – returns False. PASS/FAIL.
7. Test is_trading_allowed during news blackout – returns False. PASS/FAIL.
8. Test get_size_multiplier during settlement – returns 0.5. PASS/FAIL.
9. Print "MODULE 13 – TIME FILTERS: ALL TESTS PASSED"

## SUCCESS CRITERIA
- Settlement window detection correct across midnight
- Weekend detection correct UTC
- News blackout correctly reads calendar and checks buffer
- All tests pass

## APPROVAL GATE
Display when complete:

TASK COMPLETE – AWAITING APPROVAL
Module: 13 – Time Filters
File created: risk/time_filters.py
Settlement window test: PASS or FAIL
Weekend flag test: PASS or FAIL
News blackout test: PASS or FAIL
Trading blocked test: PASS or FAIL
Type APPROVED to proceed to Module 14 – Sentinel (Order Book Monitor)
