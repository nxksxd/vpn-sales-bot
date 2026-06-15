"""/start command, main menu navigation, and persistent keyboard routing."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.database.session import async_session_factory
from bot.database.repositories.user import UserRepository
from bot.keyboards.user_kb import (
    MENU_BUTTONS_MAP,
    persistent_menu_kb,
)
from bot.keyboards.admin_kb import admin_main_kb
from bot.middlewares.admin_check import is_admin
from bot.services.referral import ReferralService

router = Router(name="start")

WELCOME_TEXT = (
    "\U0001f510 <b>Портальный ключ</b>\n\n"
    "Добро пожаловать! Здесь вы можете приобрести подписку "
    "и получить быстрый и безопасный доступ к интернету.\n\n"
    "Выберите действие:"
)

WELCOME_ADMIN_TEXT = (
    "\U0001f510 <b>Портальный ключ — Админ-панель</b>\n\n"
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
                            bonus=str(settings.referral_bonus_rub),
                            balance=str(referrer.balance + settings.referral_bonus_rub),
                        )

    if is_admin(user.id):
        # Admin gets persistent keyboard + admin inline panel
        await message.answer(
            WELCOME_ADMIN_TEXT,
            parse_mode="HTML",
            reply_markup=admin_main_kb(),
        )
    else:
        # Regular user gets only persistent reply keyboard (no inline duplicates)
        await message.answer(
            WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=persistent_menu_kb(),
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
        kb = None  # regular users use persistent reply keyboard

    if call.message is not None:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


# ── Persistent reply keyboard text handler ─────────────────────────

@router.message(F.text.in_(MENU_BUTTONS_MAP.keys()))
async def handle_menu_button(message: Message, bot: Bot, state: FSMContext) -> None:
    """Route persistent keyboard button presses to handlers."""
    await state.clear()
    text = message.text or ""
    callback_data = MENU_BUTTONS_MAP.get(text)
    if not callback_data:
        return

    user = message.from_user
    if user is None:
        return

    # Import here to avoid circular imports
    from bot.database.repositories.subscription import SubscriptionRepository
    from bot.keyboards.user_kb import (
        back_to_menu_kb,
        buy_plan_kb,
        guide_kb,
        renew_plan_kb,
        subscription_kb,
        topup_kb,
    )
    from bot.services.referral import ReferralService
    from bot.keyboards.user_kb import user_settings_kb
    from bot.utils.formatters import code, days_until, esc, fmt_date, fmt_plan, fmt_rub, pluralize_days

    async with async_session_factory() as session:
        user_repo = UserRepository(session)

        if callback_data == "u:profile":
            db_user = await user_repo.get_by_telegram_id(user.id)
            if db_user is None:
                await message.answer(
                    "\u274c Профиль не найден. Отправьте /start",
                    parse_mode="HTML",
                )
                return
            referral_count = await user_repo.get_referral_count(user.id)
            bot_info = await bot.get_me()
            bot_username = bot_info.username or ""
            msg = (
                "\U0001f48e <b>Мой профиль</b>\n\n"
                f"\U0001f194 ID: {code(db_user.telegram_id)}\n"
                f"\U0001f464 Username: @{esc(db_user.username or '—')}\n"
                f"\U0001f4b0 Баланс: <b>{fmt_rub(db_user.balance)}</b>\n"
                f"\U0001f4c5 Дата регистрации: {fmt_date(db_user.created_at)}\n"
                f"\U0001f465 Рефералов: {referral_count}\n\n"
                f"\U0001f517 Реферальная ссылка:\n"
                f"{code(f'https://t.me/{bot_username}?start=ref_{db_user.referral_code}')}"
            )
            await message.answer(msg, parse_mode="HTML", reply_markup=back_to_menu_kb())

        elif callback_data == "u:subs":
            sub_repo = SubscriptionRepository(session)
            active = await sub_repo.get_active_by_user(user.id)
            if active:
                from bot.utils.formatters import fmt_status, fmt_traffic_limit, days_until
                days_left = days_until(active.expires_at)
                msg = (
                    "\U0001f511 <b>Мои подписки</b>\n\n"
                    f"📋 План: <b>{active.plan_type}</b>\n"
                    f"📊 Статус: {fmt_status(active.status)}\n"
                    f"📅 Действует до: <b>{fmt_date(active.expires_at)}</b>\n"
                    f"⏳ Осталось: <b>{days_left} дн.</b>\n"
                    f"📶 Трафик: {fmt_traffic_limit(active.traffic_limit_gb)}\n"
                )
                await message.answer(msg, parse_mode="HTML", reply_markup=subscription_kb(has_active=True))
            else:
                await message.answer(
                    "\U0001f511 <b>Мои подписки</b>\n\n"
                    "У вас нет активных подписок.\n"
                    "Нажмите «🛒 Купить подписку» чтобы начать.",
                    parse_mode="HTML",
                    reply_markup=subscription_kb(has_active=False),
                )

        elif callback_data == "u:buy":
            sub_repo = SubscriptionRepository(session)
            active = await sub_repo.get_active_by_user(user.id)
            if active:
                remaining = days_until(active.expires_at)
                await message.answer(
                    "\U0001f504 <b>Продление подписки</b>\n\n"
                    f"У вас уже есть активная подписка (<b>{fmt_plan(active.plan_type)}</b>, "
                    f"осталось <b>{pluralize_days(remaining)}</b>).\n\n"
                    "Выберите период продления:",
                    parse_mode="HTML",
                    reply_markup=renew_plan_kb(),
                )
            else:
                await message.answer(
                    "\U0001f6d2 <b>Выберите план подписки:</b>",
                    parse_mode="HTML",
                    reply_markup=buy_plan_kb(),
                )

        elif callback_data == "u:topup":
            await message.answer(
                "\U0001f4b0 <b>Пополнение баланса</b>\n\n"
                "Выберите сумму пополнения в Telegram Stars:",
                parse_mode="HTML",
                reply_markup=topup_kb(),
            )

        elif callback_data == "sub:show_key":
            sub_repo = SubscriptionRepository(session)
            active = await sub_repo.get_active_by_user(user.id)
            if active is None or not active.vless_link:
                await message.answer(
                    "\u274c У вас нет активного ключа.\n"
                    "Купите подписку чтобы получить ключ.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            else:
                msg = (
                    "\U0001f511 <b>Ваш ключ VLESS</b>\n\n"
                    "Скопируйте ссылку ниже и вставьте в приложение:\n\n"
                    f"{code(active.vless_link)}\n\n"
                    "\U0001f4f1 <i>Нажмите на ссылку чтобы скопировать</i>"
                )
                await message.answer(
                    msg, parse_mode="HTML", reply_markup=subscription_kb(has_active=True)
                )

        elif callback_data == "u:support":
            support = settings.support_username
            support_text = f"@{support}" if support else "администратору бота"
            await message.answer(
                "\U0001f198 <b>Поддержка</b>\n\n"
                "Если у вас возникли вопросы или проблемы:\n\n"
                f"\U0001f4ac Напишите {support_text}\n"
                "\U0001f4e7 Или опишите проблему здесь, и мы ответим вам.\n\n"
                "<i>Обычно отвечаем в течение 24 часов.</i>",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
            )

        elif callback_data == "u:guide":
            await message.answer(
                "\U0001f4d6 <b>Инструкция по подключению</b>\n\n"
                "Выберите вашу платформу:",
                parse_mode="HTML",
                reply_markup=guide_kb(),
            )

        elif callback_data == "u:ref":
            ref_service = ReferralService(session)
            stats = await ref_service.get_referral_stats(user.id)
            bot_info = await bot.get_me()
            bot_username = bot_info.username or ""
            ref_link = f"https://t.me/{bot_username}?start=ref_{stats['referral_code']}"
            msg = (
                "\U0001f465 <b>Реферальная программа</b>\n\n"
                f"\U0001f517 Ваша реферальная ссылка:\n{code(ref_link)}\n\n"
                f"\U0001f465 Приглашено: <b>{stats['count']}</b> пользователей\n"
                f"\U0001f4b0 Заработано: <b>{fmt_rub(stats['earned'])}</b>\n\n"
                f"\U0001f381 Бонус за каждого реферала: <b>{fmt_rub(settings.referral_bonus_rub)}</b>\n\n"
                "<i>Поделитесь ссылкой с друзьями и получайте бонусы!</i>"
            )
            await message.answer(msg, parse_mode="HTML", reply_markup=back_to_menu_kb())

        elif callback_data == "u:settings":
            db_user = await user_repo.get_by_telegram_id(user.id)
            auto_renew = db_user.auto_renew if db_user else True
            await message.answer(
                "\u2699\ufe0f <b>Настройки</b>\n\n"
                "Управление вашим аккаунтом:",
                parse_mode="HTML",
                reply_markup=user_settings_kb(auto_renew),
            )
