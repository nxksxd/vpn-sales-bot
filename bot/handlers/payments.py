"""Telegram Stars payment processing handlers."""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import Message, PreCheckoutQuery
from loguru import logger

from bot.database.session import async_session_factory
from bot.database.repositories.payment_event import PaymentEventRepository
from bot.database.repositories.user import UserRepository
from bot.domain_enums import PaymentStatus
from bot.keyboards.user_kb import main_menu_kb
from bot.services.notification import NotificationService
from bot.services.payment import PaymentService
from bot.utils import metrics
from bot.utils.observability import log_event

router = Router(name="payments")


def _parse_topup_payload(payload: str) -> int:
    prefix, version, amount_str = payload.split(":", 2)
    if prefix != "topup" or version != "v1":
        raise ValueError("unsupported payload version")
    amount = int(amount_str)
    if amount < 1:
        raise ValueError("amount < 1")
    return amount


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout: PreCheckoutQuery) -> None:
    user = pre_checkout.from_user
    payload = pre_checkout.invoice_payload or ""

    try:
        amount = _parse_topup_payload(payload)
    except (ValueError, IndexError):
        await pre_checkout.answer(ok=False, error_message="Некорректный платёжный payload.")
        return

    async with async_session_factory() as session:
        repo = UserRepository(session)
        db_user = await repo.get_by_telegram_id(user.id)

    if db_user is None:
        await pre_checkout.answer(
            ok=False, error_message="Пользователь не зарегистрирован. Отправьте /start."
        )
        return

    if db_user.is_banned:
        await pre_checkout.answer(
            ok=False, error_message="Ваш аккаунт заблокирован."
        )
        return

    await pre_checkout.answer(ok=True)
    logger.info(
        "Pre-checkout approved: user={} amount_stars={}", user.id, amount
    )


@router.message(lambda msg: msg.successful_payment is not None)
async def successful_payment_handler(message: Message, bot: Bot) -> None:
    payment = message.successful_payment
    if payment is None:
        return

    user = message.from_user
    if user is None:
        return

    payload = payment.invoice_payload or ""
    charge_id = payment.telegram_payment_charge_id or ""

    try:
        amount_stars = _parse_topup_payload(payload)
    except (ValueError, IndexError):
        logger.error("Invalid payment payload: {}", payload)
        return

    if payment.currency != "XTR":
        logger.error(
            "Unexpected payment currency: user={} currency={} payload={}",
            user.id,
            payment.currency,
            payload,
        )
        return

    if payment.total_amount != amount_stars:
        logger.error(
            "Payment amount mismatch: user={} payload_stars={} total_amount={} charge_id={}",
            user.id,
            amount_stars,
            payment.total_amount,
            charge_id,
        )
        return

    if not charge_id:
        logger.error("Missing Telegram charge_id for user={} payload={}", user.id, payload)
        return

    async with async_session_factory() as session:
        payment_events = PaymentEventRepository(session)
        payment_service = PaymentService(session)
        rub_amount = payment_service.user_repo and __import__("bot.config", fromlist=["settings"]).settings.stars_to_rub(amount_stars)
        await payment_events.create(
            user_id=user.id,
            status=PaymentStatus.PENDING,
            amount_stars=amount_stars,
            amount_rub=rub_amount,
            charge_id=charge_id,
            payload=payload,
        )
        rub_credited = await payment_service.process_topup(
            telegram_id=user.id,
            amount_stars=amount_stars,
            charge_id=charge_id,
        )

        if rub_credited > 0:
            await payment_events.update_status(charge_id, PaymentStatus.PAID)
            metrics.inc(metrics.PAYMENTS_SUCCEEDED)
        else:
            await payment_events.update_status(
                charge_id,
                PaymentStatus.FAILED,
                error_message="duplicate_charge",
            )
            metrics.inc(metrics.PAYMENTS_FAILED)

        if rub_credited == 0:
            await message.answer(
                "⚠️ Платёж уже был обработан ранее.",
                reply_markup=main_menu_kb(),
            )
            return

        repo = UserRepository(session)
        db_user = await repo.get_by_telegram_id(user.id)
        new_balance = db_user.balance if db_user else rub_credited

        notif = NotificationService(bot, session)
        await notif.send(
            user.id,
            "balance_topped_up",
            amount=str(rub_credited),
            stars=str(amount_stars),
            balance=str(new_balance),
        )

    logger.info(
        "Payment successful: user={} amount_stars={} charge_id={}",
        user.id,
        amount_stars,
        charge_id,
    )
    log_event(
        "payment_processed",
        user_id=user.id,
        amount_stars=amount_stars,
        charge_id=charge_id,
        status="paid",
    )
