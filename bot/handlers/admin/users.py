"""Admin user management handlers."""

from __future__ import annotations

import math

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from loguru import logger

from bot.database.session import async_session_factory
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository
from bot.database.repositories.vpn_key import VpnKeyRepository
from bot.keyboards.admin_kb import (
    admin_user_card_kb,
    admin_users_kb,
    user_list_nav_kb,
)
from bot.middlewares.admin_check import admin_only
from bot.services.admin_use_cases import AdminUseCases
from bot.services.payment import PaymentService
from bot.utils.formatters import code, esc, fmt_date, fmt_plan, fmt_rub
from bot.utils.validators import validate_balance_change

router = Router(name="admin_users")
PAGE_SIZE = 10


class AdminStates(StatesGroup):
    waiting_user_search = State()
    waiting_balance_change = State()
    waiting_user_message = State()


@router.callback_query(F.data == "adm:users")
@admin_only
async def cb_users_menu(call: CallbackQuery) -> None:
    await call.answer()
    if call.message:
        try:
            await call.message.edit_text(
                "\U0001f465 <b>Управление пользователями</b>",
                parse_mode="HTML",
                reply_markup=admin_users_kb(),
            )
        except Exception:
            await call.message.answer(
                "\U0001f465 <b>Управление пользователями</b>",
                parse_mode="HTML",
                reply_markup=admin_users_kb(),
            )


@router.callback_query(F.data == "adm:user_search")
@admin_only
async def cb_user_search(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(AdminStates.waiting_user_search)
    if call.message:
        await call.message.edit_text(
            "\U0001f50d Введите username или Telegram ID пользователя:",
            parse_mode="HTML",
        )


@router.message(AdminStates.waiting_user_search)
@admin_only
async def msg_user_search(message: Message, state: FSMContext) -> None:
    await state.clear()
    query = (message.text or "").strip()
    if not query:
        await message.answer("Пустой запрос.", reply_markup=admin_users_kb())
        return

    async with async_session_factory() as session:
        repo = UserRepository(session)
        users = await repo.search_users(query)

    if not users:
        await message.answer(
            f"\u274c Пользователь не найден: {code(query)}",
            parse_mode="HTML",
            reply_markup=admin_users_kb(),
        )
        return

    if len(users) == 1:
        u = users[0]
        text = await _build_user_card(u.telegram_id)
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=admin_user_card_kb(u.telegram_id),
        )
    else:
        lines = [f"\U0001f50d Найдено {len(users)} пользователей:\n"]
        for u in users[:20]:
            lines.append(
                f"\u2022 {code(u.telegram_id)} | @{esc(u.username or '—')} | "
                f"{fmt_rub(u.balance)}"
            )
        await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data.startswith("adm:user_list:"))
@admin_only
async def cb_user_list(call: CallbackQuery) -> None:
    await call.answer()
    page = int(call.data.split(":")[-1]) if call.data else 0

    async with async_session_factory() as session:
        repo = UserRepository(session)
        total = await repo.count_all()
        users = await repo.get_all_users(offset=page * PAGE_SIZE, limit=PAGE_SIZE)

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    lines = [f"\U0001f4cb <b>Пользователи</b> ({total})\n"]
    for u in users:
        ban_mark = "\U0001f6ab" if u.is_banned else ""
        lines.append(
            f"\u2022 {code(u.telegram_id)} | @{esc(u.username or '—')} | "
            f"{fmt_rub(u.balance)} {ban_mark}"
        )

    if call.message:
        try:
            await call.message.edit_text(
                "\n".join(lines),
                parse_mode="HTML",
                reply_markup=user_list_nav_kb(page, total_pages),
            )
        except Exception:
            await call.message.answer(
                "\n".join(lines),
                parse_mode="HTML",
                reply_markup=user_list_nav_kb(page, total_pages),
            )


@router.callback_query(F.data.startswith("adm:card:"))
@admin_only
async def cb_user_card(call: CallbackQuery) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0
    text = await _build_user_card(tid)
    if call.message:
        try:
            await call.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=admin_user_card_kb(tid),
            )
        except Exception:
            await call.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=admin_user_card_kb(tid),
            )


