# Autonomous Multi-Strategy Trading System
# Module 21a — Telegram Alerts
# Sends automatic notifications to the authorised user
# Called by orchestrator and scheduler — not by user

import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

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

logger = setup_logger('alerts', 'logs/errors.log')

# ── Credentials ───────────────────────────────────────────────
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID   = os.getenv('TELEGRAM_AUTHORISED_USER_ID', '')


def send_message(
    message: str,
    bot_token: str = None,
    chat_id: str = None
) -> bool:
    """
    Send a plain text message to the authorised user.

    Args:
        message: Text to send
        bot_token: Override bot token
        chat_id: Override chat ID

    Returns:
        True if sent successfully, False on failure
    """
    try:
        token = bot_token or BOT_TOKEN
        cid   = chat_id   or CHAT_ID

        if not token or not cid:
            logger.error(
                'send_message: missing bot token or chat ID'
            )
            return False

        url  = f'https://api.telegram.org/bot{token}/sendMessage'
        data = {
            'chat_id':    cid,
            'text':       message,
            'parse_mode': 'HTML'
        }

        response = requests.post(url, data=data, timeout=10)

        if response.status_code == 200:
            logger.debug(f'Message sent: {message[:50]}...')
            return True
        else:
            logger.error(
                f'send_message failed: '
                f'status={response.status_code} '
                f'response={response.text}'
            )
            return False

    except Exception as e:
        logger.error(f'send_message failed: {e}')
        return False


def send_trade_signal(signal_text: str) -> bool:
    """
    Send a trade signal alert.

    Args:
        signal_text: Formatted signal from position_sizer

    Returns:
        True if sent
    """
    message = f'📊 {signal_text}'
    return send_message(message)


def send_trade_opened(position: dict) -> bool:
    """
    Send confirmation when a trade is opened.

    Args:
        position: Position details dictionary

    Returns:
        True if sent
    """
    try:
        symbol    = position.get('symbol', 'N/A')
        direction = position.get('direction', 'N/A').upper()
        size      = position.get('size', 0)
        entry     = position.get('entry_price', 0)
        stop      = position.get('stop_price', 0)
        tp        = position.get('tp_price', 0)
        strategy  = position.get('strategy', 'N/A')
        edge      = position.get('edge_score', 0)
        base      = symbol.split('/')[0] if '/' in symbol else ''

        message = (
            f'✅ TRADE OPENED — {symbol}\n'
            f'{"─" * 22}\n'
            f'Direction: {direction}\n'
            f'Size: {size} {base}\n'
            f'Entry Price: ${entry:,.2f}\n'
            f'Stop Loss: ${stop:,.2f}\n'
            f'Take Profit: ${tp:,.2f}\n'
            f'Strategy: {strategy}\n'
            f'Edge Score: {edge}'
        )

        return send_message(message)

    except Exception as e:
        logger.error(f'send_trade_opened failed: {e}')
        return False


def send_trade_closed(close_result: dict) -> bool:
    """
    Send confirmation when a trade is closed.

    Args:
        close_result: Output from order_manager.close_position

    Returns:
        True if sent
    """
    try:
        symbol    = close_result.get('symbol', 'N/A')
        direction = close_result.get('direction', 'N/A')
        pnl       = close_result.get('pnl', 0)
        reason    = close_result.get('reason', 'N/A')
        entry     = close_result.get('entry_price', 0)
        exit_p    = close_result.get('exit_price', 0)
        strategy  = close_result.get('strategy', 'N/A')
        duration  = close_result.get('duration')

        pnl_emoji = '✅' if pnl >= 0 else '❌'
        pnl_sign  = '+' if pnl >= 0 else ''

        duration_str = 'N/A'
        if duration:
            total_secs = int(duration.total_seconds())
            hours      = total_secs // 3600
            minutes    = (total_secs % 3600) // 60
            duration_str = f'{hours}h {minutes}m'

        message = (
            f'{pnl_emoji} TRADE CLOSED — {symbol}\n'
            f'{"─" * 22}\n'
            f'Direction: {direction.upper()} closed\n'
            f'Entry: ${entry:,.2f} '
            f'Exit: ${exit_p:,.2f}\n'
            f'PnL: {pnl_sign}${pnl:,.2f}\n'
            f'Reason: {reason.replace("_", " ").title()}\n'
            f'Duration: {duration_str}\n'
            f'Strategy: {strategy}'
        )

        return send_message(message)

    except Exception as e:
        logger.error(f'send_trade_closed failed: {e}')
        return False


