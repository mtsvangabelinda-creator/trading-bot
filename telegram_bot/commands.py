# Autonomous Multi-Strategy Trading System
# Module 21b — Telegram Commands
# Handles all incoming commands from the authorised user
# Every command checks authorisation before executing

import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

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

logger         = setup_logger('commands', 'logs/errors.log')
commands_logger = setup_logger('commands_log', 'logs/commands.log')

AUTHORISED_ID = os.getenv('TELEGRAM_AUTHORISED_USER_ID', '')

# ── Pause State ───────────────────────────────────────────────
_system_paused           = False
_pending_confirmations   = {}
_emergency_confirm_phrase = 'CONFIRM EMERGENCY CLOSE'


def is_authorised(user_id: int) -> bool:
    """Check if user is authorised."""
    return str(user_id) == str(AUTHORISED_ID)


def log_command(
    user_id: int,
    command: str,
    args: list = None
) -> None:
    """Log command to commands log."""
    commands_logger.info(
        f'COMMAND | user={user_id} | '
        f'cmd={command} | args={args}'
    )


async def cmd_start(update, context) -> None:
    """Handle /start command."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/start')

        message = (
            'AUTONOMOUS TRADING SYSTEM\n'
            '─────────────────────────\n'
            'Available commands:\n\n'
            '/status — Full system snapshot\n'
            '/balance — Live Kraken balance\n'
            '/positions — Open positions\n'
            '/edge_scores — Current edge scores\n'
            '/sentiment — Structural sentiment\n'
            '/drawdown_status — Drawdown levels\n'
            '/correlation_status — Correlation\n'
            '/silo_status — Strategy silos\n'
            '/pause — Stop new entries\n'
            '/resume — Resume trading\n'
            '/emergency_close — Close all now\n'
            '/resolve_halt PEAK — Resolve halt\n'
            '/resume_strategy BTC/USD TF — '
            'Resume silo\n'
            '/sentinel_mode normal — Set mode\n'
            '/backtest BTC/USD 30 — Quick test\n'
            '/help — Show this message'
        )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f'cmd_start failed: {e}')


async def cmd_status(update, context) -> None:
    """Handle /status command — full system snapshot."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/status')

        from execution.kraken_client import KrakenClient
        from execution.order_manager import (
            format_position_summary
        )
        from core.edge_score import (
            calculate_all, get_summary
        )
        from core.sentiment import (
            calculate_all as sent_all,
            get_summary as sent_summary
        )
        from risk.drawdown_guard import get_status as dd_status
        from risk.correlation_breaker import (
            get_status as corr_status
        )
        from data.ohlcv_fetcher import OHLCVFetcher

        await update.message.reply_text(
            'Fetching system status...'
        )

        # Get balance
        client  = KrakenClient()
        balance = await client.fetch_balance()
        await client.close()

        balance_str = 'N/A'
        if balance:
            balance_str = ', '.join([
                f'{k}: {round(v, 4)}'
                for k, v in list(balance.items())[:3]
            ])

        # Get positions
        positions = format_position_summary()

        # Get drawdown status
        dd = await dd_status()

        # Get correlation status
        corr = await corr_status()

        message = (
            f'SYSTEM STATUS\n'
            f'{"─" * 24}\n'
            f'Balance: {balance_str}\n'
            f'{"─" * 24}\n'
            f'{positions}\n'
            f'{"─" * 24}\n'
            f'{dd}\n'
            f'{"─" * 24}\n'
            f'Trading: '
            f'{"PAUSED" if _system_paused else "ACTIVE"}'
        )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f'cmd_status failed: {e}')
        await update.message.reply_text(
            f'Status error: {e}'
        )


async def cmd_balance(update, context) -> None:
    """Handle /balance command."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/balance')

        from execution.kraken_client import KrakenClient
        client  = KrakenClient()
        balance = await client.fetch_balance()
        await client.close()

        if balance:
            lines = ['ACCOUNT BALANCE', '─' * 20]
            for currency, amount in balance.items():
                lines.append(
                    f'{currency}: {round(amount, 6)}'
                )
            await update.message.reply_text(
                '\n'.join(lines)
            )
        else:
            await update.message.reply_text(
                'Could not fetch balance.'
            )

    except Exception as e:
        logger.error(f'cmd_balance failed: {e}')
        await update.message.reply_text(f'Error: {e}')


async def cmd_positions(update, context) -> None:
    """Handle /positions command."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/positions')

        from execution.order_manager import (
            format_position_summary
        )
        summary = format_position_summary()
        await update.message.reply_text(summary)

    except Exception as e:
        logger.error(f'cmd_positions failed: {e}')
        await update.message.reply_text(f'Error: {e}')


async def cmd_drawdown_status(update, context) -> None:
    """Handle /drawdown_status command."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/drawdown_status')

        from risk.drawdown_guard import get_status
        status = await get_status()
        await update.message.reply_text(status)

    except Exception as e:
        logger.error(f'cmd_drawdown_status failed: {e}')
        await update.message.reply_text(f'Error: {e}')


async def cmd_correlation_status(update, context) -> None:
    """Handle /correlation_status command."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/correlation_status')

        from risk.correlation_breaker import get_status
        status = await get_status()
        await update.message.reply_text(status)

    except Exception as e:
        logger.error(f'cmd_correlation_status failed: {e}')
        await update.message.reply_text(f'Error: {e}')


