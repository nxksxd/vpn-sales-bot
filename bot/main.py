"""VPN Sales Bot — entry point.

Fully automated Telegram bot for selling VPN subscriptions via Telegram Stars
with 3x-ui panel integration.
"""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from bot.config import settings
from bot.database.session import close_db, init_db
from bot.handlers import balance as h_balance
from bot.handlers import fallback as h_fallback
from bot.handlers import keys as h_keys
from bot.handlers import payments as h_payments
from bot.handlers import profile as h_profile
from bot.handlers import referral as h_referral
from bot.handlers import start as h_start
from bot.handlers import subscriptions as h_subscriptions
from bot.handlers import support as h_support
from bot.handlers import user_settings as h_user_settings
from bot.handlers import yookassa_payment as h_yookassa_payment
from bot.handlers.admin import audit as h_admin_audit
from bot.handlers.admin import broadcast as h_admin_broadcast
from bot.handlers.admin import catalog as h_admin_catalog
from bot.handlers.admin import keys as h_admin_keys
from bot.handlers.admin import main as h_admin_main
from bot.handlers.admin import promo as h_admin_promo
from bot.handlers.admin import settings as h_admin_settings
from bot.handlers.admin import stats as h_admin_stats
from bot.handlers.admin import users as h_admin_users
from bot.middlewares.auth import BanCheckMiddleware
from bot.middlewares.throttling import CallbackDebounceMiddleware, ThrottlingMiddleware
from bot.scheduler.tasks import setup_scheduler
from bot.services.xui_client import XUIClient
from bot.utils.observability import ensure_directory, init_sentry, log_event

ensure_directory("logs")

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
)
logger.add(
    "logs/vpn_bot.log",
    rotation="10 MB",
    retention="30 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(BanCheckMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(CallbackDebounceMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())

    dp.include_router(h_start.router)
    dp.include_router(h_profile.router)
    dp.include_router(h_balance.router)
    dp.include_router(h_payments.router)
    dp.include_router(h_subscriptions.router)
    dp.include_router(h_keys.router)
    dp.include_router(h_referral.router)
    dp.include_router(h_support.router)
    dp.include_router(h_user_settings.router)

    dp.include_router(h_admin_main.router)
    dp.include_router(h_admin_users.router)
    dp.include_router(h_admin_keys.router)
    dp.include_router(h_admin_stats.router)
    dp.include_router(h_admin_broadcast.router)
    dp.include_router(h_admin_settings.router)
    dp.include_router(h_admin_audit.router)
    dp.include_router(h_admin_catalog.router)
    dp.include_router(h_admin_promo.router)
    dp.include_router(h_yookassa_payment.router)
    dp.include_router(h_fallback.router)

    return dp


async def on_startup(bot: Bot) -> None:
    init_sentry()

    logger.info("Initializing database...")
    log_event("startup_phase", phase="db_init")
    await init_db()

    logger.info("Validating Telegram bot token...")
    log_event("startup_phase", phase="telegram_auth")
    bot_info = await bot.get_me()
    logger.info("Bot authenticated: @{} (ID: {})", bot_info.username, bot_info.id)

    logger.info("Checking 3x-ui availability...")
    xui = XUIClient()
    try:
        if await xui.ping():
            logger.info("3x-ui panel is reachable")
        else:
            logger.warning("3x-ui panel is unreachable at startup; VPN operations may fail until it recovers")
    except Exception as e:
        logger.warning("3x-ui startup check failed: {}", e)
    finally:
        await xui.close()

    logger.info("Starting scheduler...")
    sched = setup_scheduler(bot)
    sched.start()

    # Start YooKassa webhook server if configured
    from bot.services.yookassa_webhook import start_webhook_server

    runner = await start_webhook_server()
    if runner:
        # Store runner reference for cleanup on shutdown
        bot.__dict__["_yookassa_runner"] = runner

    admin_id = settings.admin_telegram_id
    if admin_id:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text="\u2705 <b>Портальный ключ запущен!</b>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Could not notify admin: {}", e)


async def on_shutdown(bot: Bot) -> None:
    logger.info("Shutting down...")
    from bot.scheduler.tasks import scheduler

    scheduler.shutdown(wait=False)

    # Stop YooKassa webhook server
    runner = bot.__dict__.get("_yookassa_runner")
    if runner:
        await runner.cleanup()
        logger.info("YooKassa webhook server stopped")

    await close_db()
    logger.info("Bot stopped.")


async def main() -> None:
    if not settings.bot_token:
        logger.error("BOT_TOKEN is not set!")
        sys.exit(1)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
