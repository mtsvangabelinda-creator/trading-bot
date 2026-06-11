# Autonomous Multi-Strategy Trading System
# Module 07 — Composite Edge Score (Multi-Timeframe)
# The brain of the entire system
# Combines 1D bias, 4H structure, and 1H trigger confirmation
# into a single trade decision

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    EDGE_SCORE_WEIGHTS,
    BIAS_SMA_PERIOD,
    BIAS_NEUTRAL_BAND
)
from core.hurst import calculate_with_confidence as hurst_confidence
from core.autocorrelation import (
    calculate_with_signal as autocorr_signal
)
from core.pec import calculate_with_signal as pec_signal
from core.rvr import calculate_with_signal as rvr_signal
from core.rvr import chaotic_tripwire

# ── Logging ───────────────────────────────────────────────────
def setup_logger(name: str, log_file: str) -> logging.Logger:
    os.makedirs('logs', exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_file, maxBytes=10485760, backupCount=7
        )
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(funcName)s | %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

logger = setup_logger('edge_score', 'logs/errors.log')

# ── Constants ─────────────────────────────────────────────────
ACTIVATION_THRESHOLD = 0.3
SCALPER_BASE_SCORE   = 0.5
SCALPER_DANGER_SCORE = 0.25

MA_SHORT_PERIOD = 5
MA_LONG_PERIOD  = 20


# ════════════════════════════════════════════════════════════
# STAGE 1 — 1D BIAS
# ════════════════════════════════════════════════════════════
def calculate_bias_1d(df_1d: pd.DataFrame) -> str:
    """
    Determine market bias from 1D candles using price vs SMA.

    Args:
        df_1d: DataFrame with at least BIAS_SMA_PERIOD+1 rows
            and a 'close' column

    Returns:
        'BULLISH', 'BEARISH', or 'NEUTRAL'
    """
    try:
        if df_1d is None or len(df_1d) < BIAS_SMA_PERIOD:
            return 'NEUTRAL'

        close = df_1d['close']
        sma   = float(close.iloc[-BIAS_SMA_PERIOD:].mean())
        price = float(close.iloc[-1])

        upper_band = sma * (1 + BIAS_NEUTRAL_BAND)
        lower_band = sma * (1 - BIAS_NEUTRAL_BAND)

        if price > upper_band:
            return 'BULLISH'
        elif price < lower_band:
            return 'BEARISH'
        else:
            return 'NEUTRAL'

    except Exception as e:
        logger.error(f'calculate_bias_1d failed: {e}')
        return 'NEUTRAL'


