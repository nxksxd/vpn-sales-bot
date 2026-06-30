import pytest

from bot.domain_enums import SubscriptionStatus
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
