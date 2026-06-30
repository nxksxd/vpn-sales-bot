"""Read-only admin user views."""

from __future__ import annotations

from dataclasses import dataclass
import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories.subscription import SubscriptionRepository
from bot.database.repositories.transaction import TransactionRepository
from bot.database.repositories.user import UserRepository
from bot.database.repositories.vpn_key import VpnKeyRepository


@dataclass(frozen=True)
class AdminUserListItem:
    telegram_id: int
    username: str | None
    balance: int
    is_banned: bool


@dataclass(frozen=True)
class AdminUserListPage:
    total: int
    users: list[AdminUserListItem]


@dataclass(frozen=True)
class AdminSubscriptionCard:
    plan_type: str
    expires_at: datetime.datetime
    xui_client_id: str | None


@dataclass(frozen=True)
class AdminKeyCard:
    xui_client_id: str
    is_active: bool


@dataclass(frozen=True)
class AdminTransactionCard:
    amount_rub: int
    amount_stars: int | None
    tx_type: str
    created_at: datetime.datetime


@dataclass(frozen=True)
class AdminUserCard:
    telegram_id: int
    username: str | None
    first_name: str | None
    balance: int
    is_banned: bool
    created_at: datetime.datetime
    last_active: datetime.datetime | None
    active_subscription: AdminSubscriptionCard | None
    keys: list[AdminKeyCard]
    recent_transactions: list[AdminTransactionCard]


class AdminUserService:
    def __init__(self, session: AsyncSession) -> None:
        self.user_repo = UserRepository(session)
        self.sub_repo = SubscriptionRepository(session)
        self.tx_repo = TransactionRepository(session)
        self.key_repo = VpnKeyRepository(session)

    async def search_users(self, query: str) -> list[AdminUserListItem]:
        users = await self.user_repo.search_users(query)
        return [self._user_item(user) for user in users]

    async def get_user_list_page(self, *, offset: int, limit: int) -> AdminUserListPage:
        total = await self.user_repo.count_all()
        users = await self.user_repo.get_all_users(offset=offset, limit=limit)
        return AdminUserListPage(
            total=total,
            users=[self._user_item(user) for user in users],
        )

    async def get_user_card(self, telegram_id: int) -> AdminUserCard | None:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return None

        active_sub = await self.sub_repo.get_active_by_user(telegram_id)
        recent_txs = await self.tx_repo.get_user_history(telegram_id, limit=5)
        keys = await self.key_repo.get_user_keys(telegram_id)

        return AdminUserCard(
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            balance=user.balance,
            is_banned=user.is_banned,
            created_at=user.created_at,
            last_active=user.last_active,
            active_subscription=(
                AdminSubscriptionCard(
                    plan_type=active_sub.plan_type,
                    expires_at=active_sub.expires_at,
                    xui_client_id=active_sub.xui_client_id,
                )
                if active_sub is not None
                else None
            ),
            keys=[
                AdminKeyCard(
                    xui_client_id=key.xui_client_id,
                    is_active=key.is_active,
                )
                for key in keys
            ],
            recent_transactions=[
                AdminTransactionCard(
                    amount_rub=tx.amount_rub,
                    amount_stars=tx.amount_stars,
                    tx_type=tx.type,
                    created_at=tx.created_at,
                )
                for tx in recent_txs
            ],
        )

    async def get_user_ban_status(self, telegram_id: int) -> bool | None:
        user = await self.user_repo.get_by_telegram_id(telegram_id)
        return None if user is None else bool(user.is_banned)

    @staticmethod
    def _user_item(user: object) -> AdminUserListItem:
        return AdminUserListItem(
            telegram_id=user.telegram_id,
            username=user.username,
            balance=user.balance,
            is_banned=user.is_banned,
        )
