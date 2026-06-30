"""Fallback handlers for global user commands and unexpected text."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.user_kb import persistent_menu_kb

router = Router(name="fallback")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Cancel any active FSM flow and show the persistent menu again."""
    await state.clear()
    await message.answer(
        "✅ Действие отменено. Выберите нужный раздел в меню.",
        reply_markup=persistent_menu_kb(),
    )


@router.message(StateFilter(None), F.text)
async def msg_unexpected_text(message: Message) -> None:
    """Explicit response for plain text outside commands/FSM/menu handlers."""
    await message.answer(
        "Не понял сообщение. Откройте нужный раздел через меню ниже или отправьте /start.",
        reply_markup=persistent_menu_kb(),
    )
