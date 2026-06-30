"""Admin promo code management service."""

from __future__ import annotations

from dataclasses import dataclass
import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import PromoCode
from bot.database.repositories.promo_code import PromoCodeRepository
from bot.domain_enums import AuditAction
from bot.services.audit_log import AuditLogService


@dataclass(frozen=True)
class AdminPromoView:
    id: int
    code: str
    discount_percent: int
    is_active: bool
    usage_limit: int | None
    used_count: int
    valid_until: datetime.datetime | None
    created_at: datetime.datetime | None


@dataclass(frozen=True)
class AdminPromoToggleResult:
    promo: AdminPromoView | None
    new_active: bool | None


@dataclass(frozen=True)
class AdminPromoDeleteResult:
    deleted: bool
    promo_code: str


class AdminPromoService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = PromoCodeRepository(session)
        self.audit = AuditLogService(session)

    async def list_active(self) -> list[AdminPromoView]:
        promos = await self.repo.get_all_active()
        return [self._promo_view(promo) for promo in promos]

    async def list_all(self) -> list[AdminPromoView]:
        promos = await self.repo.list_all()
        return [self._promo_view(promo) for promo in promos]

    async def get_card(self, promo_id: int) -> AdminPromoView | None:
        promo = await self.repo.get_by_id(promo_id)
        return None if promo is None else self._promo_view(promo)

    async def code_exists(self, promo_code: str) -> bool:
        return await self.repo.get_by_code(promo_code) is not None

    async def create(
        self,
        *,
        admin_id: int,
        code: str,
        discount_percent: int,
        usage_limit: int | None,
        valid_until: datetime.datetime | None,
    ) -> AdminPromoView:
        promo = await self.repo.create(
            code=code,
            discount_percent=discount_percent,
            usage_limit=usage_limit,
            valid_until=valid_until,
        )
        await self.audit.log(
            admin_telegram_id=admin_id,
            action=AuditAction.SETTINGS_CHANGED,
            details=f"promo_created: {promo.code} discount={promo.discount_percent}%",
        )
        return self._promo_view(promo)

    async def toggle(self, *, admin_id: int, promo_id: int) -> AdminPromoToggleResult:
        promo = await self.repo.get_by_id(promo_id)
        if promo is None:
            return AdminPromoToggleResult(promo=None, new_active=None)

        new_active = not promo.is_active
        await self.repo.set_active(promo_id, new_active)
        await self.audit.log(
            admin_telegram_id=admin_id,
            action=AuditAction.SETTINGS_CHANGED,
            details=f"promo {'activated' if new_active else 'deactivated'}: {promo.code}",
        )
        return AdminPromoToggleResult(promo=self._promo_view(promo), new_active=new_active)

    async def delete(self, *, admin_id: int, promo_id: int) -> AdminPromoDeleteResult:
        promo = await self.repo.get_by_id(promo_id)
        promo_code = promo.code if promo else "?"
        deleted = await self.repo.delete(promo_id)

        if deleted:
            await self.audit.log(
                admin_telegram_id=admin_id,
                action=AuditAction.SETTINGS_CHANGED,
                details=f"promo_deleted: {promo_code}",
            )

        return AdminPromoDeleteResult(deleted=deleted, promo_code=promo_code)

    @staticmethod
    def _promo_view(promo: PromoCode) -> AdminPromoView:
        return AdminPromoView(
            id=promo.id,
            code=promo.code,
            discount_percent=promo.discount_percent,
            is_active=promo.is_active,
            usage_limit=promo.usage_limit,
            used_count=promo.used_count,
            valid_until=promo.valid_until,
            created_at=promo.created_at,
        )