# ════════════════════════════════════════════════════════════
# STAGE 2 — 4H STRUCTURE (Composite Edge Score)
# ════════════════════════════════════════════════════════════
def calculate_structure_4h(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series
) -> Optional[dict]:
    """
    Calculate the Composite Edge Score for 4H candles.

    Combines Hurst, Autocorrelation, PEC, and RVR into
    a single score that determines strategy selection
    and position size factor.

    Args:
        close: Series of 4H closing prices
        high: Series of 4H high prices
        low: Series of 4H low prices

    Returns:
        Dictionary with all signal values, edge scores,
        strategy decision, and reasoning or None on failure
    """
    try:
        # ── Step 1: Check Chaotic Tripwire first ──────────────
        tripwire = chaotic_tripwire(high, low, close)

        chaotic       = False
        chaotic_ratio = 0.0

        if tripwire is not None:
            chaotic       = tripwire['triggered']
            chaotic_ratio = tripwire['ratio']

        if chaotic:
            logger.warning(
                f'Chaotic Tripwire fired — ratio={chaotic_ratio}'
            )
            return {
                'hurst':                None,
                'hurst_regime':         'BLOCKED',
                'hurst_confidence':     0.0,
                'autocorr':             None,
                'autocorr_signal':      'BLOCKED',
                'pec':                  None,
                'pec_signal':           'BLOCKED',
                'rvr':                  None,
                'rvr_regime':           'DANGER',
                'chaotic':              True,
                'chaotic_ratio':        chaotic_ratio,
                'tf_score':             0.0,
                'mr_score':             0.0,
                'scalper_score':        0.0,
                'primary_strategy':     'BLOCKED',
                'position_size_factor': 0.0,
                'confidence':           0.0,
                'reasoning': (
                    f'CHAOTIC TRIPWIRE FIRED — ATR ratio={chaotic_ratio}. '
                    f'All new entries blocked until volatility normalises.'
                )
            }

        # ── Step 2: Calculate all four signals ────────────────
        failed_signals = 0

        # Hurst
        h_result = hurst_confidence(close)
        if h_result is None:
            failed_signals += 1
            hurst_val       = 0.5
            hurst_regime    = 'DEAD_ZONE'
            hurst_conf      = 0.0
            hurst_tf_factor = 0.0
            hurst_mr_factor = 0.0
        else:
            hurst_val       = h_result['hurst']
            hurst_regime    = h_result['regime']
            hurst_conf      = h_result['confidence']
            hurst_tf_factor = h_result['trend_factor']
            hurst_mr_factor = h_result['reversion_factor']

        # Autocorrelation
        ac_result = autocorr_signal(close)
        if ac_result is None:
            failed_signals += 1
            autocorr_val  = 0.0
            autocorr_sig  = 'NEUTRAL'
            autocorr_tf   = 0.0
            autocorr_mr   = 0.0
        else:
            autocorr_val  = ac_result['autocorr']
            autocorr_sig  = ac_result['signal']
            autocorr_tf   = ac_result['trend_factor']
            autocorr_mr   = ac_result['reversion_factor']

        # PEC
        p_result = pec_signal(close)
        if p_result is None:
            failed_signals += 1
            pec_val = 0.5
            pec_sig = 'NEUTRAL'
            pec_tf  = 0.0
            pec_mr  = 0.0
        else:
            pec_val = p_result['pec']
            pec_sig = p_result['signal']
            pec_tf  = p_result['trend_factor']
            pec_mr  = p_result['reversion_factor']

        # RVR
        r_result = rvr_signal(high, low, close)
        if r_result is None:
            failed_signals += 1
            rvr_val        = 1.0
            rvr_regime     = 'NORMAL'
            rvr_multiplier = 1.0
        else:
            rvr_val        = r_result['rvr']
            rvr_regime     = r_result['regime']
            rvr_multiplier = r_result['size_multiplier']

        if failed_signals > 2:
            logger.error(
                f'calculate_structure_4h: too many signal failures '
                f'({failed_signals})'
            )
            return None

        # ── Step 3: Calculate Composite Edge Scores ───────────
        weights = EDGE_SCORE_WEIGHTS

        rvr_tf_factor = float(
            np.clip((rvr_val - 1.0) / 2.0, 0.0, 1.0)
        )
        rvr_mr_factor = float(
            np.clip((2.0 - rvr_val) / 2.0, 0.0, 1.0)
        )

        tf_raw = (
            hurst_tf_factor * weights['hurst'] +
            autocorr_tf     * weights['autocorr'] +
            pec_tf          * weights['pec'] +
            rvr_tf_factor   * weights.get('rvr', 0.15)
        )

        mr_raw = (
            hurst_mr_factor * weights['hurst'] +
            autocorr_mr     * weights['autocorr'] +
            pec_mr          * weights['pec'] +
            rvr_mr_factor   * weights.get('rvr', 0.15)
        )

        # ── Step 4: Apply RVR multiplier ──────────────────────
        tf_final = round(
            float(np.clip(tf_raw * rvr_multiplier, 0.0, 1.0)), 4
        )
        mr_final = round(
            float(np.clip(mr_raw * rvr_multiplier, 0.0, 1.0)), 4
        )

        # ── Step 5: Scalper score — dynamic ───────────────────
        best_signal = max(tf_final, mr_final)
        if rvr_regime == 'DANGER':
            scalper_score = SCALPER_DANGER_SCORE
        elif rvr_regime == 'DEAD':
            scalper_score = 0.0
        else:
            scalper_score = round(
                float(np.clip(
                    SCALPER_BASE_SCORE * (1.0 - best_signal),
                    0.3, 0.5
                )), 4
            )

        # ── Step 6: Strategy Selection ────────────────────────
        if (
            tf_final > mr_final and
            tf_final > ACTIVATION_THRESHOLD
        ):
            primary_strategy     = 'TREND_FOLLOWING'
            position_size_factor = tf_final
        elif (
            mr_final > tf_final and
            mr_final > ACTIVATION_THRESHOLD
        ):
            primary_strategy     = 'MEAN_REVERSION'
            position_size_factor = mr_final
        else:
            primary_strategy     = 'SCALPER'
            position_size_factor = scalper_score

        # ── Step 7: Overall confidence ────────────────────────
        score_margin = abs(tf_final - mr_final)
        confidence   = round(
            (hurst_conf + score_margin) / 2, 4
        )

        # ── Step 8: Build reasoning string ────────────────────
        reasoning = (
            f'Hurst={hurst_val} ({hurst_regime}), '
            f'Autocorr={autocorr_val} ({autocorr_sig}), '
            f'PEC={pec_val} ({pec_sig}), '
            f'RVR={rvr_val} ({rvr_regime}). '
            f'TF_score={tf_final}, MR_score={mr_final}. '
            f'{primary_strategy} selected at '
            f'{round(position_size_factor * 100)}% position size.'
        )

        return {
            'hurst':                hurst_val,
            'hurst_regime':         hurst_regime,
            'hurst_confidence':     hurst_conf,
            'autocorr':             autocorr_val,
            'autocorr_signal':      autocorr_sig,
            'pec':                  pec_val,
            'pec_signal':           pec_sig,
            'rvr':                  rvr_val,
            'rvr_regime':           rvr_regime,
            'chaotic':              False,
            'chaotic_ratio':        chaotic_ratio,
            'tf_score':             tf_final,
            'mr_score':             mr_final,
            'scalper_score':        scalper_score,
            'primary_strategy':     primary_strategy,
            'position_size_factor': position_size_factor,
            'confidence':           confidence,
            'reasoning':            reasoning
        }

    except Exception as e:
        logger.error(f'calculate_structure_4h failed: {e}')
        return None


