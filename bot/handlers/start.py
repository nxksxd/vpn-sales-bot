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
    payment_method_kb,
    persistent_menu_kb,
)
from bot.keyboards.admin_kb import admin_main_kb
from bot.middlewares.admin_check import is_admin
from bot.services.notification import NotificationService
from bot.services.profile import UserProfileService
from bot.services.start import StartService

router = Router(name="start")

WELCOME_TEXT = (
    "🔐 <b>Портальный ключ</b>\n\n"
    "Добро пожаловать! Здесь вы можете приобрести подписку "
    "и получить быстрый и безопасный доступ к интернету.\n\n"
    "Для быстрого старта:\n"
    "1. Выберите локацию сервера\n"
    "2. Пополните баланс в Telegram Stars\n"
    "3. Купите подписку или запустите trial\n"
    "4. Получите VLESS-ключ и подключитесь\n\n"
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
        start_service = StartService(session)
        start_result = await start_service.process_start(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language_code=user.language_code or "ru",
            text=message.text or "",
        )
        if start_result.referral_notification is not None:
            notif = NotificationService(bot, session)
            await notif.send(
                start_result.referral_notification.referrer_telegram_id,
                "referral_bonus",
                bonus=str(start_result.referral_notification.bonus_rub),
                balance=str(start_result.referral_notification.balance),
            )

    if is_admin(user.id):
        # Admin gets persistent keyboard + admin inline panel
        await message.answer(
            WELCOME_ADMIN_TEXT,
            parse_mode="HTML",
            reply_markup=admin_main_kb(),
        )
    else:
        welcome_text = WELCOME_TEXT
        if start_result.show_onboarding:
            welcome_text += (
                "\n\n🎁 <b>Новым пользователям:</b>\n"
                "• выберите локацию в разделе «Купить подписку»\n"
                f"• доступен trial на {settings.trial_days} день(дней)\n"
                "• можно применить промокод перед покупкой"
            )
        await message.answer(
            welcome_text,
            parse_mode="HTML",
            reply_markup=persistent_menu_kb(),
        )


@router.callback_query(F.data == "u:menu")
async def cb_main_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
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

    from bot.keyboards.product_kb import product_select_kb, region_select_kb  # noqa: F401
    from bot.database.repositories.subscription import SubscriptionRepository
    from bot.keyboards.user_kb import (
        back_to_menu_kb,
        guide_kb,
        subscription_kb,
    )
    from bot.services.referral import ReferralService
    from bot.keyboards.user_kb import user_settings_kb
    from bot.utils.formatters import code, days_until, esc, fmt_date, fmt_rub

    async with async_session_factory() as session:
        user_repo = UserRepository(session)

        if callback_data == "u:profile":
            profile = await UserProfileService(session).get_profile(user.id)
            if profile is None:
                await message.answer(
                    "\u274c Профиль не найден. Отправьте /start",
                    parse_mode="HTML",
                )
                return
            bot_info = await bot.get_me()
            bot_username = bot_info.username or ""
            msg = (
                "\U0001f48e <b>Мой профиль</b>\n\n"
                f"\U0001f194 ID: {code(profile.telegram_id)}\n"
                f"\U0001f464 Username: @{esc(profile.username or '—')}\n"
                f"\U0001f4b0 Баланс: <b>{fmt_rub(profile.balance)}</b>\n"
                f"\U0001f4c5 Дата регистрации: {fmt_date(profile.created_at)}\n"
                f"\U0001f465 Рефералов: {profile.referral_count}\n\n"
                f"\U0001f517 Реферальная ссылка:\n"
                f"{code(f'https://t.me/{bot_username}?start=ref_{profile.referral_code}')}"
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
                await message.answer(
                    msg,
                    parse_mode="HTML",
                    reply_markup=subscription_kb(
                        has_active=True, is_legacy=not active.sub_id
                    ),
                )
            else:
                await message.answer(
                    "\U0001f511 <b>Мои подписки</b>\n\n"
                    "У вас нет активных подписок.\n"
                    "Нажмите «🛒 Купить подписку» чтобы начать.",
                    parse_mode="HTML",
                    reply_markup=subscription_kb(has_active=False),
                )

        elif callback_data == "u:buy":
            # Воронка покупки одинакова для всех пользователей вне
            # зависимости от наличия активной подписки:
            #   Продукт → Регион → Срок → Подтверждение.
            # Это позволит в будущем продавать не только VLESS-подписку,
            # но и другие продукты. Продление существующей подписки
            # доступно отдельно через «Мои подписки» → «Продлить».
            db_user = await user_repo.get_by_telegram_id(user.id)
            balance = db_user.balance if db_user else 0
            await message.answer(
                "🛒 <b>Купить подписку</b>\n\n"
                f"💰 Ваш баланс: <b>{fmt_rub(balance)}</b>\n\n"
                "Выберите, что хотите приобрести. После выбора продукта вы "
                "сможете указать регион и срок подписки.",
                parse_mode="HTML",
                reply_markup=product_select_kb(),
            )

        elif callback_data == "u:topup":
            await message.answer(
                "\U0001f4b0 <b>Пополнение баланса</b>\n\n"
                "Выберите способ оплаты:",
                parse_mode="HTML",
                reply_markup=payment_method_kb(),
            )

        elif callback_data == "sub:show_key":
            sub_repo = SubscriptionRepository(session)
            active = await sub_repo.get_active_by_user(user.id)
            sub_url = settings.subscription_url(active.sub_id) if active else None
            if active is None or (not sub_url and not active.vless_link):
                await message.answer(
                    "🔑 <b>У вас пока нет активного ключа</b>\n\n"
                    "Оформите подписку, и ключ появится в этом меню.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            elif sub_url:
                msg = (
                    "🔗 <b>Ваша ссылка-подписка</b>\n\n"
                    "Скопируйте её и добавьте в приложение (V2RayTun, Hiddify, "
                    "v2rayNG, Streisand и т.п.) как <b>«Subscription»</b> / "
                    "<b>«Подписка»</b>:\n\n"
                    f"{code(sub_url)}\n\n"
                    "📱 <i>Тапните по ссылке — она скопируется. "
                    "Конфиг будет обновляться автоматически.</i>"
                )
                await message.answer(
                    msg, parse_mode="HTML", reply_markup=subscription_kb(has_active=True)
                )
            else:
                msg = (
                    "🔑 <b>Ваш ключ VLESS</b>\n\n"
                    "Скопируйте ссылку ниже и добавьте её в приложение "
                    "как <b>конфиг VLESS</b>:\n\n"
                    f"{code(active.vless_link)}\n\n"
                    "ℹ️ <i>Это старый формат ключа. Для удобной ссылки-подписки "
                    "нажмите «Обновить ключ» в меню подписки.</i>"
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
