"""Subscription lifecycle management."""

from __future__ import annotations

import json
import uuid as uuid_mod
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import Subscription
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository
from bot.database.repositories.vpn_key import VpnKeyRepository
from bot.services.xui_client import XUIClient, XuiError, build_vless_link


class SubscriptionService:
    def __init__(self, session: AsyncSession, xui: XUIClient) -> None:
        self.session = session
        self.xui = xui
        self.user_repo = UserRepository(session)
        self.sub_repo = SubscriptionRepository(session)
        self.tx_repo = TransactionRepository(session)
        self.key_repo = VpnKeyRepository(session)

    async def purchase(
        self, telegram_id: int, plan_type: str
    ) -> Optional[Subscription]:
        plan = settings.plans.get(plan_type)
        if plan is None:
            raise ValueError(f"Unknown plan: {plan_type}")

        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            raise ValueError("User not found")
        if user.is_banned:
            raise ValueError("User is banned")
        if user.balance < plan["rub"]:
            raise ValueError(
                f"Insufficient balance: {user.balance} < {plan['rub']}"
            )

        existing = await self.sub_repo.get_active_by_user(telegram_id)
        if existing is not None:
            raise ValueError("Active subscription already exists. Renew instead.")

        client_uuid = str(uuid_mod.uuid4())
        email = f"user_{telegram_id}_{client_uuid[:8]}"
        traffic_bytes = settings.traffic_limit_gb * (1024 ** 3) if settings.traffic_limit_gb > 0 else 0
        expiry_ms = int(
            (
                __import__("datetime").datetime.utcnow()
                + __import__("datetime").timedelta(days=plan["days"])
            ).timestamp()
            * 1000
        )

        client_data = {
            "id": client_uuid,
            "email": email,
            "enable": True,
            "flow": "",
            "limitIp": 0,
            "totalGB": traffic_bytes,
            "expiryTime": expiry_ms,
            "tgId": telegram_id,
            "subId": "",
        }

        try:
            await self.xui.add_client(settings.xui_inbound_id, client_data)
        except XuiError as e:
            logger.error("Failed to create 3X-UI client: {}", e)
            raise ValueError(f"Failed to create VPN key: {e.message}")

        server = settings.server_address or settings.xui_url.split("://")[-1].split(":")[0]
        inbound = await self.xui.get_inbound(settings.xui_inbound_id)
        inbound_data = inbound or {}
        if isinstance(inbound_data.get("settings"), str):
            try:
                inbound_data["settings_obj"] = json.loads(inbound_data["settings"])
            except (ValueError, TypeError):
                inbound_data["settings_obj"] = {}
        stream_raw = inbound_data.get("streamSettings") or inbound_data.get("stream_settings")
        if isinstance(stream_raw, str):
            try:
                inbound_data["stream_obj"] = json.loads(stream_raw)
            except (ValueError, TypeError):
                inbound_data["stream_obj"] = {}
        elif isinstance(stream_raw, dict):
            inbound_data["stream_obj"] = stream_raw

        port = inbound_data.get("port", 443)
        vless_link = build_vless_link(
            uuid=client_uuid,
            server=server,
            port=port,
            inbound=inbound_data,
            email=email,
        )

        await self.user_repo.update_balance(telegram_id, -plan["rub"])

        await self.tx_repo.create(
            user_id=telegram_id,
            tx_type="purchase",
            amount=-plan["rub"],
            description=f"Подписка {plan['label']} ({plan_type})",
        )

        sub = await self.sub_repo.create(
            user_id=telegram_id,
            plan_type=plan_type,
            price_stars=plan["rub"],
            days=plan["days"],
            xui_client_id=client_uuid,
            xui_inbound_id=settings.xui_inbound_id,
            vless_link=vless_link,
            traffic_limit_gb=settings.traffic_limit_gb,
        )

        await self.key_repo.create(
            subscription_id=sub.id,
            user_id=telegram_id,
            xui_client_id=client_uuid,
            xui_inbound_id=settings.xui_inbound_id,
            email=email,
            vless_link=vless_link,
        )

        logger.info(
            "Subscription purchased: user={} plan={} uuid={}",
            telegram_id,
            plan_type,
            client_uuid,
        )
        return sub

    async def renew(
        self, telegram_id: int, plan_type: str
    ) -> Optional[Subscription]:
        plan = settings.plans.get(plan_type)
        if plan is None:
            raise ValueError(f"Unknown plan: {plan_type}")

        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            raise ValueError("User not found")
        if user.balance < plan["rub"]:
            raise ValueError(
                f"Insufficient balance: {user.balance} < {plan['rub']}"
            )

        existing = await self.sub_repo.get_active_by_user(telegram_id)
        if existing is None:
            return await self.purchase(telegram_id, plan_type)

        if existing.xui_client_id:
            try:
                import datetime

                new_expiry = existing.expires_at + datetime.timedelta(days=plan["days"])
                expiry_ms = int(new_expiry.timestamp() * 1000)
                key = await self.key_repo.get_by_client_id(existing.xui_client_id)
                email = key.email if key else f"user_{telegram_id}"
                await self.xui.update_client(
                    existing.xui_inbound_id or settings.xui_inbound_id,
                    existing.xui_client_id,
                    {
                        "id": existing.xui_client_id,
                        "email": email,
                        "enable": True,
                        "expiryTime": expiry_ms,
                    },
                )
            except XuiError as e:
                logger.error("Failed to update 3X-UI client expiry: {}", e)

        await self.user_repo.update_balance(telegram_id, -plan["rub"])

        await self.tx_repo.create(
            user_id=telegram_id,
            tx_type="purchase",
            amount=-plan["rub"],
            description=f"Продление {plan['label']} ({plan_type})",
        )

        sub = await self.sub_repo.extend(existing.id, plan["days"])
        logger.info(
            "Subscription renewed: user={} plan={} sub_id={}",
            telegram_id,
            plan_type,
            existing.id,
        )
        return sub

    async def deactivate(self, sub: Subscription) -> None:
        if sub.xui_client_id and sub.xui_inbound_id:
            try:
                key = await self.key_repo.get_by_client_id(sub.xui_client_id)
                email = key.email if key else None
                await self.xui.update_client(
                    sub.xui_inbound_id,
                    sub.xui_client_id,
                    {
                        "id": sub.xui_client_id,
                        "email": email or f"user_{sub.user_id}",
                        "enable": False,
                    },
                )
            except XuiError as e:
                logger.error(
                    "Failed to disable 3X-UI client {}: {}", sub.xui_client_id, e
                )

        await self.sub_repo.set_status(sub.id, "expired")
        await self.key_repo.deactivate_by_subscription(sub.id)
        logger.info(
            "Subscription deactivated: user={} sub_id={}",
            sub.user_id,
            sub.id,
        )

    async def reactivate_key(self, sub: Subscription) -> None:
        if sub.xui_client_id and sub.xui_inbound_id:
            try:
                key = await self.key_repo.get_by_client_id(sub.xui_client_id)
                email = key.email if key else f"user_{sub.user_id}"
                await self.xui.update_client(
                    sub.xui_inbound_id,
                    sub.xui_client_id,
                    {
                        "id": sub.xui_client_id,
                        "email": email,
                        "enable": True,
                    },
                )
                if key:
                    await self.key_repo.set_active(key.id, True)
            except XuiError as e:
                logger.error(
                    "Failed to reactivate 3X-UI client {}: {}",
                    sub.xui_client_id,
                    e,
                )

    async def regenerate_key(self, sub: Subscription) -> Optional[str]:
        if not sub.xui_client_id or not sub.xui_inbound_id:
            raise ValueError("No VPN key associated with subscription")

        try:
            result = await self.xui.regenerate_client(
                sub.xui_inbound_id, sub.xui_client_id
            )
        except XuiError as e:
            raise ValueError(f"Failed to regenerate key: {e.message}")

        new_uuid = result["new_uuid"]
        server = settings.server_address or settings.xui_url.split("://")[-1].split(":")[0]
        inbound = await self.xui.get_inbound(sub.xui_inbound_id)
        inbound_data = inbound or {}
        if isinstance(inbound_data.get("settings"), str):
            try:
                inbound_data["settings_obj"] = json.loads(inbound_data["settings"])
            except (ValueError, TypeError):
                inbound_data["settings_obj"] = {}
        stream_raw = inbound_data.get("streamSettings") or inbound_data.get("stream_settings")
        if isinstance(stream_raw, str):
            try:
                inbound_data["stream_obj"] = json.loads(stream_raw)
            except (ValueError, TypeError):
                inbound_data["stream_obj"] = {}
        elif isinstance(stream_raw, dict):
            inbound_data["stream_obj"] = stream_raw

        port = inbound_data.get("port", 443)
        email = result.get("email", f"user_{sub.user_id}")
        new_link = build_vless_link(
            uuid=new_uuid,
            server=server,
            port=port,
            inbound=inbound_data,
            email=email,
        )

        sub.xui_client_id = new_uuid
        sub.vless_link = new_link
        await self.session.commit()

        key = await self.key_repo.get_by_client_id(result["old_uuid"])
        if key:
            await self.key_repo.update_vless_link(key.id, new_link, new_uuid)

        return new_link