# ════════════════════════════════════════════════════════════
# STAGE 3 — 1H TRIGGER CONFIRMATION
# ════════════════════════════════════════════════════════════
def check_trigger_1h(
    df_1h: pd.DataFrame,
    primary_strategy: str,
    direction: str
) -> bool:
    """
    Confirm whether the 1H timeframe supports entry in the
    given direction for the given strategy.

    TREND_FOLLOWING: 1H short MA vs long MA must agree
        with the trend direction.
    MEAN_REVERSION: last 1H candle must show a rejection
        (close back toward the open after touching an
        extreme in the direction of the reversal).
    SCALPER: 1H short-term momentum must agree with
        direction (short MA vs long MA, looser check).

    Args:
        df_1h: DataFrame with 'close', 'high', 'low', 'open'
            columns, at least MA_LONG_PERIOD+1 rows
        primary_strategy: 'TREND_FOLLOWING', 'MEAN_REVERSION',
            or 'SCALPER'
        direction: 'long' or 'short'

    Returns:
        True if the 1H timeframe confirms entry
    """
    try:
        if df_1h is None or len(df_1h) < MA_LONG_PERIOD + 1:
            return False

        close = df_1h['close']

        if primary_strategy == 'TREND_FOLLOWING':
            short_ma = float(close.iloc[-MA_SHORT_PERIOD:].mean())
            long_ma  = float(close.iloc[-MA_LONG_PERIOD:].mean())

            if direction == 'long':
                return short_ma > long_ma
            else:
                return short_ma < long_ma

        elif primary_strategy == 'MEAN_REVERSION':
            last = df_1h.iloc[-1]
            open_p  = float(last['open'])
            close_p = float(last['close'])
            high_p  = float(last['high'])
            low_p   = float(last['low'])

            if direction == 'long':
                # Rejection of the low — wicked down but
                # closed back up toward/above open
                wicked_low = (open_p - low_p) > (high_p - open_p)
                closed_up  = close_p >= open_p
                return wicked_low and closed_up
            else:
                # Rejection of the high — wicked up but
                # closed back down toward/below open
                wicked_high = (high_p - open_p) > (open_p - low_p)
                closed_down = close_p <= open_p
                return wicked_high and closed_down

        else:  # SCALPER
            short_ma = float(close.iloc[-MA_SHORT_PERIOD:].mean())
            long_ma  = float(close.iloc[-MA_LONG_PERIOD:].mean())

            if direction == 'long':
                return short_ma >= long_ma
            else:
                return short_ma <= long_ma

    except Exception as e:
        logger.error(f'check_trigger_1h failed: {e}')
        return False


