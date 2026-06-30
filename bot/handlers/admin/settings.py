"""Admin settings, server status, and 3x-ui connection management."""

from __future__ import annotations

import html
import re
import shlex

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from loguru import logger

from bot.config import settings, BASE_DIR
from bot.keyboards.admin_kb import admin_main_kb, admin_xui_settings_kb
from bot.middlewares.admin_check import admin_only, is_admin
from bot.domain_enums import AuditAction
from bot.services.admin_catalog import AdminCatalogService
from bot.services.admin_keys import AdminKeyService
from bot.services.audit_log import AuditLogService
from bot.services.xui_client import XUIClient
from bot.utils.formatters import code

router = Router(name="admin_settings")


class XuiSettingsStates(StatesGroup):
    waiting_value = State()


async def _safe_edit_text(message: Message, text: str, **kwargs) -> None:
    """edit_text wrapper that silently ignores 'message is not modified'."""
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        raise


# ── Helpers ────────────────────────────────────────────────────────

_XUI_FIELDS = {
    "xui_url": ("XUI_URL", "URL панели 3x-ui"),
    "xui_username": ("XUI_USERNAME", "Логин 3x-ui"),
    "xui_password": ("XUI_PASSWORD", "Пароль 3x-ui"),
    "xui_inbound_id": ("XUI_INBOUND_ID", "Inbound ID"),
    "server_address": ("SERVER_ADDRESS", "Адрес сервера (IP/домен)"),
}


def _env_line(env_key: str, value: str) -> str:
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValueError("Значение не должно содержать переносы строк или NUL")
    return f"{env_key}={shlex.quote(value)}\n"


def _update_env_file(env_key: str, value: str) -> None:
    """Update a key in the .env file (create if missing)."""
    env_path = BASE_DIR / ".env"
    lines: list[str] = []
    found = False
    replacement = _env_line(env_key, value)

    if env_path.exists():
        lines = env_path.read_text().splitlines(keepends=True)
        new_lines: list[str] = []
        for line in lines:
            if re.match(rf"^{re.escape(env_key)}\s*=", line):
                new_lines.append(replacement)
                found = True
            else:
                new_lines.append(line)
        lines = new_lines

    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append(replacement)

    env_path.write_text("".join(lines))


def _apply_setting(field: str, value: str) -> None:
    """Apply a setting to the running config and persist to .env."""
    env_key = _XUI_FIELDS[field][0]
    if field == "xui_inbound_id":
        int_val = int(value)
        settings.xui_inbound_id = int_val
        _update_env_file(env_key, value)
    else:
        setattr(settings, field, value)
        _update_env_file(env_key, value)


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


# ── Settings menu ─────────────────────────────────────────────────

@router.callback_query(F.data == "adm:settings")
@admin_only
async def cb_settings(call: CallbackQuery) -> None:
    await call.answer()

    plans = settings.plans
    plan_lines = []
    for key, plan in plans.items():
        discount = f" (-{plan['discount']}%)" if plan['discount'] > 0 else ""
        plan_lines.append(
            f"  {plan['label']}: {plan['rub']} \u20bd ({plan['stars']} \u2b50){discount}"
        )

    text = (
        "\u2699\ufe0f <b>Настройки бота</b>\n\n"
        f"\U0001f4e1 <b>3x-ui панель:</b>\n"
        f"  URL: {code(settings.xui_url)}\n"
        f"  Логин: {code(settings.xui_username)}\n"
        f"  Пароль: {code(_mask(settings.xui_password))}\n"
        f"  Inbound ID: {code(settings.xui_inbound_id)}\n"
        f"  Адрес сервера: {code(settings.server_address or '—')}\n\n"
        f"\U0001f4b0 <b>Тарифы:</b>\n"
        + "\n".join(plan_lines) + "\n\n"
        f"\U0001f4b1 <b>Курс:</b> 1 \u2b50 = {settings.stars_to_rub_rate} \u20bd\n\n"
        f"\U0001f4ca <b>Трафик:</b>\n"
        f"  Лимит: {settings.traffic_limit_gb} GB"
        f" ({'безлимит' if settings.traffic_limit_gb == 0 else ''})\n\n"
        f"\U0001f381 <b>Реферальный бонус:</b> {settings.referral_bonus_rub} \u20bd\n"
        f"\U0001f514 <b>Напоминания:</b> за {settings.notify_before_days} дней"
    )

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=admin_xui_settings_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=admin_xui_settings_kb()
            )