@router.callback_query(F.data.startswith("adm:bal:"))
@admin_only
async def cb_balance_change(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0
    await state.set_state(AdminStates.waiting_balance_change)
    await state.update_data(target_user=tid)
    if call.message:
        await call.message.edit_text(
            f"\u270f\ufe0f Введите изменение баланса для пользователя {code(tid)}.\n"
            "Положительное число — пополнение, отрицательное — списание.\n\n"
            "Пример: <code>+100</code> или <code>-50</code>",
            parse_mode="HTML",
        )


@router.message(AdminStates.waiting_balance_change)
@admin_only
async def msg_balance_change(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    tid = data.get("target_user")
    if tid is None:
        await message.answer("Ошибка: пользователь не выбран.")
        return

    amount = validate_balance_change(message.text or "")
    if amount is None:
        await message.answer(
            "\u274c Некорректная сумма. Введите число.",
            reply_markup=admin_user_card_kb(tid),
        )
        return

    async with async_session_factory() as session:
        admin_uc = AdminUseCases(session)
        result = await admin_uc.adjust_user_balance(
            admin_id=message.from_user.id if message.from_user else 0,
            user_id=tid,
            amount=amount,
        )

    if result:
        sign = "+" if amount >= 0 else ""
        await message.answer(
            f"✅ Баланс пользователя {code(tid)} изменён на {sign}{amount} ₽.",
            parse_mode="HTML",
            reply_markup=admin_user_card_kb(tid),
        )
    else:
        await message.answer(
            f"\u274c Пользователь {code(tid)} не найден.",
            parse_mode="HTML",
            reply_markup=admin_users_kb(),
        )


@router.callback_query(F.data.startswith("adm:ban:"))
@admin_only
async def cb_toggle_ban(call: CallbackQuery) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(tid)
        if user is None:
            if call.message:
                await call.message.answer("❌ Пользователь не найден.")
            return

        new_status = not user.is_banned
        admin_uc = AdminUseCases(session)
        await admin_uc.toggle_ban(
            admin_id=call.from_user.id,
            user_id=tid,
            is_banned=new_status,
        )

    status_text = "\U0001f6ab заблокирован" if new_status else "\u2705 разблокирован"
    text = await _build_user_card(tid)
    if call.message:
        await call.message.edit_text(
            f"{text}\n\n<b>Статус: {status_text}</b>",
            parse_mode="HTML",
            reply_markup=admin_user_card_kb(tid),
        )


@router.callback_query(F.data.startswith("adm:msg:"))
@admin_only
async def cb_send_user_message(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0
    await state.set_state(AdminStates.waiting_user_message)
    await state.update_data(target_user=tid)
    if call.message:
        await call.message.edit_text(
            f"\U0001f4e8 Введите сообщение для пользователя {code(tid)}:",
            parse_mode="HTML",
        )


@router.message(AdminStates.waiting_user_message)
@admin_only
async def msg_send_user_message(message: Message, bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    tid = data.get("target_user")
    if tid is None:
        await message.answer("Ошибка: пользователь не выбран.")
        return

    text = message.text or ""
    if not text.strip():
        await message.answer("\u274c Пустое сообщение.")
        return

    try:
        await bot.send_message(
            chat_id=tid,
            text=f"\U0001f4e8 <b>Сообщение от администратора:</b>\n\n{esc(text)}",
            parse_mode="HTML",
        )
        await message.answer(
            f"\u2705 Сообщение отправлено пользователю {code(tid)}.",
            parse_mode="HTML",
            reply_markup=admin_user_card_kb(tid),
        )
        async with async_session_factory() as session:
            from bot.services.audit_log import AuditLogService
            from bot.domain_enums import AuditAction
            await AuditLogService(session).log(
                admin_telegram_id=message.from_user.id if message.from_user else 0,
                action=AuditAction.USER_MESSAGE_SENT,
                target_user_id=tid,
            )
            await session.commit()
    except Exception as e:
        logger.error("Failed to send message to user {}: {}", tid, e)
        await message.answer(
            f"\u274c Не удалось отправить сообщение: {esc(str(e))}",
            parse_mode="HTML",
            reply_markup=admin_user_card_kb(tid),
        )


async def _build_user_card(telegram_id: int) -> str:
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return f"\u274c Пользователь {code(telegram_id)} не найден."

        sub_repo = SubscriptionRepository(session)
        active_sub = await sub_repo.get_active_by_user(telegram_id)
        tx_repo = TransactionRepository(session)
        recent_txs = await tx_repo.get_user_history(telegram_id, limit=5)

        key_repo = VpnKeyRepository(session)
        keys = await key_repo.get_user_keys(telegram_id)

    ban_status = "\U0001f6ab Заблокирован" if user.is_banned else "\u2705 Активен"

    lines = [
        "\U0001f464 <b>Карточка пользователя</b>\n",
        f"\U0001f194 ID: {code(user.telegram_id)}",
        f"\U0001f464 Username: @{esc(user.username or '—')}",
        f"\U0001f4dd Имя: {esc(user.first_name or '—')}",
        f"\U0001f4b0 Баланс: <b>{fmt_rub(user.balance)}</b>",
        f"\U0001f7e2 Статус: {ban_status}",
        f"\U0001f4c5 Регистрация: {fmt_date(user.created_at)}",
        f"\U0001f552 Последняя активность: {fmt_date(user.last_active)}",
    ]

    if active_sub:
        lines.append("\n\U0001f511 <b>Активная подписка:</b>")
        lines.append(f"  Тариф: {fmt_plan(active_sub.plan_type)}")
        lines.append(f"  До: {fmt_date(active_sub.expires_at)}")
        lines.append(f"  UUID: {code(active_sub.xui_client_id or '—')}")

    if keys:
        lines.append(f"\n\U0001f511 <b>Ключи ({len(keys)}):</b>")
        for k in keys[:3]:
            status = "\u2705" if k.is_active else "\u274c"
            lines.append(f"  {status} {code(k.xui_client_id[:16])}...")

    if recent_txs:
        lines.append("\n\U0001f4b3 <b>Последние транзакции:</b>")
        for tx in recent_txs[:5]:
            sign = "+" if tx.amount_rub >= 0 else ""
            stars_suffix = f" ({tx.amount_stars}⭐)" if tx.amount_stars is not None else ""
            lines.append(
                f"  {sign}{tx.amount_rub}₽{stars_suffix} | {tx.type} | {fmt_date(tx.created_at)}"
            )


    return "\n".join(lines)
