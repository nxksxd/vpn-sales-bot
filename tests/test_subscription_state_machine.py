import pytest

from bot.domain_enums import SubscriptionStatus
from bot.services import subscription as subscription_module
from bot.services.subscription import SubscriptionService, _cleanup_provisioned_client
from bot.services.xui_client import XuiError


class _DummyXUI:
    pass


class _DummySession:
    pass


def test_subscription_transition_rejects_invalid_path() -> None:
    service = SubscriptionService(_DummySession(), _DummyXUI())
    with pytest.raises(ValueError):
        service._ensure_transition(SubscriptionStatus.CANCELLED, SubscriptionStatus.ACTIVE)


class _RecordingXUI:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc
        self.deleted: list[tuple[int, str, str]] = []

    async def delete_client(self, inbound_id: int, client_id: str, *, email: str) -> None:
        self.deleted.append((inbound_id, client_id, email))
        if self.exc:
            raise self.exc


@pytest.mark.asyncio
async def test_cleanup_provisioned_client_rolls_back_created_xui_client() -> None:
    xui = _RecordingXUI()

    await _cleanup_provisioned_client(xui, 7, "client-uuid", "user@example", "test")

    assert xui.deleted == [(7, "client-uuid", "user@example")]


@pytest.mark.asyncio
async def test_cleanup_provisioned_client_treats_missing_client_as_success() -> None:
    xui = _RecordingXUI(XuiError(404, "record not found"))

    await _cleanup_provisioned_client(xui, 7, "missing-uuid", "user@example", "test")

    assert xui.deleted == [(7, "missing-uuid", "user@example")]


class _PurchaseXUI(_RecordingXUI):
    def __init__(self) -> None:
        super().__init__()
        self.added_client_id: str | None = None
        self.added_email: str | None = None

    async def get_inbound(self, inbound_id: int) -> dict:
        return {"port": 443, "settings": "{}", "streamSettings": "{}"}

    async def add_client(self, inbound_id: int, client_data: dict) -> None:
        self.added_client_id = client_data["id"]
        self.added_email = client_data["email"]


class _FakeUserRepo:
    async def get_by_telegram_id(self, telegram_id: int):
        return type("User", (), {"balance": 10_000, "is_banned": False})()

    async def update_balance(self, *args, **kwargs):
        raise AssertionError("balance must not be debited after provisioning failure")


class _FakeSubRepo:
    async def get_active_by_user(self, telegram_id: int):
        return None


class _FakeTxRepo:
    async def get_by_idempotency_key(self, key: str):
        return None

    async def delete_by_idempotency_key(self, key: str) -> None:
        return None


class _FakeKeyRepo:
    pass


@pytest.mark.asyncio
async def test_purchase_rolls_back_xui_client_when_post_add_step_fails(monkeypatch) -> None:
    xui = _PurchaseXUI()
    service = SubscriptionService(_DummySession(), xui)
    service.user_repo = _FakeUserRepo()
    service.sub_repo = _FakeSubRepo()
    service.tx_repo = _FakeTxRepo()
    service.key_repo = _FakeKeyRepo()

    def fail_build_vless_link(**kwargs) -> str:
        raise RuntimeError("link build failed")

    monkeypatch.setattr(subscription_module, "build_vless_link", fail_build_vless_link)

    with pytest.raises(RuntimeError, match="link build failed"):
        await service.purchase(telegram_id=123, plan_type="1m", idempotency_key="buy:123")

    assert xui.added_client_id is not None
    assert xui.added_email is not None
    assert xui.deleted == [(1, xui.added_client_id, xui.added_email)]