# ── Edit 3x-ui fields ─────────────────────────────────────────────

@router.callback_query(F.data.in_({f"adm:set:{f}" for f in _XUI_FIELDS}))
@admin_only
async def cb_edit_xui_field(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    field = (call.data or "").split("adm:set:", 1)[1]
    _, label = _XUI_FIELDS[field]

    current = getattr(settings, field, "")
    if field == "xui_password":
        display = _mask(str(current))
    else:
        display = str(current) or "—"

    await state.set_state(XuiSettingsStates.waiting_value)
    await state.update_data(field=field)

    text = (
        f"\u270f\ufe0f <b>{label}</b>\n\n"
        f"Текущее значение: {code(display)}\n\n"
        "Отправьте новое значение или /cancel для отмены:"
    )
    if call.message:
        try:
            await call.message.edit_text(text, parse_mode="HTML")
        except Exception:
            await call.message.answer(text, parse_mode="HTML")


@router.message(XuiSettingsStates.waiting_value, F.text == "/cancel")
async def cancel_edit(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "\u274c Отменено.",
        parse_mode="HTML",
        reply_markup=admin_xui_settings_kb(),
    )


@router.message(XuiSettingsStates.waiting_value)
async def receive_xui_value(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    field = data.get("field", "")
    if field not in _XUI_FIELDS:
        await state.clear()
        return

    value = (message.text or "").strip()
    if not value:
        await message.answer("\u274c Значение не может быть пустым. Попробуйте ещё раз:")
        return

    _, label = _XUI_FIELDS[field]

    if field == "xui_inbound_id":
        try:
            int(value)
        except ValueError:
            await message.answer("\u274c Inbound ID должен быть числом. Попробуйте ещё раз:")
            return

    try:
        _apply_setting(field, value)
    except Exception as e:
        logger.error("Failed to apply setting {}={}: {}", field, value, e)
        await message.answer(
            f"\u274c Ошибка при сохранении: {html.escape(str(e))}",
            parse_mode="HTML",
        )
        return

    await state.clear()

    if field == "xui_password":
        display = _mask(value)
    else:
        display = value

    await message.answer(
        f"✅ <b>{label}</b> обновлён: {code(display)}\n\n"
        "Изменение применено без перезапуска бота.",
        parse_mode="HTML",
        reply_markup=admin_xui_settings_kb(),
    )
    async with __import__("bot.database.session", fromlist=["async_session_factory"]).async_session_factory() as session:
        audit = AuditLogService(session)
        await audit.log(
            message.from_user.id,
            AuditAction.SETTINGS_CHANGED,
            details=f"field={field};value={display if field != 'xui_password' else '***'}",
        )
    logger.info("Admin {} changed {} to {}", message.from_user.id, field,
                display if field != "xui_password" else "***")


# ── Test connection ────────────────────────────────────────────────

@router.callback_query(F.data == "adm:regions")
@admin_only
async def cb_regions_settings(call: CallbackQuery) -> None:
    await call.answer()
    async with __import__("bot.database.session", fromlist=["async_session_factory"]).async_session_factory() as session:
        regions = await AdminCatalogService(session).get_regions()

    if not regions:
        text = "🌍 <b>Регионы серверов</b>\n\nЗаписей пока нет."
    else:
        lines = ["🌍 <b>Регионы серверов</b>\n"]
        for region in regions:
            lines.append(
                f"• {code(region.code)} | {region.label} | {region.server_address} | inbound={region.inbound_id}"
            )
        text = "\n".join(lines)

    if call.message:
        await _safe_edit_text(call.message, text, parse_mode="HTML", reply_markup=admin_xui_settings_kb())


@router.callback_query(F.data == "adm:set:test")
@admin_only
async def cb_test_xui_connection(call: CallbackQuery) -> None:
    await call.answer("\U0001f50d Проверяю подключение...")

    xui = XUIClient()
    try:
        ping_ok = await xui.ping()
        if ping_ok:
            inbounds = await xui.get_inbounds()
            text = (
                "\u2705 <b>Подключение успешно!</b>\n\n"
                f"\U0001f4e1 URL: {code(settings.xui_url)}\n"
                f"\U0001f464 Логин: {code(settings.xui_username)}\n"
                f"\U0001f4cb Inbounds: <b>{len(inbounds)}</b>\n"
            )
            for ib in inbounds:
                text += (
                    f"\n  #{ib.get('id')} — {ib.get('remark', '?')} "
                    f"({ib.get('protocol', '?')}, port {ib.get('port', '?')})"
                )
        else:
            text = (
                "\u274c <b>Не удалось подключиться</b>\n\n"
                f"\U0001f4e1 URL: {code(settings.xui_url)}\n\n"
                "Проверьте URL, логин и пароль."
            )
    except Exception as e:
        text = (
            f"\u274c <b>Ошибка подключения:</b>\n"
            f"{code(str(e)[:200])}\n\n"
            "Проверьте настройки 3x-ui."
        )
    finally:
        await xui.close()

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=admin_xui_settings_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=admin_xui_settings_kb()
            )


@router.callback_query(F.data == "adm:server")
@admin_only
async def cb_server_status(call: CallbackQuery) -> None:
    await call.answer()

    xui = XUIClient()
    try:
        ping_ok = await xui.ping()

        client_count = 0
        if ping_ok:
            try:
                inbounds = await xui.get_inbounds()
                for ib in inbounds:
                    settings_raw = ib.get("settings", "{}")
                    if isinstance(settings_raw, str):
                        import json
                        try:
                            s = json.loads(settings_raw)
                        except ValueError:
                            s = {}
                    else:
                        s = settings_raw
                    clients = s.get("clients", [])
                    client_count += len(clients)
            except Exception as e:
                logger.error("Failed to count clients: {}", e)

        onlines = []
        if ping_ok:
            try:
                onlines = await xui.get_onlines()
            except Exception:
                pass

        status_icon = "\u2705" if ping_ok else "\u274c"
        text = (
            "\U0001f5a5 <b>Статус сервера</b>\n\n"
            f"\U0001f4e1 3x-ui: {status_icon} {'OK' if ping_ok else 'Недоступен'}\n"
            f"  URL: {code(settings.xui_url)}\n\n"
        )
        if ping_ok:
            text += (
                f"\U0001f465 Клиентов в панели: <b>{client_count}</b>\n"
                f"\U0001f7e2 Онлайн: <b>{len(onlines)}</b>\n"
            )
    finally:
        await xui.close()

    if call.message:
        try:
            await call.message.edit_text(
                text, parse_mode="HTML", reply_markup=admin_main_kb()
            )
        except Exception:
            await call.message.answer(
                text, parse_mode="HTML", reply_markup=admin_main_kb()
            )


@router.callback_query(F.data.startswith("adm:sub:"))
@admin_only
async def cb_admin_subscription(call: CallbackQuery) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0

    from bot.keyboards.admin_kb import admin_sub_actions_kb
    from bot.utils.formatters import fmt_date, fmt_plan, fmt_status, days_until, pluralize_days

    async with __import__("bot.database.session", fromlist=["async_session_factory"]).async_session_factory() as session:
        active = await AdminKeyService(session).get_active_subscription(tid)

    if active is None:
        text = f"\U0001f4c5 У пользователя {code(tid)} нет активной подписки."
    else:
        remaining = days_until(active.expires_at)
        text = (
            f"\U0001f4c5 <b>Подписка пользователя {code(tid)}</b>\n\n"
            f"Тариф: {fmt_plan(active.plan_type)}\n"
            f"Статус: {fmt_status(active.status)}\n"
            f"Начало: {fmt_date(active.starts_at)}\n"
            f"Окончание: {fmt_date(active.expires_at)}\n"
            f"Осталось: {pluralize_days(remaining)}\n"
            f"UUID: {code(active.xui_client_id or '—')}"
        )

    if call.message:
        try:
            await call.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=admin_sub_actions_kb(tid),
            )
        except Exception:
            await call.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=admin_sub_actions_kb(tid),
            )


