"""/start command and main menu navigation."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.database.session import async_session_factory
from bot.database.repositories.user import UserRepository
from bot.keyboards.user_kb import main_menu_kb
from bot.keyboards.admin_kb import admin_main_kb
from bot.middlewares.admin_check import is_admin
from bot.services.referral import ReferralService

router = Router(name="start")

WELCOME_TEXT = (
    "\U0001f510 <b>VPN Bot</b>\n\n"
    "Добро пожаловать! Здесь вы можете приобрести VPN-подписку "
    "и получить быстрый и безопасный доступ к интернету.\n\n"
    "Выберите действие:"
)

WELCOME_ADMIN_TEXT = (
    "\U0001f510 <b>VPN Bot — Админ-панель</b>\n\n"
    "Добро пожаловать, администратор!\n\n"
    "Выберите действие:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return

    async with async_session_factory() as session:
        repo = UserRepository(session)
        await repo.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language_code=user.language_code or "ru",
        )

        args = message.text or ""
        if args.startswith("/start ref_"):
            ref_code = args.split("ref_", 1)[1].strip()
            if ref_code:
                ref_service = ReferralService(session)
                result = await ref_service.process_referral(user.id, ref_code)
                if result:
                    from bot.services.notification import NotificationService

                    referrer = await repo.get_by_referral_code(ref_code)
                    if referrer:
                        notif = NotificationService(bot, session)
                        await notif.send(
                            referrer.telegram_id,
                            "referral_bonus",
                            bonus=str(settings.referral_bonus_stars),
                            balance=str(referrer.balance + settings.referral_bonus_stars),
                        )

    if is_admin(user.id):
        await message.answer(
            WELCOME_ADMIN_TEXT,
            parse_mode="HTML",
            reply_markup=admin_main_kb(),
        )
    else:
        await message.answer(
            WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )


@router.callback_query(F.data == "u:menu")
async def cb_main_menu(call: CallbackQuery) -> None:
    await call.answer()
    user = call.from_user
    if user and is_admin(user.id):
        text = WELCOME_ADMIN_TEXT
        kb = admin_main_kb()
    else:
        text = WELCOME_TEXT
        kb = main_menu_kb()

    if call.message is not None:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()