# ════════════════════════════════════════════════════════════
# DIRECTION DETERMINATION
# ════════════════════════════════════════════════════════════
def determine_direction(
    structure: dict,
    bias: str,
    df_4h: pd.DataFrame
) -> Optional[str]:
    """
    Determine trade direction from 4H structure, then
    filter against 1D bias.

    Args:
        structure: Output from calculate_structure_4h
        bias: 'BULLISH', 'BEARISH', or 'NEUTRAL'
        df_4h: 4H DataFrame for direction calculation

    Returns:
        'long', 'short', or None if no valid direction
    """
    try:
        strategy = structure['primary_strategy']
        close    = df_4h['close']
        current_price = float(close.iloc[-1])

        if strategy == 'TREND_FOLLOWING':
            short_ma = float(close.iloc[-MA_SHORT_PERIOD:].mean())
            long_ma  = float(close.iloc[-MA_LONG_PERIOD:].mean())
            if short_ma > long_ma:
                direction = 'long'
            elif short_ma < long_ma:
                direction = 'short'
            else:
                return None

        elif strategy == 'MEAN_REVERSION':
            sma = float(close.iloc[-MA_LONG_PERIOD:].mean())
            if current_price < sma * 0.99:
                direction = 'long'
            elif current_price > sma * 1.01:
                direction = 'short'
            else:
                return None

        else:  # SCALPER — direction follows 1D bias directly
            if bias == 'BULLISH':
                direction = 'long'
            elif bias == 'BEARISH':
                direction = 'short'
            else:
                return None

        # ── Bias filter ────────────────────────────────────
        if bias == 'BULLISH' and direction == 'short':
            return None
        if bias == 'BEARISH' and direction == 'long':
            return None

        return direction

    except Exception as e:
        logger.error(f'determine_direction failed: {e}')
        return None


