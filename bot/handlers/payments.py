"""Telegram Stars payment processing handlers."""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import Message, PreCheckoutQuery
from loguru import logger

from bot.database.session import async_session_factory
from bot.database.repositories.user import UserRepository
from bot.keyboards.user_kb import main_menu_kb
from bot.services.notification import NotificationService
from bot.services.payment import PaymentService

router = Router(name="payments")


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout: PreCheckoutQuery) -> None:
    user = pre_checkout.from_user
    payload = pre_checkout.invoice_payload or ""

    if not payload.startswith("topup_"):
        await pre_checkout.answer(ok=False, error_message="Неизвестный тип платежа.")
        return

    try:
        amount = int(payload.split("_", 1)[1])
        if amount < 1:
            raise ValueError("amount < 1")
    except (ValueError, IndexError):
        await pre_checkout.answer(ok=False, error_message="Некорректная сумма.")
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
        "Pre-checkout approved: user={} amount={}", user.id, amount
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

    if not payload.startswith("topup_"):
        logger.warning("Unknown payment payload: {}", payload)
        return

    try:
        amount = int(payload.split("_", 1)[1])
    except (ValueError, IndexError):
        logger.error("Invalid payment payload: {}", payload)
        return

    async with async_session_factory() as session:
        payment_service = PaymentService(session)
        success = await payment_service.process_topup(
            telegram_id=user.id,
            amount=amount,
            charge_id=charge_id,
        )

        if not success:
            await message.answer(
                "\u26a0\ufe0f Платёж уже был обработан ранее.",
                reply_markup=main_menu_kb(),
            )
            return

        repo = UserRepository(session)
        db_user = await repo.get_by_telegram_id(user.id)
        new_balance = db_user.balance if db_user else amount

        notif = NotificationService(bot, session)
        await notif.send(
            user.id,
            "balance_topped_up",
            amount=str(amount),
            balance=str(new_balance),
        )

    logger.info(
        "Payment successful: user={} amount={} charge_id={}",
        user.id,
        amount,
        charge_id,
    )
