import pytest

from bot.domain_enums import SubscriptionStatus
from bot.services.subscription import SubscriptionService


class _DummyXUI:
    pass


class _DummySession:
    pass


def test_subscription_transition_rejects_invalid_path() -> None:
    service = SubscriptionService(_DummySession(), _DummyXUI())
    with pytest.raises(ValueError):
        service._ensure_transition(SubscriptionStatus.CANCELLED, SubscriptionStatus.ACTIVE)
