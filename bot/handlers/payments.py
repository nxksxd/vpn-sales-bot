"""Telegram Stars payment processing handlers."""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import Message, PreCheckoutQuery
from loguru import logger

from bot.database.session import async_session_factory
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
        payment_service = PaymentService(session)
        validation_error = await payment_service.validate_telegram_topup_allowed(user.id)

    if validation_error is not None:
        await pre_checkout.answer(ok=False, error_message=validation_error)
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
        payment_service = PaymentService(session)
        rub_credited = await payment_service.process_telegram_successful_topup(
            telegram_id=user.id,
            amount_stars=amount_stars,
            charge_id=charge_id,
            payload=payload,
        )

        if rub_credited > 0:
            metrics.inc(metrics.PAYMENTS_SUCCEEDED)
        else:
            metrics.inc(metrics.PAYMENTS_FAILED)
            await message.answer(
                "⚠️ Платёж уже был обработан ранее.",
                reply_markup=main_menu_kb(),
            )
            return

        new_balance = await payment_service.get_user_balance_or_default(
            user.id, rub_credited
        )

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
