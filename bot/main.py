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
from bot.middlewares.auth import BanCheckMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware

from bot.handlers import start as h_start
from bot.handlers import profile as h_profile
from bot.handlers import balance as h_balance
from bot.handlers import payments as h_payments
from bot.handlers import subscriptions as h_subscriptions
from bot.handlers import keys as h_keys
from bot.handlers import referral as h_referral
from bot.handlers import support as h_support
from bot.handlers.admin import main as h_admin_main
from bot.handlers.admin import users as h_admin_users
from bot.handlers.admin import keys as h_admin_keys
from bot.handlers.admin import stats as h_admin_stats
from bot.handlers.admin import broadcast as h_admin_broadcast
from bot.handlers.admin import settings as h_admin_settings

from bot.scheduler.tasks import setup_scheduler

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
    dp.callback_query.middleware(ThrottlingMiddleware())

    dp.include_router(h_start.router)
    dp.include_router(h_profile.router)
    dp.include_router(h_balance.router)
    dp.include_router(h_payments.router)
    dp.include_router(h_subscriptions.router)
    dp.include_router(h_keys.router)
    dp.include_router(h_referral.router)
    dp.include_router(h_support.router)

    dp.include_router(h_admin_main.router)
    dp.include_router(h_admin_users.router)
    dp.include_router(h_admin_keys.router)
    dp.include_router(h_admin_stats.router)
    dp.include_router(h_admin_broadcast.router)
    dp.include_router(h_admin_settings.router)

    return dp


async def on_startup(bot: Bot) -> None:
    logger.info("Initializing database...")
    await init_db()

    logger.info("Starting scheduler...")
    sched = setup_scheduler(bot)
    sched.start()

    bot_info = await bot.get_me()
    logger.info("Bot started: @{} (ID: {})", bot_info.username, bot_info.id)

    admin_id = settings.admin_telegram_id
    if admin_id:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text="\u2705 <b>VPN Bot запущен!</b>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Could not notify admin: {}", e)


async def on_shutdown(bot: Bot) -> None:
    logger.info("Shutting down...")
    from bot.scheduler.tasks import scheduler

    scheduler.shutdown(wait=False)
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