@router.callback_query(F.data.regexp(r"^adm:ext:\d+:\d+$"))
@admin_only
async def cb_extend_subscription(call: CallbackQuery) -> None:
    await call.answer()
    parts = call.data.split(":") if call.data else []
    days = int(parts[2])
    tid = int(parts[3])

    from bot.database.session import async_session_factory
    from bot.database.repositories.subscription import SubscriptionRepository
    from bot.keyboards.admin_kb import admin_sub_actions_kb
    from bot.utils.formatters import pluralize_days

    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        active = await sub_repo.get_active_by_user(tid)
        if active is None:
            if call.message:
                await call.message.answer(
                    f"\u274c Нет активной подписки у {code(tid)}.",
                    parse_mode="HTML",
                )
            return

        xui = XUIClient()
        try:
            sub = await sub_repo.extend(active.id, days)

            if sub and sub.xui_client_id:
                new_expiry_ms = int(sub.expires_at.timestamp() * 1000)
                from bot.database.repositories.vpn_key import VpnKeyRepository
                key_repo = VpnKeyRepository(session)
                key = await key_repo.get_by_client_id(sub.xui_client_id)
                email = key.email if key else f"user_{tid}"
                try:
                    await xui.update_client(
                        sub.xui_inbound_id or settings.xui_inbound_id,
                        sub.xui_client_id,
                        {
                            "id": sub.xui_client_id,
                            "email": email,
                            "enable": True,
                            "expiryTime": new_expiry_ms,
                        },
                    )
                except Exception as e:
                    logger.error("Failed to update 3X-UI expiry: {}", e)
        finally:
            await xui.close()

        from bot.services.audit_log import AuditLogService
        from bot.domain_enums import AuditAction
        await AuditLogService(session).log(
            admin_telegram_id=call.from_user.id if call.from_user else 0,
            action=AuditAction.SUBSCRIPTION_EXTENDED,
            target_user_id=tid,
            details=f"+{days}d",
        )
        await session.commit()

    if call.message:
        await call.message.edit_text(
            f"\u2705 Подписка продлена на {pluralize_days(days)} "
            f"для пользователя {code(tid)}.",
            parse_mode="HTML",
            reply_markup=admin_sub_actions_kb(tid),
        )