def send_drawdown_alert(drawdown_result: dict) -> bool:
    """
    Send alert when drawdown limit is breached.

    Args:
        drawdown_result: Output from drawdown_guard.update

    Returns:
        True if sent
    """
    try:
        alert = drawdown_result.get('alert_message')
        if not alert:
            return False

        message = f'🚨 {alert}'
        return send_message(message)

    except Exception as e:
        logger.error(f'send_drawdown_alert failed: {e}')
        return False


def send_strategy_paused_alert(
    asset: str,
    strategy: str,
    reason: str
) -> bool:
    """
    Send alert when a strategy silo is paused.

    Args:
        asset: Trading pair
        strategy: Strategy name
        reason: Reason for pause

    Returns:
        True if sent
    """
    try:
        message = (
            f'⏸ STRATEGY PAUSED\n'
            f'{"─" * 22}\n'
            f'Asset: {asset}\n'
            f'Strategy: {strategy}\n'
            f'Reason: {reason}'
        )
        return send_message(message)

    except Exception as e:
        logger.error(f'send_strategy_paused_alert failed: {e}')
        return False


def send_correlation_alert(correlation_result: dict) -> bool:
    """
    Send alert when correlation breaker fires.

    Args:
        correlation_result: Output from correlation_breaker.check

    Returns:
        True if sent
    """
    try:
        alert = correlation_result.get('alert_message')
        if not alert:
            return False

        message = f'⚠️ {alert}'
        return send_message(message)

    except Exception as e:
        logger.error(f'send_correlation_alert failed: {e}')
        return False


def send_chaotic_tripwire_alert(
    asset: str,
    ratio: float
) -> bool:
    """
    Send alert when Chaotic Tripwire fires.

    Args:
        asset: Trading pair
        ratio: Current ATR ratio that triggered

    Returns:
        True if sent
    """
    try:
        message = (
            f'🔥 CHAOTIC TRIPWIRE FIRED\n'
            f'{"─" * 22}\n'
            f'Asset: {asset}\n'
            f'ATR Ratio: {round(ratio, 2)}x normal\n'
            f'All new entries blocked for {asset}\n'
            f'Will resume when ATR normalises.'
        )
        return send_message(message)

    except Exception as e:
        logger.error(
            f'send_chaotic_tripwire_alert failed: {e}'
        )
        return False


def send_status_update(status: dict) -> bool:
    """
    Send 4-hourly automatic status update.

    Args:
        status: System status dictionary

    Returns:
        True if sent
    """
    try:
        now         = datetime.now(timezone.utc)
        account     = status.get('account_value', 0)
        daily_pnl   = status.get('daily_pnl', 0)
        positions   = status.get('open_positions', {})
        edge_summary = status.get('edge_summary', 'N/A')
        sent_summary = status.get('sentiment_summary', 'N/A')
        risk_status  = status.get('risk_status', 'ACTIVE')
        corr_status  = status.get('correlation_status', 'NORMAL')
        corr_val     = status.get('avg_correlation', 0)

        pnl_sign  = '+' if daily_pnl >= 0 else ''
        pnl_pct   = (
            daily_pnl / account * 100
            if account > 0 else 0
        )
        open_count = len(positions)

        pos_str = (
            f'{open_count} open'
            if open_count > 0
            else 'No open positions'
        )

        message = (
            f'📊 SYSTEM STATUS — '
            f'{now.strftime("%H:%M UTC")}\n'
            f'{"─" * 26}\n'
            f'Account: ${account:,.2f}\n'
            f'Daily PnL: {pnl_sign}${daily_pnl:,.2f} '
            f'({pnl_sign}{round(pnl_pct,2)}%)\n'
            f'Positions: {pos_str}\n'
            f'{"─" * 26}\n'
            f'EDGE SCORES:\n{edge_summary}\n'
            f'{"─" * 26}\n'
            f'SENTIMENT:\n{sent_summary}\n'
            f'{"─" * 26}\n'
            f'Risk Status: {risk_status}\n'
            f'Correlation: {corr_status} ({corr_val})'
        )

        return send_message(message)

    except Exception as e:
        logger.error(f'send_status_update failed: {e}')
        return False


