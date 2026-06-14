"""Admin broadcast (mass messaging) handlers."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.database.session import async_session_factory
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.user import UserRepository
from bot.keyboards.admin_kb import admin_broadcast_kb, admin_main_kb
from bot.middlewares.admin_check import admin_only
from bot.services.notification import NotificationService

router = Router(name="admin_broadcast")


class BroadcastStates(StatesGroup):
    waiting_text = State()


@router.callback_query(F.data == "adm:broadcast")
@admin_only
async def cb_broadcast_menu(call: CallbackQuery) -> None:
    await call.answer()
    if call.message:
        try:
            await call.message.edit_text(
                "\U0001f4e2 <b>Рассылка</b>\n\nВыберите аудиторию:",
                parse_mode="HTML",
                reply_markup=admin_broadcast_kb(),
            )
        except Exception:
            await call.message.answer(
                "\U0001f4e2 <b>Рассылка</b>\n\nВыберите аудиторию:",
                parse_mode="HTML",
                reply_markup=admin_broadcast_kb(),
            )


@router.callback_query(F.data.in_({"adm:bc_all", "adm:bc_active", "adm:bc_expiring"}))
@admin_only
async def cb_broadcast_target(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    target = call.data if call.data else "adm:bc_all"
    await state.set_state(BroadcastStates.waiting_text)
    await state.update_data(broadcast_target=target)

    target_names = {
        "adm:bc_all": "всем пользователям",
        "adm:bc_active": "активным подписчикам",
        "adm:bc_expiring": "с истекающей подпиской (3 дня)",
    }
    name = target_names.get(target, "пользователям")

    if call.message:
        await call.message.edit_text(
            f"\U0001f4e2 Рассылка <b>{name}</b>\n\n"
            "Введите текст сообщения (поддерживается HTML):",
            parse_mode="HTML",
        )


@router.message(BroadcastStates.waiting_text)
@admin_only
async def msg_broadcast_text(message: Message, bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    target = data.get("broadcast_target", "adm:bc_all")
    text = message.text or ""

    if not text.strip():
        await message.answer("\u274c Пустое сообщение. Рассылка отменена.")
        return

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)

        if target == "adm:bc_all":
            telegram_ids = list(await user_repo.get_all_telegram_ids())
        elif target == "adm:bc_active":
            active_subs = await sub_repo.get_all_active()
            telegram_ids = [s.user_id for s in active_subs]
        elif target == "adm:bc_expiring":
            expiring = await sub_repo.get_expiring_soon(3)
            telegram_ids = [s.user_id for s in expiring]
        else:
            telegram_ids = []

        if not telegram_ids:
            await message.answer(
                "\u274c Нет подходящих пользователей для рассылки.",
                reply_markup=admin_main_kb(),
            )
            return

        await message.answer(
            f"\U0001f4e8 Начинаю рассылку {len(telegram_ids)} пользователям..."
        )

        notif = NotificationService(bot, session)
        sent, failed = await notif.broadcast(telegram_ids, text)

    await message.answer(
        f"\u2705 <b>Рассылка завершена</b>\n\n"
        f"\U0001f4e8 Отправлено: {sent}\n"
        f"\u274c Ошибок: {failed}",
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
    )