# ════════════════════════════════════════════════════════════
# MAIN ENTRY POINT — MULTI-TIMEFRAME EDGE SCORE
# ════════════════════════════════════════════════════════════
def calculate(
    df_1d: pd.DataFrame,
    df_4h: pd.DataFrame,
    df_1h: pd.DataFrame
) -> Optional[dict]:
    """
    Calculate the full multi-timeframe edge score.

    Pipeline:
        1. 1D bias (BULLISH/BEARISH/NEUTRAL)
        2. 4H structure (Composite Edge Score)
        3. Direction (from 4H structure, filtered by bias)
        4. 1H trigger confirmation

    A trade signal is only valid when direction is not None
    AND trigger_confirmed is True.

    Args:
        df_1d: 1D OHLCV DataFrame (>= BIAS_SMA_PERIOD rows)
        df_4h: 4H OHLCV DataFrame (>= 200 rows recommended)
        df_1h: 1H OHLCV DataFrame (>= MA_LONG_PERIOD+1 rows)

    Returns:
        Dictionary with bias, structure details, direction,
        trigger confirmation, and position sizing info,
        or None on failure
    """
    try:
        # ── Stage 1: 1D Bias ───────────────────────────────
        bias = calculate_bias_1d(df_1d)

        # ── Stage 2: 4H Structure ──────────────────────────
        structure = calculate_structure_4h(
            df_4h['close'], df_4h['high'], df_4h['low']
        )

        if structure is None:
            return None

        if structure['primary_strategy'] == 'BLOCKED':
            return {
                **structure,
                'bias':              bias,
                'direction':         None,
                'trigger_confirmed': False
            }

        # ── Stage 3: Direction (4H structure + 1D bias) ────
        direction = determine_direction(structure, bias, df_4h)

        if direction is None:
            return {
                **structure,
                'bias':              bias,
                'direction':         None,
                'trigger_confirmed': False
            }

        # ── Stage 4: 1H Trigger Confirmation ───────────────
        trigger_confirmed = check_trigger_1h(
            df_1h, structure['primary_strategy'], direction
        )

        result = {
            **structure,
            'bias':              bias,
            'direction':         direction,
            'trigger_confirmed': trigger_confirmed
        }

        result['reasoning'] += (
            f' | Bias={bias}, Direction={direction}, '
            f'1H Trigger={"CONFIRMED" if trigger_confirmed else "NOT CONFIRMED"}.'
        )

        return result

    except Exception as e:
        logger.error(f'calculate failed: {e}')
        return None


def calculate_all(
    assets_data: dict
) -> dict:
    """
    Calculate multi-timeframe edge scores for all assets.

    Args:
        assets_data: Dict where keys are asset names and
            values are dicts with 'df_1d', 'df_4h', 'df_1h'
            DataFrames

    Returns:
        Dictionary of asset name to edge score result
    """
    results = {}
    for asset, data in assets_data.items():
        try:
            result = calculate(
                data['df_1d'],
                data['df_4h'],
                data['df_1h']
            )
            results[asset] = result
            if result:
                logger.debug(
                    f'{asset}: {result["primary_strategy"]} '
                    f'direction={result.get("direction")} '
                    f'trigger={result.get("trigger_confirmed")}'
                )
        except Exception as e:
            logger.error(
                f'calculate_all failed for {asset}: {e}'
            )
            results[asset] = None

    return results


