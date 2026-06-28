"""Admin promo code management: list, create, toggle, delete."""

from __future__ import annotations

import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.database.repositories.promo_code import PromoCodeRepository
from bot.database.session import async_session_factory
from bot.domain_enums import AuditAction
from bot.middlewares.admin_check import admin_only, is_admin
from bot.services.audit_log import AuditLogService
from bot.utils.formatters import code, esc

router = Router(name="admin_promo")


class PromoStates(StatesGroup):
    waiting_code = State()
    waiting_discount = State()
    waiting_limit = State()
    waiting_valid_until = State()


# ── Keyboards ─────────────────────────────────────────────────────


def _promo_list_kb(promos: list, show_inactive: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for promo in promos:
        status = "✅" if promo.is_active else "❌"
        rows.append([
            InlineKeyboardButton(
                text=f"{status} {promo.code} ({promo.discount_percent}%)",
                callback_data=f"adm:promo_card:{promo.id}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="➕ Создать промокод",
            callback_data="adm:promo_create",
        )
    ])
    toggle_text = "📋 Только активные" if show_inactive else "📋 Показать все"
    toggle_cb = "adm:promos" if show_inactive else "adm:promos_all"
    rows.append([InlineKeyboardButton(text=toggle_text, callback_data=toggle_cb)])
    rows.append([InlineKeyboardButton(text="« Настройки", callback_data="adm:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _promo_card_kb(promo_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "⏸ Деактивировать" if is_active else "▶️ Активировать"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=f"adm:promo_toggle:{promo_id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:promo_del:{promo_id}")],
            [InlineKeyboardButton(text="« Промокоды", callback_data="adm:promos")],
        ]
    )


# ── List promos ───────────────────────────────────────────────────


@router.callback_query(F.data == "adm:promos")
@admin_only
async def cb_promo_list(call: CallbackQuery) -> None:
    await call.answer()
    async with async_session_factory() as session:
        repo = PromoCodeRepository(session)
        promos = list(await repo.get_all_active())

    if not promos:
        text = "🎁 <b>Промокоды</b>\n\nАктивных промокодов нет."
    else:
        lines = ["🎁 <b>Промокоды</b>\n"]
        for p in promos:
            limit = p.usage_limit if p.usage_limit is not None else "∞"
            valid = f" | до {p.valid_until:%d.%m.%Y}" if p.valid_until else ""
            lines.append(
                f"• {code(p.code)} — {p.discount_percent}% | "
                f"использовано: {p.used_count}/{limit}{valid}"
            )
        text = "\n".join(lines)

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=_promo_list_kb(promos)
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=_promo_list_kb(promos)
            )


@router.callback_query(F.data == "adm:promos_all")
@admin_only
async def cb_promo_list_all(call: CallbackQuery) -> None:
    await call.answer()
    async with async_session_factory() as session:
        repo = PromoCodeRepository(session)
        promos = list(await repo.list_all())

    if not promos:
        text = "🎁 <b>Промокоды</b>\n\nПромокодов нет."
    else:
        lines = ["🎁 <b>Все промокоды</b>\n"]
        for p in promos:
            status = "✅" if p.is_active else "❌"
            limit = p.usage_limit if p.usage_limit is not None else "∞"
            valid = f" | до {p.valid_until:%d.%m.%Y}" if p.valid_until else ""
            lines.append(
                f"• {status} {code(p.code)} — {p.discount_percent}% | "
                f"{p.used_count}/{limit}{valid}"
            )
        text = "\n".join(lines)

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML",
                reply_markup=_promo_list_kb(promos, show_inactive=True),
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML",
                reply_markup=_promo_list_kb(promos, show_inactive=True),
            )


# ── Promo card ────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("adm:promo_card:"))
@admin_only
async def cb_promo_card(call: CallbackQuery) -> None:
    await call.answer()
    promo_id = int(call.data.split(":")[-1]) if call.data else 0

    async with async_session_factory() as session:
        repo = PromoCodeRepository(session)
        promo = await repo.get_by_id(promo_id)

    if promo is None:
        if call.message:
            await call.message.edit_text(
                "❌ Промокод не найден.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="« Промокоды", callback_data="adm:promos")]
                ]),
            )
        return

    status = "✅ Активен" if promo.is_active else "❌ Неактивен"
    limit = promo.usage_limit if promo.usage_limit is not None else "∞"
    valid = (
        f"\n📅 Действует до: <b>{promo.valid_until:%d.%m.%Y %H:%M}</b>"
        if promo.valid_until
        else ""
    )
    created = f"{promo.created_at:%d.%m.%Y %H:%M}" if promo.created_at else "—"

    text = (
        f"🎁 <b>Промокод: {code(promo.code)}</b>\n\n"
        f"📊 Статус: {status}\n"
        f"💰 Скидка: <b>{promo.discount_percent}%</b>\n"
        f"👥 Использовано: <b>{promo.used_count}/{limit}</b>\n"
        f"📅 Создан: {created}{valid}"
    )

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML",
                reply_markup=_promo_card_kb(promo.id, promo.is_active),
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML",
                reply_markup=_promo_card_kb(promo.id, promo.is_active),
            )


