"""YooKassa payment handlers — create payment + send link to user."""

from __future__ import annotations

import asyncio
import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from bot.config import settings
from bot.keyboards.user_kb import back_to_menu_kb

router = Router(name="yookassa_payment")
YOOKASSA_IDEMPOTENCY_WINDOW_SECONDS = 5 * 60


class YooKassaTopupStates(StatesGroup):
    waiting_amount = State()


def _yookassa_available() -> bool:
    return bool(settings.yookassa_shop_id and settings.yookassa_secret_key)


@router.callback_query(F.data == "topup:yookassa")
async def cb_yookassa_topup(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    if not _yookassa_available():
        if call.message:
            await call.message.edit_text(
                "⚠️ Оплата через ЮKassa временно недоступна.",
                reply_markup=back_to_menu_kb(),
            )
        return

    amounts_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="100 ₽", callback_data="yk_amount:100")],
            [InlineKeyboardButton(text="200 ₽", callback_data="yk_amount:200")],
            [InlineKeyboardButton(text="500 ₽", callback_data="yk_amount:500")],
            [InlineKeyboardButton(text="1000 ₽", callback_data="yk_amount:1000")],
            [InlineKeyboardButton(text="✏️ Ввести свою сумму", callback_data="yk_amount:custom")],
            [InlineKeyboardButton(text="« Назад", callback_data="u:topup")],
        ]
    )
    if call.message:
        await call.message.edit_text(
            "💳 <b>Пополнение через ЮKassa</b>\n\n"
            "Выберите сумму пополнения в рублях:",
            parse_mode="HTML",
            reply_markup=amounts_kb,
        )


@router.callback_query(F.data.startswith("yk_amount:"))
async def cb_yookassa_amount(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    amount_str = call.data.split(":", 1)[1] if call.data else ""

    if amount_str == "custom":
        await state.set_state(YooKassaTopupStates.waiting_amount)
        if call.message:
            await call.message.edit_text(
                "✏️ Введите сумму пополнения в рублях (от 10 до 100000):",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
            )
        return

    try:
        amount = int(amount_str)
    except (ValueError, TypeError):
        return

    if amount < 10 or amount > 100000:
        return

    await _create_yookassa_payment(call, amount)


@router.message(YooKassaTopupStates.waiting_amount)
async def msg_yookassa_custom_amount(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        amount = int(text)
    except (ValueError, TypeError):
        await message.answer(
            "❌ Некорректная сумма. Введите число от 10 до 100000.",
            reply_markup=back_to_menu_kb(),
        )
        return

    if amount < 10 or amount > 100000:
        await message.answer(
            "❌ Сумма должна быть от 10 до 100000 ₽.",
            reply_markup=back_to_menu_kb(),
        )
        return

    await state.clear()
    await _create_yookassa_payment_msg(message, amount)


async def _create_yookassa_payment(call: CallbackQuery, amount_rub: int) -> None:
    """Create YooKassa payment and send link to user via callback."""
    user = call.from_user
    if not user:
        return

    result = await _do_create_payment(user.id, amount_rub)
    if result is None:
        if call.message:
            await call.message.edit_text(
                "❌ Ошибка создания платежа. Попробуйте позже.",
                reply_markup=back_to_menu_kb(),
            )
        return

    payment_url, payment_id = result
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
            [InlineKeyboardButton(text="« Главное меню", callback_data="u:menu")],
        ]
    )
    if call.message:
        await call.message.edit_text(
            f"💳 <b>Платёж создан</b>\n\n"
            f"Сумма: <b>{amount_rub} ₽</b>\n"
            f"Перейдите по ссылке для оплаты.\n\n"
            f"После оплаты баланс пополнится автоматически.",
            parse_mode="HTML",
            reply_markup=kb,
        )


async def _create_yookassa_payment_msg(message: Message, amount_rub: int) -> None:
    """Create YooKassa payment and send link to user via message."""
    user = message.from_user
    if not user:
        return

    result = await _do_create_payment(user.id, amount_rub)
    if result is None:
        await message.answer(
            "❌ Ошибка создания платежа. Попробуйте позже.",
            reply_markup=back_to_menu_kb(),
        )
        return

    payment_url, payment_id = result
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
            [InlineKeyboardButton(text="« Главное меню", callback_data="u:menu")],
        ]
    )
    await message.answer(
        f"💳 <b>Платёж создан</b>\n\n"
        f"Сумма: <b>{amount_rub} ₽</b>\n"
        f"Перейдите по ссылке для оплаты.\n\n"
        f"После оплаты баланс пополнится автоматически.",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def _do_create_payment(telegram_id: int, amount_rub: int) -> tuple[str, str] | None:
    """Create a YooKassa payment. Returns (confirmation_url, payment_id) or None on error."""
    from yookassa import Configuration
    from yookassa import Payment as YKPayment

    Configuration.account_id = settings.yookassa_shop_id
    Configuration.secret_key = settings.yookassa_secret_key

    idempotency_bucket = int(time.time() // YOOKASSA_IDEMPOTENCY_WINDOW_SECONDS)
    idempotency_key = f"yookassa-topup:{telegram_id}:{amount_rub}:{idempotency_bucket}"

    try:
        payment = await asyncio.to_thread(
            YKPayment.create,
            {
                "amount": {
                    "value": f"{amount_rub}.00",
                    "currency": "RUB",
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": settings.yookassa_return_url,
                },
                "capture": True,
                "description": f"Пополнение баланса на {amount_rub} ₽",
                "metadata": {
                    "telegram_id": str(telegram_id),
                    "amount_rub": str(amount_rub),
                    "type": "topup",
                },
            },
            idempotency_key=idempotency_key,
        )
    except Exception as e:
        logger.error("YooKassa payment creation failed: {}", e)
        return None

    if not payment or not payment.confirmation:
        logger.error("YooKassa payment has no confirmation URL")
        return None

    confirmation_url = payment.confirmation.confirmation_url
    payment_id = payment.id
    if not payment_id:
        logger.error("YooKassa payment has no id")
        return None

    # Save pending payment event
    from bot.database.repositories.payment_event import PaymentEventRepository
    from bot.database.session import async_session_factory
    from bot.domain_enums import PaymentStatus

    async with async_session_factory() as session:
        repo = PaymentEventRepository(session)
        existing_event = await repo.get_by_charge_id(payment_id)
        if existing_event is None:
            await repo.create(
                user_id=telegram_id,
                status=PaymentStatus.PENDING,
                amount_stars=0,
                amount_rub=amount_rub,
                charge_id=payment_id,
                payload=f"yookassa:topup:{amount_rub}",
            )

    logger.info(
        "YooKassa payment created: user={} amount={} payment_id={}",
        telegram_id,
        amount_rub,
        payment_id,
    )
    return confirmation_url, payment_id
