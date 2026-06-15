"""Subscription purchase, view, and renewal handlers."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from loguru import logger

from bot.config import settings
from bot.database.session import async_session_factory
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.user import UserRepository
from bot.keyboards.user_kb import (
    back_to_menu_kb,
    buy_plan_kb,
    confirm_purchase_kb,
    renew_plan_kb,
    subscription_kb,
)
from bot.services.notification import NotificationService
from bot.services.subscription import SubscriptionService
from bot.services.xui_client import XUIClient
from bot.utils.formatters import (
    code,
    fmt_date,
    fmt_plan,
    fmt_price,
    fmt_rub,
    fmt_status,
    fmt_traffic_limit,
    days_until,
    pluralize_days,
)

router = Router(name="subscriptions")


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
        kb = subscription_kb(has_active=True)
    else:
        text = (
            "\U0001f511 <b>Мои подписки</b>\n\n"
            "\u274c У вас нет активной подписки.\n"
            "Нажмите «Купить подписку» чтобы начать."
        )
        kb = subscription_kb(has_active=False)

    if call.message:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "u:buy")
async def cb_buy_menu(call: CallbackQuery) -> None:
    await call.answer()
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)
        db_user = await user_repo.get_by_telegram_id(call.from_user.id)
        active = await sub_repo.get_active_by_user(call.from_user.id)

    balance = db_user.balance if db_user else 0

    if active:
        remaining = days_until(active.expires_at)
        text = (
            "\U0001f504 <b>Продление подписки</b>\n\n"
            f"У вас уже есть активная подписка (<b>{fmt_plan(active.plan_type)}</b>, "
            f"осталось <b>{pluralize_days(remaining)}</b>).\n\n"
            f"\U0001f4b0 Ваш баланс: <b>{fmt_rub(balance)}</b>\n\n"
            "Выберите период продления:"
        )
        kb = renew_plan_kb()
    else:
        text = (
            "\U0001f6d2 <b>Купить подписку</b>\n\n"
            f"\U0001f4b0 Ваш баланс: <b>{fmt_rub(balance)}</b>\n\n"
            "Выберите тариф:"
        )
        kb = buy_plan_kb()

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
    await call.answer()
    plan_type = call.data.split(":", 1)[1] if call.data else ""
    plan = settings.plans.get(plan_type)
    if plan is None:
        return

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_telegram_id(call.from_user.id)

    balance = db_user.balance if db_user else 0
    plan_rub = plan["rub"]
    text = (
        f"\U0001f6d2 <b>Подтверждение покупки</b>\n\n"
        f"\U0001f4cb Тариф: <b>{plan['label']}</b>\n"
        f"\U0001f4b0 Стоимость: <b>{fmt_price(plan_rub, plan['stars'])}</b>\n"
        f"\U0001f48e Ваш баланс: {fmt_rub(balance)}\n\n"
    )

    if balance < plan_rub:
        text += (
            "\u274c <b>Недостаточно средств!</b>\n"
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
                reply_markup=confirm_purchase_kb(plan_type),
            )
        except Exception:
            await call.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=confirm_purchase_kb(plan_type),
            )


@router.callback_query(F.data.startswith("confirm_buy:"))
async def cb_confirm_buy(call: CallbackQuery, bot: Bot) -> None:
    await call.answer()
    plan_type = call.data.split(":", 1)[1] if call.data else ""

    async with async_session_factory() as session:
        xui = XUIClient()
        try:
            sub_service = SubscriptionService(session, xui)
            sub = await sub_service.purchase(call.from_user.id, plan_type)
        except ValueError as e:
            if call.message:
                await call.message.edit_text(
                    f"\u274c <b>Ошибка:</b> {str(e)}",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        except Exception as e:
            logger.error("Purchase failed: {}", e)
            if call.message:
                await call.message.edit_text(
                    "\u274c Ошибка при оформлении подписки. Попробуйте позже.",
                    parse_mode="HTML",
                    reply_markup=back_to_menu_kb(),
                )
            return
        finally:
            await xui.close()

        if sub is None:
            if call.message:
                await call.message.edit_text(
                    "\u274c Не удалось оформить подписку.",
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
            price=str(sub.price_stars),
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


@router.callback_query(F.data.startswith("renew:"))
async def cb_renew_plan(call: CallbackQuery, bot: Bot) -> None:
    await call.answer()
    plan_type = call.data.split(":", 1)[1] if call.data else ""

    async with async_session_factory() as session:
        xui = XUIClient()
        try:
            sub_service = SubscriptionService(session, xui)
            sub = await sub_service.renew(call.from_user.id, plan_type)
        except ValueError as e:
            if call.message:
                await call.message.edit_text(
                    f"\u274c <b>Ошибка:</b> {str(e)}",
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
                price=str(sub.price_stars),
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
