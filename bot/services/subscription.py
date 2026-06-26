"""Subscription lifecycle management."""

from __future__ import annotations

import json
import uuid as uuid_mod
from typing import Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import Subscription
from bot.domain_enums import SubscriptionStatus, TransactionType
from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository
from bot.database.repositories.vpn_key import VpnKeyRepository
from bot.services.xui_client import XUIClient, XuiError, build_vless_link


class SubscriptionService:
    ALLOWED_TRANSITIONS = {
        SubscriptionStatus.PENDING: {SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED, SubscriptionStatus.TRIAL},
        SubscriptionStatus.TRIAL: {SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED},
        SubscriptionStatus.ACTIVE: {SubscriptionStatus.GRACE_PERIOD, SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED},
        SubscriptionStatus.GRACE_PERIOD: {SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED},
        SubscriptionStatus.SUSPENDED: {SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED},
        SubscriptionStatus.EXPIRED: {SubscriptionStatus.ACTIVE},
        SubscriptionStatus.CANCELLED: set(),
    }

    def __init__(self, session: AsyncSession, xui: XUIClient) -> None:
        self.session = session
        self.xui = xui
        self.user_repo = UserRepository(session)
        self.sub_repo = SubscriptionRepository(session)
        self.tx_repo = TransactionRepository(session)
        self.key_repo = VpnKeyRepository(session)

    def _ensure_transition(self, current: str, target: SubscriptionStatus) -> None:
        current_status = SubscriptionStatus(current)
        allowed = self.ALLOWED_TRANSITIONS.get(current_status, set())
        if target not in allowed and current_status != target:
            raise ValueError(f"Invalid subscription status transition: {current_status} -> {target}")

    async def purchase(
        self,
        telegram_id: int,
        plan_type: str,
        idempotency_key: str | None = None,
        is_trial: bool = False,
    ) -> Optional[Subscription]:
        plan = settings.plans.get(plan_type)
        if plan is None:
            raise ValueError(f"Unknown plan: {plan_type}")

        # Trial overrides: free, with configurable duration and traffic limit.
        if is_trial:
            plan = {
                **plan,
                "rub": 0,
                "stars": 0,
                "days": settings.trial_days,
            }
            effective_traffic_gb = settings.trial_traffic_limit_gb
        else:
            effective_traffic_gb = settings.traffic_limit_gb

        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            raise ValueError("User not found")
        if user.is_banned:
            raise ValueError("User is banned")
        if not is_trial and user.balance < plan["rub"]:
            raise ValueError(
                f"Insufficient balance: {user.balance} < {plan['rub']}"
            )

        if idempotency_key:
            existing_tx = await self.tx_repo.get_by_idempotency_key(idempotency_key)
            if existing_tx is not None:
                raise ValueError("Purchase already processed")

        existing = await self.sub_repo.get_active_by_user(telegram_id)
        if existing is not None:
            raise ValueError("Active subscription already exists. Renew instead.")

        client_uuid = str(uuid_mod.uuid4())
        email = f"user_{telegram_id}_{client_uuid[:8]}"
        traffic_bytes = effective_traffic_gb * (1024 ** 3) if effective_traffic_gb > 0 else 0
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
            "limitIp": settings.device_limit,
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

        if plan["rub"] > 0:
            user_after_debit = await self.user_repo.update_balance(
                telegram_id,
                -plan["rub"],
                allow_negative=False,
            )
            if user_after_debit is None:
                raise ValueError("Insufficient balance during purchase")

            try:
                await self.tx_repo.create(
                    user_id=telegram_id,
                    tx_type=TransactionType.PURCHASE,
                    amount_rub=-plan["rub"],
                    amount_stars=plan["stars"],
                    description=(
                        f"Trial {plan['label']} ({plan_type})"
                        if is_trial
                        else f"Подписка {plan['label']} ({plan_type})"
                    ),
                    idempotency_key=idempotency_key,
                    rate_snapshot=str(settings.stars_to_rub_rate),
                )
            except IntegrityError as e:
                await self.user_repo.update_balance(telegram_id, plan["rub"])
                raise ValueError("Purchase already processed") from e
        elif idempotency_key:
            # Free purchase (e.g. trial): record a zero-amount transaction so
            # the idempotency key prevents repeated activations.
            try:
                await self.tx_repo.create(
                    user_id=telegram_id,
                    tx_type=TransactionType.PURCHASE,
                    amount_rub=0,
                    amount_stars=0,
                    description=(
                        f"Trial {plan['label']} ({plan_type})"
                        if is_trial
                        else f"Подписка {plan['label']} ({plan_type})"
                    ),
                    idempotency_key=idempotency_key,
                    rate_snapshot=str(settings.stars_to_rub_rate),
                )
            except IntegrityError as e:
                raise ValueError("Purchase already processed") from e

        sub = await self.sub_repo.create(
            user_id=telegram_id,
            plan_type=plan_type,
            price_rub=plan["rub"],
            days=plan["days"],
            xui_client_id=client_uuid,
            xui_inbound_id=settings.xui_inbound_id,
            vless_link=vless_link,
            traffic_limit_gb=effective_traffic_gb,
            is_trial=is_trial,
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
        self,
        telegram_id: int,
        plan_type: str,
        transaction_description: str | None = None,
        idempotency_key: str | None = None,
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

        if idempotency_key:
            existing_tx = await self.tx_repo.get_by_idempotency_key(idempotency_key)
            if existing_tx is not None:
                raise ValueError("Renewal already processed")

        existing = await self.sub_repo.get_active_by_user(telegram_id)
        if existing is None:
            return await self.purchase(
                telegram_id,
                plan_type,
                idempotency_key=idempotency_key,
            )

        self._ensure_transition(existing.status, SubscriptionStatus.ACTIVE)

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
                raise ValueError(f"Failed to renew VPN access in 3x-ui: {e.message}")

        user_after_debit = await self.user_repo.update_balance(
            telegram_id,
            -plan["rub"],
            allow_negative=False,
        )
        if user_after_debit is None:
            raise ValueError("Insufficient balance during renewal")

        try:
            await self.tx_repo.create(
                user_id=telegram_id,
                tx_type=TransactionType.PURCHASE,
                amount_rub=-plan["rub"],
                amount_stars=plan["stars"],
                description=transaction_description or f"Продление {plan['label']} ({plan_type})",
                idempotency_key=idempotency_key,
                rate_snapshot=str(settings.stars_to_rub_rate),
            )
        except IntegrityError as e:
            await self.user_repo.update_balance(telegram_id, plan["rub"])
            raise ValueError("Renewal already processed") from e

        sub = await self.sub_repo.extend(existing.id, plan["days"])
        logger.info(
            "Subscription renewed: user={} plan={} sub_id={}",
            telegram_id,
            plan_type,
            existing.id,
        )
        return sub

    async def deactivate(self, sub: Subscription) -> None:
        self._ensure_transition(sub.status, SubscriptionStatus.EXPIRED)
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
                raise ValueError(f"Failed to deactivate VPN access in 3x-ui: {e.message}")

        await self.sub_repo.set_status(sub.id, SubscriptionStatus.EXPIRED)
        await self.key_repo.deactivate_by_subscription(sub.id)
        logger.info(
            "Subscription deactivated: user={} sub_id={}",
            sub.user_id,
            sub.id,
        )

    async def mark_grace_period(self, sub: Subscription) -> None:
        self._ensure_transition(sub.status, SubscriptionStatus.GRACE_PERIOD)
        await self.sub_repo.mark_grace_period(sub.id)

    async def suspend(self, sub: Subscription) -> None:
        self._ensure_transition(sub.status, SubscriptionStatus.SUSPENDED)
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
                        "enable": False,
                    },
                )
            except XuiError as e:
                raise ValueError(f"Failed to suspend VPN access in 3x-ui: {e.message}")
        await self.sub_repo.mark_suspended(sub.id)

    async def reactivate_key(self, sub: Subscription) -> None:
        self._ensure_transition(sub.status, SubscriptionStatus.ACTIVE)
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
                raise ValueError(f"Failed to reactivate VPN access in 3x-ui: {e.message}")

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