# ── Create promo ──────────────────────────────────────────────────


@router.callback_query(F.data == "adm:promo_create")
@admin_only
async def cb_promo_create_start(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(PromoStates.waiting_code)
    if call.message:
        await call.message.edit_text(
            "➕ <b>Создание промокода</b>\n\n"
            "Введите код промокода (латиница, цифры, до 50 символов).\n"
            "Или отправьте /cancel для отмены.",
            parse_mode="HTML",
        )


@router.message(PromoStates.waiting_code, F.text == "/cancel")
@router.message(PromoStates.waiting_discount, F.text == "/cancel")
@router.message(PromoStates.waiting_limit, F.text == "/cancel")
@router.message(PromoStates.waiting_valid_until, F.text == "/cancel")
async def cancel_promo_create(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "❌ Создание промокода отменено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Промокоды", callback_data="adm:promos")]
        ]),
    )


@router.message(PromoStates.waiting_code)
async def msg_promo_code(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        return
    promo_code = (message.text or "").strip().upper()
    if not promo_code or len(promo_code) > 50:
        await message.answer("❌ Код должен быть от 1 до 50 символов. Попробуйте ещё раз:")
        return
    if not promo_code.replace("_", "").replace("-", "").isalnum():
        await message.answer(
            "❌ Код может содержать только "
            "буквы, цифры, _ и -."
        )
        return

    async with async_session_factory() as session:
        repo = PromoCodeRepository(session)
        existing = await repo.get_by_code(promo_code)
        if existing:
            await message.answer(
                f"❌ Промокод {code(promo_code)} уже существует. "
                "Введите другой:",
                parse_mode="HTML",
            )
            return

    await state.update_data(promo_code=promo_code)
    await state.set_state(PromoStates.waiting_discount)
    await message.answer(
        f"Код: <b>{esc(promo_code)}</b>\n\n"
        "Введите процент скидки (1–100):",
        parse_mode="HTML",
    )


@router.message(PromoStates.waiting_discount)
async def msg_promo_discount(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        return
    try:
        discount = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Введите число от 1 до 100:")
        return
    if discount < 1 or discount > 100:
        await message.answer("❌ Скидка должна быть от 1 до 100%. Попробуйте ещё раз:")
        return

    await state.update_data(discount=discount)
    await state.set_state(PromoStates.waiting_limit)
    await message.answer(
        f"Скидка: <b>{discount}%</b>\n\n"
        "Введите лимит использований (число) или <b>0</b> для безлимита:",
        parse_mode="HTML",
    )


@router.message(PromoStates.waiting_limit)
async def msg_promo_limit(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        return
    try:
        limit = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Введите целое число (0 = безлимит):")
        return
    if limit < 0:
        await message.answer("❌ Лимит не может быть отрицательным:")
        return

    await state.update_data(usage_limit=limit if limit > 0 else None)
    await state.set_state(PromoStates.waiting_valid_until)
    await message.answer(
        f"Лимит: <b>{'∞' if limit == 0 else limit}</b>\n\n"
        "Введите дату окончания действия в формате <b>ДД.ММ.ГГГГ</b>\n"
        "или <b>0</b> для бессрочного промокода:",
        parse_mode="HTML",
    )


@router.message(PromoStates.waiting_valid_until)
async def msg_promo_valid_until(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()

    valid_until: datetime.datetime | None = None
    if text != "0":
        try:
            valid_until = datetime.datetime.strptime(text, "%d.%m.%Y").replace(
                hour=23, minute=59, second=59
            )
        except ValueError:
            await message.answer("❌ Неверный формат. Введите дату как ДД.ММ.ГГГГ или 0:")
            return
        if valid_until <= datetime.datetime.utcnow():
            await message.answer("❌ Дата должна быть в будущем. Попробуйте ещё раз:")
            return

    data = await state.get_data()
    await state.clear()

    promo_code = data.get("promo_code", "")
    discount = data.get("discount", 0)
    usage_limit = data.get("usage_limit")

    async with async_session_factory() as session:
        repo = PromoCodeRepository(session)
        promo = await repo.create(
            code=promo_code,
            discount_percent=discount,
            usage_limit=usage_limit,
            valid_until=valid_until,
        )
        await AuditLogService(session).log(
            admin_telegram_id=message.from_user.id,
            action=AuditAction.SETTINGS_CHANGED,
            details=f"promo_created: {promo.code} discount={promo.discount_percent}%",
        )

    limit_text = usage_limit if usage_limit is not None else "∞"
    valid_text = f"\n📅 До: {valid_until:%d.%m.%Y}" if valid_until else "\n📅 Бессрочный"
    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"🎁 Код: {code(promo.code)}\n"
        f"💰 Скидка: <b>{promo.discount_percent}%</b>\n"
        f"👥 Лимит: <b>{limit_text}</b>{valid_text}",
        parse_mode="HTML",
        reply_markup=_promo_card_kb(promo.id, promo.is_active),
    )


# ── Toggle active ─────────────────────────────────────────────────


@router.callback_query(F.data.startswith("adm:promo_toggle:"))
@admin_only
async def cb_promo_toggle(call: CallbackQuery) -> None:
    await call.answer()
    promo_id = int(call.data.split(":")[-1]) if call.data else 0

    async with async_session_factory() as session:
        repo = PromoCodeRepository(session)
        promo = await repo.get_by_id(promo_id)
        if promo is None:
            if call.message:
                await call.message.edit_text("❌ Промокод не найден.")
            return
        new_active = not promo.is_active
        await repo.set_active(promo_id, new_active)

        await AuditLogService(session).log(
            admin_telegram_id=call.from_user.id if call.from_user else 0,
            action=AuditAction.SETTINGS_CHANGED,
            details=f"promo {'activated' if new_active else 'deactivated'}: {promo.code}",
        )

    status = "✅ активирован" if new_active else "❌ деактивирован"
    text = f"Промокод {code(promo.code)} {status}."
    if call.message:
        await call.message.edit_text(
            text, parse_mode="HTML",
            reply_markup=_promo_card_kb(promo_id, new_active),
        )


# ── Delete promo ──────────────────────────────────────────────────


@router.callback_query(F.data.startswith("adm:promo_del:"))
@admin_only
async def cb_promo_delete(call: CallbackQuery) -> None:
    await call.answer()
    promo_id = int(call.data.split(":")[-1]) if call.data else 0

    async with async_session_factory() as session:
        repo = PromoCodeRepository(session)
        promo = await repo.get_by_id(promo_id)
        promo_code_str = promo.code if promo else "?"
        deleted = await repo.delete(promo_id)

        if deleted:
            await AuditLogService(session).log(
                admin_telegram_id=call.from_user.id if call.from_user else 0,
                action=AuditAction.SETTINGS_CHANGED,
                details=f"promo_deleted: {promo_code_str}",
            )

    if deleted:
        text = f"🗑 Промокод {code(promo_code_str)} удалён."
    else:
        text = "❌ Промокод не найден."

    if call.message:
        await call.message.edit_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="« Промокоды", callback_data="adm:promos")]
            ]),
        )