async def cmd_silo_status(update, context) -> None:
    """Handle /silo_status command."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/silo_status')

        from risk.strategy_silo import (
            get_all_status, format_summary
        )
        all_status = await get_all_status()
        summary    = format_summary(all_status)
        await update.message.reply_text(summary)

    except Exception as e:
        logger.error(f'cmd_silo_status failed: {e}')
        await update.message.reply_text(f'Error: {e}')


async def cmd_pause(update, context) -> None:
    """Handle /pause command — stop new entries."""
    try:
        global _system_paused
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/pause')

        _system_paused = True
        await update.message.reply_text(
            'System PAUSED — no new entries.\n'
            'Existing positions remain open.\n'
            'Use /resume to restart.'
        )

    except Exception as e:
        logger.error(f'cmd_pause failed: {e}')


async def cmd_resume(update, context) -> None:
    """Handle /resume command."""
    try:
        global _system_paused
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/resume')

        _system_paused = False
        await update.message.reply_text(
            'System RESUMED — trading active.'
        )

    except Exception as e:
        logger.error(f'cmd_resume failed: {e}')


async def cmd_emergency_close(update, context) -> None:
    """Handle /emergency_close — requires confirmation."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        log_command(user_id, '/emergency_close')

        # Set pending confirmation
        _pending_confirmations[user_id] = 'emergency_close'

        await update.message.reply_text(
            'EMERGENCY CLOSE requested.\n\n'
            f'Type exactly:\n{_emergency_confirm_phrase}\n\n'
            'This will close ALL positions immediately.'
        )

    except Exception as e:
        logger.error(f'cmd_emergency_close failed: {e}')


async def cmd_resolve_halt(update, context) -> None:
    """Handle /resolve_halt PEAK command."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        args = context.args
        log_command(user_id, '/resolve_halt', args)

        if not args:
            await update.message.reply_text(
                'Usage: /resolve_halt PEAK or INTRADAY or WEEKLY'
            )
            return

        halt_type = args[0].upper()
        if halt_type not in ['PEAK', 'INTRADAY', 'WEEKLY']:
            await update.message.reply_text(
                'Invalid halt type. Use PEAK, INTRADAY, or WEEKLY'
            )
            return

        from risk.drawdown_guard import resolve_halt
        result = await resolve_halt(f'{halt_type}_HALT')

        if result:
            await update.message.reply_text(
                f'{halt_type}_HALT resolved. Trading resumed.'
            )
        else:
            await update.message.reply_text(
                f'Could not resolve {halt_type}_HALT.'
            )

    except Exception as e:
        logger.error(f'cmd_resolve_halt failed: {e}')
        await update.message.reply_text(f'Error: {e}')


async def cmd_resume_strategy(update, context) -> None:
    """Handle /resume_strategy BTC/USD TREND_FOLLOWING."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        args = context.args
        log_command(user_id, '/resume_strategy', args)

        if not args or len(args) < 2:
            await update.message.reply_text(
                'Usage: /resume_strategy ASSET STRATEGY\n'
                'Example: /resume_strategy BTC/USD '
                'TREND_FOLLOWING'
            )
            return

        asset    = args[0].upper()
        strategy = args[1].upper()

        from risk.strategy_silo import resume_strategy
        result = await resume_strategy(asset, strategy)

        if result:
            await update.message.reply_text(
                f'{asset} {strategy} resumed successfully.'
            )
        else:
            await update.message.reply_text(
                f'Could not resume {asset} {strategy}.'
            )

    except Exception as e:
        logger.error(f'cmd_resume_strategy failed: {e}')
        await update.message.reply_text(f'Error: {e}')


async def cmd_sentinel_mode(update, context) -> None:
    """Handle /sentinel_mode normal|paranoid|relaxed."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        args = context.args
        log_command(user_id, '/sentinel_mode', args)

        if not args:
            await update.message.reply_text(
                'Usage: /sentinel_mode normal or paranoid or relaxed'
            )
            return

        mode = args[0].lower()
        if mode not in ['normal', 'paranoid', 'relaxed']:
            await update.message.reply_text(
                'Invalid mode. Use normal, paranoid, or relaxed'
            )
            return

        from sentinel.sentinel import set_sentinel_mode
        set_sentinel_mode(mode)

        await update.message.reply_text(
            f'Sentinel mode set to: {mode.upper()}'
        )

    except Exception as e:
        logger.error(f'cmd_sentinel_mode failed: {e}')
        await update.message.reply_text(f'Error: {e}')


async def cmd_help(update, context) -> None:
    """Handle /help command."""
    await cmd_start(update, context)


async def handle_text(update, context) -> None:
    """Handle plain text messages — used for confirmations."""
    try:
        user_id = update.effective_user.id
        if not is_authorised(user_id):
            return

        text = update.message.text.strip()

        # Check pending emergency close confirmation
        if (
            _pending_confirmations.get(user_id) ==
            'emergency_close' and
            text == _emergency_confirm_phrase
        ):
            del _pending_confirmations[user_id]
            log_command(user_id, 'EMERGENCY_CLOSE_CONFIRMED')

            from execution.kraken_client import KrakenClient
            from execution.order_manager import (
                emergency_close_all
            )

            client = KrakenClient()
            count  = await emergency_close_all(client)
            await client.close()

            await update.message.reply_text(
                f'EMERGENCY CLOSE COMPLETE\n'
                f'{count} positions closed.'
            )
        elif _pending_confirmations.get(user_id):
            del _pending_confirmations[user_id]
            await update.message.reply_text(
                'Confirmation cancelled.'
            )

    except Exception as e:
        logger.error(f'handle_text failed: {e}')


def is_system_paused() -> bool:
    """Check if system is manually paused."""
    return _system_paused