@router.callback_query(F.data.startswith("adm:cancel_sub:"))
@admin_only
async def cb_cancel_subscription(call: CallbackQuery) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0

    from bot.keyboards.admin_kb import admin_user_card_kb

    async with __import__("bot.database.session", fromlist=["async_session_factory"]).async_session_factory() as session:
        active = await AdminKeyService(session).get_active_subscription(tid)
        if active is None:
            if call.message:
                await call.message.answer(
                    f"\u274c Нет активной подписки у {code(tid)}.",
                    parse_mode="HTML",
                )
            return

        xui = XUIClient()
        try:
            from bot.services.subscription import SubscriptionService
            sub_service = SubscriptionService(session, xui)
            await sub_service.deactivate(active)
        finally:
            await xui.close()

        from bot.services.audit_log import AuditLogService
        from bot.domain_enums import AuditAction
        await AuditLogService(session).log(
            admin_telegram_id=call.from_user.id if call.from_user else 0,
            action=AuditAction.SUBSCRIPTION_CANCELLED,
            target_user_id=tid,
        )
        await session.commit()

    if call.message:
        await call.message.edit_text(
            f"\u274c Подписка отменена для пользователя {code(tid)}.",
            parse_mode="HTML",
            reply_markup=admin_user_card_kb(tid),
        )
