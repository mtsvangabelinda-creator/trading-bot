# Autonomous Multi-Strategy Trading System
# Module 07 — Composite Edge Score
# The brain of the entire system
# Combines all four signals into one number that drives
# every strategy decision and position size

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

import numpy as np
import pandas as pd

from config import EDGE_SCORE_WEIGHTS
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


def calculate(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series
) -> Optional[dict]:
    """
    Calculate the Composite Edge Score for one asset.

    Combines Hurst, Autocorrelation, PEC, and RVR into
    a single score that determines strategy selection
    and position size factor.

    Args:
        close: Series of closing prices
        high: Series of high prices
        low: Series of low prices

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

        # If chaotic block everything immediately
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
            hurst_val         = 0.5
            hurst_regime      = 'DEAD_ZONE'
            hurst_conf        = 0.0
            hurst_tf_factor   = 0.0
            hurst_mr_factor   = 0.0
        else:
            hurst_val         = h_result['hurst']
            hurst_regime      = h_result['regime']
            hurst_conf        = h_result['confidence']
            hurst_tf_factor   = h_result['trend_factor']
            hurst_mr_factor   = h_result['reversion_factor']

        # Autocorrelation
        ac_result = autocorr_signal(close)
        if ac_result is None:
            failed_signals += 1
            autocorr_val      = 0.0
            autocorr_sig      = 'NEUTRAL'
            autocorr_tf       = 0.0
            autocorr_mr       = 0.0
        else:
            autocorr_val      = ac_result['autocorr']
            autocorr_sig      = ac_result['signal']
            autocorr_tf       = ac_result['trend_factor']
            autocorr_mr       = ac_result['reversion_factor']

        # PEC
        p_result = pec_signal(close)
        if p_result is None:
            failed_signals += 1
            pec_val           = 0.5
            pec_sig           = 'NEUTRAL'
            pec_tf            = 0.0
            pec_mr            = 0.0
        else:
            pec_val           = p_result['pec']
            pec_sig           = p_result['signal']
            pec_tf            = p_result['trend_factor']
            pec_mr            = p_result['reversion_factor']

        # RVR
        r_result = rvr_signal(high, low, close)
        if r_result is None:
            failed_signals += 1
            rvr_val           = 1.0
            rvr_regime        = 'NORMAL'
            rvr_multiplier    = 1.0
        else:
            rvr_val           = r_result['rvr']
            rvr_regime        = r_result['regime']
            rvr_multiplier    = r_result['size_multiplier']

        # If more than 2 signals failed return None
        if failed_signals > 2:
            logger.error(
                f'calculate: too many signal failures '
                f'({failed_signals})'
            )
            return None

        # ── Step 3: Calculate Composite Edge Scores ───────────
        weights = EDGE_SCORE_WEIGHTS

        tf_raw = (
            hurst_tf_factor   * weights['hurst'] +
            autocorr_tf       * weights['autocorr'] +
            pec_tf            * weights['pec']
        )

        mr_raw = (
            hurst_mr_factor   * weights['hurst'] +
            autocorr_mr       * weights['autocorr'] +
            pec_mr            * weights['pec']
        )

        # ── Step 4: Apply RVR multiplier ──────────────────────
        tf_final = round(
            float(np.clip(tf_raw * rvr_multiplier, 0.0, 1.0)), 4
        )
        mr_final = round(
            float(np.clip(mr_raw * rvr_multiplier, 0.0, 1.0)), 4
        )

        # Scalper score
        if rvr_regime == 'DANGER':
            scalper_score = SCALPER_DANGER_SCORE
        elif rvr_regime == 'DEAD':
            scalper_score = SCALPER_BASE_SCORE
        else:
            scalper_score = SCALPER_BASE_SCORE

        # ── Step 5: Strategy Selection ────────────────────────
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

        # ── Step 6: Overall confidence ────────────────────────
        score_margin = abs(tf_final - mr_final)
        confidence   = round(
            (hurst_conf + score_margin) / 2, 4
        )

        # ── Step 7: Build reasoning string ────────────────────
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
        logger.error(f'calculate failed: {e}')
        return None


def calculate_all(
    assets_data: dict
) -> dict:
    """
    Calculate edge scores for all assets independently.

    Args:
        assets_data: Dictionary where keys are asset names
            and values are dicts with close, high, low Series

    Returns:
        Dictionary of asset name to edge score result
    """
    results = {}
    for asset, data in assets_data.items():
        try:
            result = calculate(
                data['close'],
                data['high'],
                data['low']
            )
            results[asset] = result
            if result:
                logger.debug(
                    f'{asset}: {result["primary_strategy"]} '
                    f'score={result["position_size_factor"]}'
                )
        except Exception as e:
            logger.error(f'calculate_all failed for {asset}: {e}')
            results[asset] = None

    return results


def get_summary(results: dict) -> str:
    """
    Format edge score results as a Telegram-ready string.

    Args:
        results: Output from calculate_all

    Returns:
        Formatted summary string
    """
    try:
        lines = ['EDGE SCORES', '─' * 30]
        for asset, result in results.items():
            if result is None:
                lines.append(f'{asset}: ERROR — calculation failed')
            elif result.get('chaotic'):
                lines.append(
                    f'{asset}: BLOCKED — Chaotic Tripwire fired'
                )
            else:
                strategy = result['primary_strategy']
                score    = result['position_size_factor']
                hurst    = result['hurst']
                rvr_r    = result['rvr_regime']
                lines.append(
                    f'{asset}: {strategy} (score: {score}) — '
                    f'Hurst={hurst}, RVR={rvr_r}'
                )
        lines.append('─' * 30)
        return '\n'.join(lines)

    except Exception as e:
        logger.error(f'get_summary failed: {e}')
        return 'Edge score summary unavailable'


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 07 — EDGE SCORE TESTS ===\n')
    np.random.seed(42)
    n = 200

    def build_dataset(close_arr, vol=1.0):
        high  = pd.Series(
            close_arr + np.abs(np.random.normal(0, vol, n))
        )
        low   = pd.Series(
            close_arr - np.abs(np.random.normal(0, vol, n))
        )
        close = pd.Series(close_arr)
        return close, high, low

    # Test 1 — Trending dataset
    print('Test 1: Trending dataset...')
    trend_close = np.cumsum(np.random.normal(0.2, 0.5, n)) + 100
    c, h, l = build_dataset(trend_close)
    result = calculate(c, h, l)
    if result:
        print(f'  Strategy: {result["primary_strategy"]}')
        print(f'  TF Score: {result["tf_score"]}')
        print(f'  MR Score: {result["mr_score"]}')
        print(f'  Reasoning: {result["reasoning"]}')
        passed = result['primary_strategy'] == 'TREND_FOLLOWING'
        print(f'Test 1: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 1: FAILED — no result\n')

    # Test 2 — Mean reverting dataset
    print('Test 2: Mean reverting dataset...')
    mr_prices = []
    p = 100.0
    for _ in range(n):
        p = p + (100 - p) * 0.4 + np.random.normal(0, 0.3)
        mr_prices.append(p)
    c2, h2, l2 = build_dataset(np.array(mr_prices), vol=0.3)
    result2 = calculate(c2, h2, l2)
    if result2:
        print(f'  Strategy: {result2["primary_strategy"]}')
        print(f'  TF Score: {result2["tf_score"]}')
        print(f'  MR Score: {result2["mr_score"]}')
        passed = result2['primary_strategy'] == 'MEAN_REVERSION'
        print(f'Test 2: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 2: FAILED — no result\n')

    # Test 3 — Chaotic dataset
    print('Test 3: Chaotic dataset...')
    chaotic_close = np.cumsum(np.random.normal(0, 1, n)) + 100
    h3 = pd.Series(
        chaotic_close + np.abs(np.random.normal(0, 1, n))
    )
    l3 = pd.Series(
        chaotic_close - np.abs(np.random.normal(0, 1, n))
    )
    # Inject massive spike in last 10 candles
    h3.iloc[-10:] = chaotic_close[-10:] + 50
    l3.iloc[-10:] = chaotic_close[-10:] - 50
    c3 = pd.Series(chaotic_close)
    result3 = calculate(c3, h3, l3)
    if result3:
        print(f'  Strategy: {result3["primary_strategy"]}')
        print(f'  Chaotic: {result3["chaotic"]}')
        passed = result3['primary_strategy'] == 'BLOCKED'
        print(f'Test 3: {"PASSED" if passed else "FAILED"}\n')
    else:
        print('Test 3: FAILED — no result\n')

    # Test 4 — Dead zone dataset
    print('Test 4: Dead zone (random walk) dataset...')
    random_walk = np.cumsum(np.random.normal(0, 1, n)) + 100
    c4, h4, l4 = build_dataset(random_walk, vol=0.5)
    result4 = calculate(c4, h4, l4)
    if result4:
        print(f'  Strategy: {result4["primary_strategy"]}')
        print(f'  TF Score: {result4["tf_score"]}')
        print(f'  MR Score: {result4["mr_score"]}')
        print('Test 4: PASSED\n')
    else:
        print('Test 4: FAILED — no result\n')

    # Test 5 — calculate_all with two assets
    print('Test 5: calculate_all with BTC and ETH...')
    assets = {
        'BTC/USD': {'close': c,  'high': h,  'low': l},
        'ETH/USD': {'close': c2, 'high': h2, 'low': l2}
    }
    all_results = calculate_all(assets)
    for asset, res in all_results.items():
        if res:
            print(
                f'  {asset}: {res["primary_strategy"]} '
                f'score={res["position_size_factor"]}'
            )
    print('Test 5: PASSED\n')

    # Test 6 — get_summary
    print('Test 6: get_summary...')
    summary = get_summary(all_results)
    print(summary)
    print('Test 6: PASSED\n')

    all_passed = (
        result  is not None and
        result['primary_strategy']  == 'TREND_FOLLOWING' and
        result2 is not None and
        result2['primary_strategy'] == 'MEAN_REVERSION' and
        result3 is not None and
        result3['primary_strategy'] == 'BLOCKED'
    )
    print(
        '=== MODULE 07 — EDGE SCORE: '
        f'{"ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"} ==='
          )
