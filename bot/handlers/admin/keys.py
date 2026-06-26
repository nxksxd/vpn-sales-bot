"""Admin VPN key management handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger

from bot.database.session import async_session_factory
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.vpn_key import VpnKeyRepository
from bot.domain_enums import AuditAction, SubscriptionStatus
from bot.keyboards.admin_kb import admin_key_actions_kb, admin_user_card_kb
from bot.middlewares.admin_check import admin_only
from bot.services.audit_log import AuditLogService
from bot.services.subscription import SubscriptionService
from bot.services.xui_client import XUIClient, XuiError
from bot.utils.formatters import code, esc

router = Router(name="admin_keys")


@router.callback_query(F.data.startswith("adm:keys:"))
@admin_only
async def cb_keys_menu(call: CallbackQuery) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0

    async with async_session_factory() as session:
        key_repo = VpnKeyRepository(session)
        keys = await key_repo.get_user_keys(tid)

    if not keys:
        text = f"\U0001f511 У пользователя {code(tid)} нет ключей."
    else:
        lines = [f"\U0001f511 <b>Ключи пользователя {code(tid)}:</b>\n"]
        for k in keys:
            status = "\u2705 Активен" if k.is_active else "\u274c Неактивен"
            lines.append(
                f"\u2022 UUID: {code(k.xui_client_id[:20])}...\n"
                f"  Email: {code(k.email)}\n"
                f"  Статус: {status}\n"
                f"  Inbound: {k.xui_inbound_id}"
            )
        text = "\n".join(lines)

    if call.message:
        try:
            await call.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=admin_key_actions_kb(tid),
            )
        except Exception:
            await call.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=admin_key_actions_kb(tid),
            )


@router.callback_query(F.data.startswith("adm:regen:"))
@admin_only
async def cb_regenerate_key(call: CallbackQuery) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0

    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        active = await sub_repo.get_active_by_user(tid)

        if active is None:
            if call.message:
                await call.message.edit_text(
                    f"\u274c У пользователя {code(tid)} нет активной подписки.",
                    parse_mode="HTML",
                    reply_markup=admin_user_card_kb(tid),
                )
            return

        xui = XUIClient()
        try:
            sub_service = SubscriptionService(session, xui)
            new_link = await sub_service.regenerate_key(active)
            audit = AuditLogService(session)
            await audit.log(
                call.from_user.id,
                AuditAction.KEY_REGENERATED,
                target_user_id=tid,
                details="regenerated active key",
            )
        except ValueError as e:
            if call.message:
                await call.message.edit_text(
                    f"\u274c Ошибка: {esc(str(e))}",
                    parse_mode="HTML",
                    reply_markup=admin_key_actions_kb(tid),
                )
            return
        except Exception as e:
            logger.error("Key regeneration failed for user {}: {}", tid, e)
            if call.message:
                await call.message.edit_text(
                    f"\u274c Ошибка при пересоздании ключа: {esc(str(e))}",
                    parse_mode="HTML",
                    reply_markup=admin_key_actions_kb(tid),
                )
            return
        finally:
            await xui.close()

    if call.message:
        await call.message.edit_text(
            f"\u2705 Ключ VLESS пересоздан для пользователя {code(tid)}.\n\n"
            f"Новый ключ:\n{code(new_link or '—')}",
            parse_mode="HTML",
            reply_markup=admin_key_actions_kb(tid),
        )


@router.callback_query(F.data.startswith("adm:deact:"))
@admin_only
async def cb_deactivate_key(call: CallbackQuery) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0

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
            sub_service = SubscriptionService(session, xui)
            await sub_service.deactivate(active)
            audit = AuditLogService(session)
            await audit.log(
                call.from_user.id,
                AuditAction.KEY_DEACTIVATED,
                target_user_id=tid,
                details="deactivated active key",
            )
        except Exception as e:
            logger.error("Deactivation failed: {}", e)
        finally:
            await xui.close()

    if call.message:
        await call.message.edit_text(
            f"\u23f8 Ключ деактивирован для пользователя {code(tid)}.",
            parse_mode="HTML",
            reply_markup=admin_key_actions_kb(tid),
        )


@router.callback_query(F.data.startswith("adm:react:"))
@admin_only
async def cb_reactivate_key(call: CallbackQuery) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0

    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        active = await sub_repo.get_active_by_user(tid)
        if active is None:
            subs = await sub_repo.get_user_subscriptions(tid, limit=1)
            active = subs[0] if subs else None

        if active is None:
            if call.message:
                await call.message.answer(
                    f"\u274c Нет подписки у {code(tid)}.",
                    parse_mode="HTML",
                )
            return

        xui = XUIClient()
        try:
            sub_service = SubscriptionService(session, xui)
            await sub_service.reactivate_key(active)
            await sub_repo.set_status(active.id, SubscriptionStatus.ACTIVE)
            audit = AuditLogService(session)
            await audit.log(
                call.from_user.id,
                AuditAction.KEY_REACTIVATED,
                target_user_id=tid,
                details="reactivated key",
            )
        except Exception as e:
            logger.error("Reactivation failed: {}", e)
        finally:
            await xui.close()

    if call.message:
        await call.message.edit_text(
            f"\u25b6\ufe0f Ключ активирован для пользователя {code(tid)}.",
            parse_mode="HTML",
            reply_markup=admin_key_actions_kb(tid),
        )


@router.callback_query(F.data.startswith("adm:rst_traffic:"))
@admin_only
async def cb_reset_traffic(call: CallbackQuery) -> None:
    await call.answer()
    tid = int(call.data.split(":")[-1]) if call.data else 0

    async with async_session_factory() as session:
        key_repo = VpnKeyRepository(session)
        key = await key_repo.get_active_by_user(tid)
        if key is None:
            if call.message:
                await call.message.answer(
                    f"\u274c Нет активного ключа у {code(tid)}.",
                    parse_mode="HTML",
                )
            return

        xui = XUIClient()
        try:
            await xui.reset_client_traffic(key.xui_inbound_id, key.email)
            audit = AuditLogService(session)
            await audit.log(
                call.from_user.id,
                AuditAction.TRAFFIC_RESET,
                target_user_id=tid,
                details=f"email={key.email}",
            )
        except XuiError as e:
            logger.error("Traffic reset failed: {}", e)
            if call.message:
                await call.message.answer(
                    f"\u274c Ошибка сброса трафика: {esc(e.message)}",
                    parse_mode="HTML",
                )
            return
        finally:
            await xui.close()

    if call.message:
        await call.message.edit_text(
            f"\U0001f504 Трафик сброшен для пользователя {code(tid)}.",
            parse_mode="HTML",
            reply_markup=admin_key_actions_kb(tid),
        )
