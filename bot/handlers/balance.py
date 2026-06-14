"""Balance top-up handlers (Telegram Stars)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from loguru import logger

from bot.keyboards.user_kb import back_to_menu_kb, topup_kb
from bot.utils.validators import validate_topup_amount

router = Router(name="balance")


class TopupStates(StatesGroup):
    waiting_custom_amount = State()


@router.callback_query(F.data == "u:topup")
async def cb_topup_menu(call: CallbackQuery) -> None:
    await call.answer()
    text = (
        "\U0001f4b0 <b>Пополнение баланса</b>\n\n"
        "Выберите сумму пополнения в Telegram Stars:"
    )
    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=topup_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=topup_kb()
            )


@router.callback_query(F.data.startswith("topup:"))
async def cb_topup_amount(call: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    await call.answer()
    amount_str = call.data.split(":", 1)[1] if call.data else ""

    if amount_str == "custom":
        await state.set_state(TopupStates.waiting_custom_amount)
        if call.message:
            await call.message.edit_text(
                "\u270f\ufe0f Введите сумму пополнения в Stars (от 1 до 100000):",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
            )
        return

    amount = validate_topup_amount(amount_str)
    if amount is None:
        return

    await _send_invoice(call, bot, amount)


@router.message(TopupStates.waiting_custom_amount)
async def msg_custom_amount(message: Message, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    amount = validate_topup_amount(message.text or "")
    if amount is None:
        await message.answer(
            "\u274c Некорректная сумма. Введите число от 1 до 100000.",
            reply_markup=back_to_menu_kb(),
        )
        return

    try:
        await bot.send_invoice(
            chat_id=message.chat.id,
            title="Пополнение баланса VPN",
            description=f"Пополнение баланса на {amount} Stars",
            payload=f"topup_{amount}",
            currency="XTR",
            prices=[{"label": "Stars", "amount": amount}],
        )
    except Exception as e:
        logger.error("Failed to send invoice: {}", e)
        await message.answer(
            "\u274c Ошибка создания счёта. Попробуйте позже.",
            reply_markup=back_to_menu_kb(),
        )


async def _send_invoice(call: CallbackQuery, bot: Bot, amount: int) -> None:
    try:
        chat_id = call.message.chat.id if call.message else call.from_user.id
        await bot.send_invoice(
            chat_id=chat_id,
            title="Пополнение баланса VPN",
            description=f"Пополнение баланса на {amount} Stars",
            payload=f"topup_{amount}",
            currency="XTR",
            prices=[{"label": "Stars", "amount": amount}],
        )
    except Exception as e:
        logger.error("Failed to send invoice: {}", e)
        if call.message:
            await call.message.answer(
                "\u274c Ошибка создания счёта. Попробуйте позже.",
                reply_markup=back_to_menu_kb(),
            )