def get_summary(results: dict) -> str:
    """
    Format multi-timeframe edge score results as a
    Telegram-ready string.

    Args:
        results: Output from calculate_all

    Returns:
        Formatted summary string
    """
    try:
        lines = ['EDGE SCORES (Multi-Timeframe)', '─' * 30]
        for asset, result in results.items():
            if result is None:
                lines.append(
                    f'{asset}: ERROR — calculation failed'
                )
            elif result.get('chaotic'):
                lines.append(
                    f'{asset}: BLOCKED — Chaotic Tripwire fired'
                )
            elif result.get('direction') is None:
                lines.append(
                    f'{asset}: NO SIGNAL — '
                    f'Bias={result.get("bias")}, '
                    f'Strategy={result["primary_strategy"]}'
                )
            else:
                strategy  = result['primary_strategy']
                score     = result['position_size_factor']
                direction = result['direction']
                trigger   = result['trigger_confirmed']
                lines.append(
                    f'{asset}: {strategy} {direction.upper()} '
                    f'(score: {score}) — '
                    f'Bias={result["bias"]}, '
                    f'Trigger={"YES" if trigger else "NO"}'
                )
        lines.append('─' * 30)
        return '\n'.join(lines)

    except Exception as e:
        logger.error(f'get_summary failed: {e}')
        return 'Edge score summary unavailable'


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 07 — MULTI-TIMEFRAME EDGE SCORE TESTS ===\n')
    np.random.seed(42)

    def build_4h_dataset(close_arr, vol=1.0):
        n = len(close_arr)
        high  = pd.Series(
            close_arr + np.abs(np.random.normal(0, vol, n))
        )
        low   = pd.Series(
            close_arr - np.abs(np.random.normal(0, vol, n))
        )
        close = pd.Series(close_arr)
        open_ = pd.Series(close_arr) - np.random.normal(0, vol * 0.3, n)
        return pd.DataFrame({
            'open': open_, 'high': high, 'low': low, 'close': close
        })

    # ── Test 1: Trending 4H, Bullish 1D bias ──────────────
    print('Test 1: Trending up dataset with bullish bias...')
    n_4h = 200
    trend_close = np.cumsum(np.random.normal(0.3, 0.5, n_4h)) + 100
    df_4h = build_4h_dataset(trend_close)

    # 1D — uptrend, price above SMA
    n_1d = 60
    d1_close = np.linspace(90, 105, n_1d)
    df_1d = pd.DataFrame({'close': d1_close})

    # 1H — short MA above long MA (confirms trend)
    n_1h = 30
    h1_close = np.linspace(103, 105, n_1h)
    df_1h = pd.DataFrame({
        'open':  h1_close - 0.05,
        'high':  h1_close + 0.1,
        'low':   h1_close - 0.1,
        'close': h1_close
    })

    result = calculate(df_1d, df_4h, df_1h)
    if result:
        print(f'  Bias:      {result["bias"]}')
        print(f'  Strategy:  {result["primary_strategy"]}')
        print(f'  Direction: {result["direction"]}')
        print(f'  Trigger:   {result["trigger_confirmed"]}')
        print('Test 1: PASSED\n')
    else:
        print('Test 1: FAILED — no result\n')

    # ── Test 2: Chaotic 4H ─────────────────────────────────
    print('Test 2: Chaotic 4H dataset...')
    chaotic_close = np.cumsum(np.random.normal(0, 1, n_4h)) + 100
    df_4h_chaotic = build_4h_dataset(chaotic_close)
    df_4h_chaotic.loc[df_4h_chaotic.index[-10:], 'high'] = (
        chaotic_close[-10:] + 50
    )
    df_4h_chaotic.loc[df_4h_chaotic.index[-10:], 'low'] = (
        chaotic_close[-10:] - 50
    )

    result2 = calculate(df_1d, df_4h_chaotic, df_1h)
    if result2:
        print(f'  Strategy: {result2["primary_strategy"]}')
        print(f'  Chaotic:  {result2["chaotic"]}')
        passed = result2['primary_strategy'] == 'BLOCKED'
        print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 2: FAILED — no result\n')

    # ── Test 3: Bias conflicts with structure direction ───
    print('Test 3: Bearish bias with bullish 4H structure...')
    d1_close_bear = np.linspace(105, 90, n_1d)
    df_1d_bear = pd.DataFrame({'close': d1_close_bear})

    result3 = calculate(df_1d_bear, df_4h, df_1h)
    if result3:
        print(f'  Bias:      {result3["bias"]}')
        print(f'  Strategy:  {result3["primary_strategy"]}')
        print(f'  Direction: {result3["direction"]}')
        passed = result3['direction'] is None
        print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 3: FAILED — no result\n')

    # ── Test 4: get_summary ────────────────────────────────
    print('Test 4: get_summary with multiple assets...')
    all_results = {
        'BTC/USD': result,
        'ETH/USD': result2,
        'SOL/USD': result3
    }
    summary = get_summary(all_results)
    print(summary)
    print('Test 4: PASSED\n')

    print('=== MODULE 07 — MULTI-TIMEFRAME EDGE SCORE TESTS COMPLETE ===')
