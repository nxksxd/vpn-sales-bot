"""Subscription purchase, view, and renewal handlers."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger

from bot.config import settings
from bot.database.session import async_session_factory
from bot.database.repositories.promo_code import PromoCodeRepository
from bot.database.repositories.server_region import ServerRegionRepository
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.user import UserRepository
from bot.keyboards.user_kb import (
    back_to_menu_kb,
    buy_plan_kb,
    confirm_purchase_kb,
    renew_plan_kb,
    subscription_kb,
)
from bot.keyboards.product_kb import PRODUCTS, product_select_kb, region_select_kb
from bot.services.notification import NotificationService
from bot.services.subscription import SubscriptionService, UserFacingError
from bot.services.subscription_use_cases import SubscriptionUseCases
from bot.services.xui_client import XUIClient
from bot.utils.formatters import (
    code,
    days_until,
    fmt_date,
    fmt_plan,
    fmt_price,
    fmt_rub,
    fmt_status,
    fmt_traffic_limit,
    pluralize_days,
)

router = Router(name="subscriptions")


class PurchaseStates(StatesGroup):
    waiting_promo = State()


@router.callback_query(F.data == "u:regions")
async def cb_regions(call: CallbackQuery) -> None:
    """Legacy alias — redirect to the new product selection screen."""
    await call.answer()
    async with async_session_factory() as session:
        repo = ServerRegionRepository(session)
        region_rows = [
            {"code": region.code, "label": region.label}
            for region in await repo.get_active_regions()
        ]
    text = (
        "🌍 <b>Выбор локации</b>\n\n"
        "Выберите регион сервера."
    )
    if call.message:
        await call.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=region_select_kb(region_rows, product_code="vless"),
        )


def _product_label(product_code: str) -> str:
    for p in PRODUCTS:
        if p["code"] == product_code:
            return p["label"]
    return product_code


@router.callback_query(F.data.startswith("prod:"))
async def cb_product_selected(call: CallbackQuery) -> None:
    """Step 2 of purchase funnel — region picker for the chosen product.

    Callback formats:
      * ``prod:<product>`` — entered from product menu
      * ``prod:<product>:<PROMO>`` — preserves applied promo code
    """
    await call.answer()
    parts = (call.data or "").split(":")
    product_code = parts[1] if len(parts) > 1 else "vless"
    promo_code = parts[2] if len(parts) > 2 else None

    async with async_session_factory() as session:
        repo = ServerRegionRepository(session)
        region_rows = [
            {"code": region.code, "label": region.label}
            for region in await repo.get_active_regions()
        ]

    if not region_rows:
        text = (
            f"🌍 <b>{_product_label(product_code)} — выбор региона</b>\n\n"
            "❌ Сейчас нет доступных регионов. Попробуйте позже."
        )
        if call.message:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=back_to_menu_kb())
        return

    promo_text = f"\n🎁 Применён промокод: <b>{promo_code}</b>" if promo_code else ""
    text = (
        f"🌍 <b>{_product_label(product_code)} — выбор региона</b>\n\n"
        f"Выберите страну сервера:{promo_text}"
    )
    if call.message:
        await call.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=region_select_kb(region_rows, product_code=product_code, promo_code=promo_code),
        )


@router.callback_query(F.data.startswith("region:"))
async def cb_region_selected(call: CallbackQuery) -> None:
    """Step 3 — duration picker.

    Callback formats:
      * ``region:<product>:<code>`` — new format
      * ``region:<product>:<code>:<PROMO>``
      * ``region:<code>`` — legacy (assume product=vless)
    """
    await call.answer("Локация выбрана")
    parts = (call.data or "").split(":")
    # New format: region:<product>:<code>[:<promo>]
    if len(parts) >= 3:
        product_code = parts[1]
        region_code = parts[2]
        promo_code = parts[3] if len(parts) > 3 else None
    else:
        product_code = "vless"
        region_code = parts[1] if len(parts) > 1 else "default"
        promo_code = None

    async with async_session_factory() as session:
        xui = XUIClient()
        uc = SubscriptionUseCases(session, xui)
        region = await uc.resolve_region(region_code)

    region_label = region.label if region is not None else settings.server_regions.get(region_code, {}).get("label", region_code)
    promo_line = f"\n🎁 Промокод: <b>{promo_code}</b>" if promo_code else ""
    text = (
        f"🛒 <b>{_product_label(product_code)} — выбор срока</b>\n\n"
        f"🌍 Локация: <b>{region_label}</b>{promo_line}\n\n"
        "Выберите, на сколько месяцев оформить подписку:"
    )
    if call.message:
        await call.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=buy_plan_kb(
                region_code=region_code,
                promo_code=promo_code,
                product_code=product_code,
            ),
        )


@router.callback_query(F.data == "u:promo")
async def cb_enter_promo(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(PurchaseStates.waiting_promo)
    if call.message:
        await call.message.edit_text(
            "🎁 <b>Промокод</b>\n\nОтправьте промокод сообщением.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb(),
        )


@router.message(PurchaseStates.waiting_promo)
async def msg_enter_promo(message: Message, state: FSMContext) -> None:
    promo_code = (message.text or "").strip().upper()
    await state.clear()
    async with async_session_factory() as session:
        uc = SubscriptionUseCases(session, XUIClient())
        promo = await uc.resolve_promo(promo_code)
    if promo is None and promo_code not in settings.promo_codes:
        await message.answer(
            "❌ Промокод не найден или неактивен.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb(),
        )
        return
    discount = promo.discount_percent if promo is not None else settings.promo_codes[promo_code].get("discount_percent", 0)
    # Send user back to the product picker, preserving the promo code in
    # subsequent callbacks so it's automatically applied to checkout.
    rows = []
    for p in PRODUCTS:
        rows.append(
            [InlineKeyboardButton(
                text=p["label"],
                callback_data=f"prod:{p['code']}:{promo_code}",
            )]
        )
    rows.append([InlineKeyboardButton(text="« Главное меню", callback_data="u:menu")])
    await message.answer(
        f"✅ Промокод <b>{promo_code}</b> применён. Скидка: <b>{discount}%</b>\n\n"
        "Выберите продукт:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "sub:trial")
async def cb_start_trial(call: CallbackQuery, bot: Bot) -> None:
    await call.answer()
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(call.from_user.id)
        if db_user is None:
            return
        if db_user.trial_used:
            if call.message:
                await call.message.edit_text(
                    "❌ Trial уже был использован ранее.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        # Mark trial as used up-front so concurrent clicks can't double-activate.
        db_user.trial_used = True
        await session.commit()

        xui = XUIClient()
        sub = None
        try:
            sub_service = SubscriptionService(session, xui)
            sub = await sub_service.purchase(
                call.from_user.id,
                "1m",
                idempotency_key=f"trial:{call.from_user.id}",
                is_trial=True,
            )
        except Exception as e:
            logger.error("Trial activation failed: {}", e)
            # Roll back the trial_used flag so user can retry.
            db_user.trial_used = False
            await session.commit()
            if call.message:
                await call.message.edit_text(
                    "❌ Не удалось запустить trial. Попробуйте позже.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        finally:
            await xui.close()

        if sub is not None:
            notif = NotificationService(bot, session)
            await notif.send(
                call.from_user.id,
                "purchase_success",
                expires_at=fmt_date(sub.expires_at),
                price="0",
                balance=str(db_user.balance),
            )

    if call.message:
        await call.message.edit_text(
            f"✅ <b>Trial активирован</b> на {settings.trial_days} дн.\n\nПерейдите в «Мои подписки» или «Мой ключ».",
            parse_mode="HTML",
            reply_markup=subscription_kb(has_active=True),
        )

@router.callback_query(F.data == "u:subs")
async def cb_subscriptions(call: CallbackQuery) -> None:
    await call.answer()
    user = call.from_user
    if user is None:
        return

    async with async_session_factory() as session:
        repo = SubscriptionRepository(session)
        active = await repo.get_active_by_user(user.id)

    if active:
        remaining = days_until(active.expires_at)
        text = (
            "\U0001f511 <b>Мои подписки</b>\n\n"
            f"\U0001f4cb Тариф: <b>{fmt_plan(active.plan_type)}</b>\n"
            f"\U0001f7e2 Статус: {fmt_status(active.status)}\n"
            f"\U0001f4c5 Действует до: {code(fmt_date(active.expires_at))}\n"
            f"\u23f3 Осталось: <b>{pluralize_days(remaining)}</b>\n"
            f"\U0001f4ca Лимит трафика: {fmt_traffic_limit(active.traffic_limit_gb)}\n"
        )
        kb = subscription_kb(has_active=True, is_legacy=not active.sub_id)
    else:
        text = (
            "🔑 <b>Мои подписки</b>\n\n"
            "❌ У вас нет активной подписки.\n"
            "Нажмите «Купить подписку» чтобы начать.\n\n"
            f"🎁 Trial: <b>{'недоступен' if getattr(user, 'trial_used', False) else 'доступен'}</b>"
        )
        kb = subscription_kb(has_active=False)
        if call.message:
            try:
                await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
        return


@router.callback_query(F.data == "u:buy")
async def cb_buy_menu(call: CallbackQuery) -> None:
    """Step 1 of the purchase funnel — product selection.

    The funnel is intentionally the same regardless of whether the user
    already has an active subscription: Product → Region → Plan duration.
    Renewals of an existing subscription live under «Мои подписки» →
    «Продлить» (``sub:renew``), not here.
    """
    await call.answer()
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(call.from_user.id)

    balance = db_user.balance if db_user else 0
    text = (
        "🛒 <b>Купить подписку</b>\n\n"
        f"💰 Ваш баланс: <b>{fmt_rub(balance)}</b>\n\n"
        "Выберите, что хотите приобрести. После выбора продукта вы "
        "сможете указать регион и срок подписки."
    )
    kb = product_select_kb()

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=kb
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=kb
            )


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy_plan(call: CallbackQuery) -> None:
    """Step 4 — show purchase confirmation card.

    Supports two callback layouts:

    * ``buy:<product>:<plan>:<region>[:<promo>]`` — current format
    * ``buy:<plan>:<region>[:<promo>]`` — legacy (assume product=vless)
    """
    await call.answer()
    parts = (call.data or "").split(":")
    product_codes = {p["code"] for p in PRODUCTS}
    if len(parts) >= 4 and parts[1] in product_codes:
        product_code = parts[1]
        plan_type = parts[2]
        region_code = parts[3]
        promo_code = parts[4] if len(parts) > 4 else None
    else:
        product_code = "vless"
        plan_type = parts[1] if len(parts) > 1 else ""
        region_code = parts[2] if len(parts) > 2 else None
        promo_code = parts[3] if len(parts) > 3 else None
    plan = settings.price_with_promo(plan_type, promo_code)
    if not plan:
        return

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(call.from_user.id)
        uc = SubscriptionUseCases(session, XUIClient())
        promo = await uc.resolve_promo(promo_code)
        region = await uc.resolve_region(region_code)

    balance = db_user.balance if db_user else 0
    plan_rub = plan["rub"]
    if promo is not None:
        plan_rub = max(0, round(plan_rub * (100 - promo.discount_percent) / 100))
        plan["stars"] = settings.rub_to_stars(plan_rub)
    region_label = region.label if region is not None else settings.server_regions.get(region_code or "default", {}).get("label", "Автовыбор")
    text = (
        f"🛒 <b>Подтверждение покупки</b>\n\n"
        f"🛍 Продукт: <b>{_product_label(product_code)}</b>\n"
        f"📋 Тариф: <b>{plan['label']}</b>\n"
        f"🌍 Локация: <b>{region_label}</b>\n"
        f"💰 Стоимость: <b>{fmt_price(plan_rub, plan['stars'])}</b>\n"
        f"💎 Ваш баланс: {fmt_rub(balance)}\n"
    )
    if promo_code:
        text += f"🎁 Промокод: <b>{promo_code}</b>\n"
    text += "\n"

    if balance < plan_rub:
        text += (
            "❌ <b>Недостаточно средств!</b>\n"
            f"Необходимо ещё {fmt_rub(plan_rub - balance)}.\n"
            "Пополните баланс."
        )
        if call.message:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=back_to_menu_kb()
            )
        return

    text += "Подтвердите покупку:"
    if call.message:
        try:
            await call.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=confirm_purchase_kb(
                    plan_type,
                    region_code=region_code,
                    promo_code=promo_code,
                    product_code=product_code,
                ),
            )
        except Exception:
            await call.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=confirm_purchase_kb(
                    plan_type,
                    region_code=region_code,
                    promo_code=promo_code,
                    product_code=product_code,
                ),
            )


@router.callback_query(F.data.startswith("confirm_buy:"))
async def cb_confirm_buy(call: CallbackQuery, bot: Bot) -> None:
    """Final step — debit balance and provision the product.

    Supports two callback layouts:

    * ``confirm_buy:<product>:<plan>:<region>[:<promo>]`` — current format
    * ``confirm_buy:<plan>:<region>[:<promo>]`` — legacy (assume product=vless)
    """
    await call.answer()
    parts = (call.data or "").split(":")
    product_codes = {p["code"] for p in PRODUCTS}
    if len(parts) >= 4 and parts[1] in product_codes:
        product_code = parts[1]
        plan_type = parts[2]
        region_code = parts[3]
        promo_code = parts[4] if len(parts) > 4 else None
    else:
        product_code = "vless"
        plan_type = parts[1] if len(parts) > 1 else ""
        region_code = parts[2] if len(parts) > 2 else "default"
        promo_code = parts[3] if len(parts) > 3 else None
    # ``product_code`` reserved for future products (Outline, dedicated IP, ...).
    _ = product_code

    async with async_session_factory() as session:
        xui = XUIClient()
        try:
            uc = SubscriptionUseCases(session, xui)
            promo = await uc.resolve_promo(promo_code)
            region = await uc.resolve_region(region_code)
            sub = await uc.purchase(
                call.from_user.id,
                plan_type,
                idempotency_key=f"purchase:{call.from_user.id}:{plan_type}:{region_code}:{promo_code or 'none'}",
            )
            if sub is not None:
                sub.region_code = region_code
                sub.promo_code = promo_code
                if region is not None:
                    sub.xui_inbound_id = int(region.inbound_id)
                if promo is not None:
                    await uc.promo_repo.increment_usage(promo.id)
                await session.commit()
        except UserFacingError as e:
            if call.message:
                await call.message.edit_text(
                    e.user_message,
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        except ValueError as e:
            logger.warning("Purchase validation failed: {}", e)
            if call.message:
                await call.message.edit_text(
                    "❌ Не удалось оформить подписку. Проверьте параметры и попробуйте снова.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        except Exception as e:
            logger.error("Purchase failed: {}", e)
            if call.message:
                await call.message.edit_text(
                    "❌ Ошибка при оформлении подписки. Попробуйте позже.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        finally:
            await xui.close()

        if sub is None:
            if call.message:
                await call.message.edit_text(
                    "❌ Не удалось оформить подписку.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return

        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(call.from_user.id)
        balance = db_user.balance if db_user else 0

        notif = NotificationService(bot, session)
        await notif.send(
            call.from_user.id,
            "purchase_success",
            expires_at=fmt_date(sub.expires_at),
            price=str(sub.price_rub),
            balance=str(balance),
        )


@router.callback_query(F.data == "sub:renew")
async def cb_renew_menu(call: CallbackQuery) -> None:
    await call.answer()
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(call.from_user.id)

    balance = db_user.balance if db_user else 0
    text = (
        "\U0001f504 <b>Продление подписки</b>\n\n"
        f"\U0001f4b0 Ваш баланс: <b>{fmt_rub(balance)}</b>\n\n"
        "Выберите период продления:"
    )
    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=renew_plan_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=renew_plan_kb()
            )


@router.callback_query(F.data == "sub:renew_quick")
async def cb_quick_renew(call: CallbackQuery, bot: Bot) -> None:
    await call.answer("Продлеваю...")
    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        active = await sub_repo.get_active_by_user(call.from_user.id)
        if active is None:
            if call.message:
                await call.message.edit_text(
                    "❌ Нет активной подписки для быстрого продления.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return

    fake_call = type("RenewCtx", (), {"data": f"renew:{active.plan_type}", "answer": call.answer, "from_user": call.from_user, "message": call.message})
    await cb_renew_plan(fake_call, bot)


@router.callback_query(F.data.startswith("renew:"))
async def cb_renew_plan(call: CallbackQuery, bot: Bot) -> None:
    await call.answer()
    plan_type = call.data.split(":", 1)[1] if call.data else ""

    async with async_session_factory() as session:
        xui = XUIClient()
        try:
            sub_service = SubscriptionService(session, xui)
            sub = await sub_service.renew(
                call.from_user.id,
                plan_type,
                idempotency_key=f"manual-renew:{call.from_user.id}:{plan_type}",
            )
        except UserFacingError as e:
            if call.message:
                await call.message.edit_text(
                    e.user_message,
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        except ValueError as e:
            logger.warning("Renewal validation failed: {}", e)
            if call.message:
                await call.message.edit_text(
                    "❌ Не удалось продлить подписку. Попробуйте ещё раз.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        except Exception as e:
            logger.error("Renewal failed: {}", e)
            if call.message:
                await call.message.edit_text(
                    "\u274c Ошибка при продлении. Попробуйте позже.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        finally:
            await xui.close()

        if sub:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_telegram_id(call.from_user.id)
            balance = db_user.balance if db_user else 0

            notif = NotificationService(bot, session)
            await notif.send(
                call.from_user.id,
                "purchase_success",
                expires_at=fmt_date(sub.expires_at),
                price=str(sub.price_rub),
                balance=str(balance),
            )


@router.callback_query(F.data == "sub:history")
async def cb_sub_history(call: CallbackQuery) -> None:
    await call.answer()

    async with async_session_factory() as session:
        repo = SubscriptionRepository(session)
        subs = await repo.get_user_subscriptions(call.from_user.id, limit=10)

    if not subs:
        text = "\U0001f4dc <b>История подписок</b>\n\nУ вас ещё не было подписок."
    else:
        lines = ["\U0001f4dc <b>История подписок</b>\n"]
        for s in subs:
            lines.append(
                f"• {fmt_plan(s.plan_type)} | {fmt_status(s.status)} | "
                f"{fmt_date(s.starts_at)} — {fmt_date(s.expires_at)}"
            )
        text = "\n".join(lines)

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=back_to_menu_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=back_to_menu_kb()
            )