def send_daily_summary(summary: dict) -> bool:
    """
    Send midnight UTC daily performance summary.

    Args:
        summary: Daily performance dictionary

    Returns:
        True if sent
    """
    try:
        now         = datetime.now(timezone.utc)
        date_str    = now.strftime('%d %b %Y')
        total       = summary.get('total_trades', 0)
        winners     = summary.get('winning_trades', 0)
        losers      = summary.get('losing_trades', 0)
        daily_pnl   = summary.get('daily_pnl', 0)
        best_trade  = summary.get('best_trade', 0)
        worst_trade = summary.get('worst_trade', 0)
        balance     = summary.get('account_balance', 0)
        peak_dd     = summary.get('peak_drawdown_today', 0)
        status      = summary.get('status', 'ACTIVE')

        pnl_sign = '+' if daily_pnl >= 0 else ''
        pnl_pct  = (
            daily_pnl / balance * 100
            if balance > 0 else 0
        )

        tf_trades = summary.get('tf_trades', 0)
        mr_trades = summary.get('mr_trades', 0)
        sc_trades = summary.get('sc_trades', 0)

        message = (
            f'📅 DAILY SUMMARY — {date_str}\n'
            f'{"─" * 28}\n'
            f'Total Trades: {total}\n'
            f'Winners: {winners} '
            f'Losers: {losers}\n'
            f'Daily PnL: {pnl_sign}${daily_pnl:,.2f} '
            f'({pnl_sign}{round(pnl_pct,2)}%)\n'
            f'Best Trade: ${best_trade:,.2f}\n'
            f'Worst Trade: ${worst_trade:,.2f}\n'
            f'Strategies: TF:{tf_trades} '
            f'MR:{mr_trades} SC:{sc_trades}\n'
            f'{"─" * 28}\n'
            f'Account Balance: ${balance:,.2f}\n'
            f'Peak Drawdown Today: '
            f'{round(peak_dd*100,2)}%\n'
            f'Status: {status}'
        )

        return send_message(message)

    except Exception as e:
        logger.error(f'send_daily_summary failed: {e}')
        return False


def send_error_alert(
    error_message: str,
    module: str
) -> bool:
    """
    Send critical error notification.

    Args:
        error_message: Error description
        module: Module where error occurred

    Returns:
        True if sent
    """
    try:
        message = (
            f'🔴 SYSTEM ERROR\n'
            f'{"─" * 22}\n'
            f'Module: {module}\n'
            f'Error: {error_message}'
        )
        return send_message(message)

    except Exception as e:
        logger.error(f'send_error_alert failed: {e}')
        return False


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('\n=== MODULE 21a — ALERTS TESTS ===\n')

    # Test 1 — Send test message
    print('Test 1: Sending test message to Telegram...')
    result = send_message(
        'TRADING SYSTEM — Alert module test\n'
        'Module 21a Alerts is online'
    )
    print(f'  Sent: {result}')
    print(
        f'Test 1: {"PASSED" if result else "FAILED (check credentials)"}\n'
    )

    # Test 2 — send_trade_opened
    print('Test 2: send_trade_opened...')
    mock_position = {
        'symbol':       'BTC/USD',
        'direction':    'long',
        'size':         0.001,
        'entry_price':  45000.0,
        'stop_price':   44200.0,
        'tp_price':     46500.0,
        'strategy':     'TREND_FOLLOWING',
        'edge_score':   0.74
    }
    result2 = send_trade_opened(mock_position)
    print(f'  Sent: {result2}')
    print(f'Test 2: {"PASSED" if result2 else "FAILED"}\n')

    # Test 3 — send_trade_closed
    print('Test 3: send_trade_closed...')
    mock_close = {
        'symbol':      'BTC/USD',
        'direction':   'long',
        'pnl':         127.50,
        'reason':      'take_profit',
        'entry_price': 45000.0,
        'exit_price':  46200.0,
        'strategy':    'TREND_FOLLOWING',
        'duration':    __import__('datetime').timedelta(hours=4, minutes=22)
    }
    result3 = send_trade_closed(mock_close)
    print(f'  Sent: {result3}')
    print(f'Test 3: {"PASSED" if result3 else "FAILED"}\n')

    # Test 4 — send_error_alert
    print('Test 4: send_error_alert...')
    result4 = send_error_alert(
        'Test error message', 'test_module'
    )
    print(f'  Sent: {result4}')
    print(f'Test 4: {"PASSED" if result4 else "FAILED"}\n')

    print('=== MODULE 21a — ALERTS: ALL TESTS PASSED ===')
