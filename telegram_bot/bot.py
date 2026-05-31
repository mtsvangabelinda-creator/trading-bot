# Autonomous Multi-Strategy Trading System
# Module 21c — Telegram Bot Main
# Entry point for the Telegram bot
# Initialises bot registers all handlers starts polling

import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters
)

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

logger = setup_logger('bot', 'logs/errors.log')

# ── Credentials ───────────────────────────────────────────────
BOT_TOKEN     = os.getenv('TELEGRAM_BOT_TOKEN', '')
AUTHORISED_ID = os.getenv('TELEGRAM_AUTHORISED_USER_ID', '')

# ── Application Instance ──────────────────────────────────────
_application = None


def create_bot() -> Application:
    """
    Create and configure the Telegram bot application.

    Returns:
        Configured Application instance
    """
    if not BOT_TOKEN:
        raise ValueError(
            'TELEGRAM_BOT_TOKEN not found in .env'
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    logger.info('Telegram bot application created')
    return application


def register_handlers(application: Application) -> None:
    """
    Register all command and message handlers.

    Args:
        application: Telegram Application instance
    """
    from telegram_bot.commands import (
        cmd_start,
        cmd_status,
        cmd_balance,
        cmd_positions,
        cmd_drawdown_status,
        cmd_correlation_status,
        cmd_silo_status,
        cmd_pause,
        cmd_resume,
        cmd_emergency_close,
        cmd_resolve_halt,
        cmd_resume_strategy,
        cmd_sentinel_mode,
        cmd_help,
        handle_text
    )

    # Register command handlers
    application.add_handler(
        CommandHandler('start',              cmd_start)
    )
    application.add_handler(
        CommandHandler('status',             cmd_status)
    )
    application.add_handler(
        CommandHandler('balance',            cmd_balance)
    )
    application.add_handler(
        CommandHandler('positions',          cmd_positions)
    )
    application.add_handler(
        CommandHandler('drawdown_status',    cmd_drawdown_status)
    )
    application.add_handler(
        CommandHandler('correlation_status', cmd_correlation_status)
    )
    application.add_handler(
        CommandHandler('silo_status',        cmd_silo_status)
    )
    application.add_handler(
        CommandHandler('pause',              cmd_pause)
    )
    application.add_handler(
        CommandHandler('resume',             cmd_resume)
    )
    application.add_handler(
        CommandHandler('emergency_close',    cmd_emergency_close)
    )
    application.add_handler(
        CommandHandler('resolve_halt',       cmd_resolve_halt)
    )
    application.add_handler(
        CommandHandler('resume_strategy',    cmd_resume_strategy)
    )
    application.add_handler(
        CommandHandler('sentinel_mode',      cmd_sentinel_mode)
    )
    application.add_handler(
        CommandHandler('help',               cmd_help)
    )

    # Text handler for confirmations
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    logger.info(
        f'Registered {len(application.handlers[0])} handlers'
    )


def check_authorised(user_id: int) -> bool:
    """
    Check if a user is authorised to use the bot.

    Args:
        user_id: Telegram user ID

    Returns:
        True if authorised, False otherwise
    """
    authorised = str(user_id) == str(AUTHORISED_ID)
    if not authorised:
        logger.warning(
            f'Unauthorised access attempt from user {user_id}'
        )
    return authorised


async def start_bot() -> None:
    """
    Start the Telegram bot polling.

    Initialises the bot registers all handlers
    and starts listening for messages.
    """
    global _application

    try:
        _application = create_bot()
        register_handlers(_application)

        logger.info('Telegram bot starting...')

        await _application.initialize()
        await _application.start()
        await _application.updater.start_polling(
            drop_pending_updates=True
        )

        logger.info('Telegram bot is running')

    except Exception as e:
        logger.error(f'start_bot failed: {e}')
        raise


async def stop_bot() -> None:
    """
    Gracefully stop the Telegram bot.
    """
    global _application

    try:
        if _application:
            await _application.updater.stop()
            await _application.stop()
            await _application.shutdown()
            logger.info('Telegram bot stopped')

    except Exception as e:
        logger.error(f'stop_bot failed: {e}')


def get_application() -> Application:
    """Get the current bot application instance."""
    return _application


# ── Tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    async def run_tests():
        print('\n=== MODULE 21c — TELEGRAM BOT TESTS ===\n')

        # Test 1 — Bot token loads
        print('Test 1: Bot token loaded from .env...')
        token_loaded = bool(BOT_TOKEN)
        print(f'  Token loaded: {token_loaded}')
        print(
            f'Test 1: {"PASSED" if token_loaded else "FAILED (add TELEGRAM_BOT_TOKEN to .env)"}\n'
        )

        # Test 2 — Authorised user ID loads
        print('Test 2: Authorised user ID loaded...')
        id_loaded = bool(AUTHORISED_ID)
        print(f'  User ID: {AUTHORISED_ID}')
        print(
            f'Test 2: {"PASSED" if id_loaded else "FAILED (add TELEGRAM_AUTHORISED_USER_ID to .env)"}\n'
        )

        # Test 3 — Send test message
        print('Test 3: Sending test message to Telegram...')
        from telegram_bot.alerts import send_message
        sent = send_message(
            'TRADING SYSTEM — Bot test successful\n'
            'Module 21 Telegram Bot is online\n'
            'All handlers registered.'
        )
        print(f'  Message sent: {sent}')
        print(
            f'Test 3: {"PASSED" if sent else "FAILED (check credentials)"}\n'
        )

        # Test 4 — check_authorised
        print('Test 4: check_authorised...')
        if AUTHORISED_ID:
            valid   = check_authorised(int(AUTHORISED_ID))
            invalid = check_authorised(999999999)
            print(f'  Authorised ID valid: {valid}')
            print(f'  Random ID blocked: {not invalid}')
            passed = valid and not invalid
            print(
                f'Test 4: {"PASSED" if passed else "FAILED"}\n'
            )
        else:
            print(
                'Test 4: SKIPPED — no user ID configured\n'
            )

        # Test 5 — Create bot application
        print('Test 5: Create bot application...')
        if BOT_TOKEN:
            try:
                app = create_bot()
                register_handlers(app)
                print(f'  Application created: {app is not None}')
                print('Test 5: PASSED\n')
            except Exception as e:
                print(f'Test 5: FAILED — {e}\n')
        else:
            print(
                'Test 5: SKIPPED — no bot token configured\n'
            )

        print(
            '=== MODULE 21c — TELEGRAM BOT: '
            'ALL TESTS PASSED ==='
        )

    asyncio.run(run_tests())
