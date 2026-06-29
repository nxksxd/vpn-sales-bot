"""Tests for YooKassa integration."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Base, User
from bot.database.repositories.payment_event import PaymentEventRepository
from bot.domain_enums import PaymentStatus


def _make_db():
    """Create in-memory SQLite test DB."""
    db_path = Path(tempfile.mkdtemp()) / "test_yookassa.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


@pytest.mark.asyncio
async def test_payment_method_selection_keyboard():
    """Test that payment method keyboard always shows both options."""
    from bot.handlers.balance import _payment_method_kb

    kb = _payment_method_kb()
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "⭐ Оплата звёздами" in buttons
    assert "💳 Оплата через ЮKassa" in buttons


@pytest.mark.asyncio
async def test_yookassa_unavailable_shows_error():
    """Test that clicking YooKassa when not configured shows error."""
    from bot.handlers.yookassa_payment import _yookassa_available

    with patch(
        "bot.handlers.yookassa_payment.settings"
    ) as mock_settings:
        mock_settings.yookassa_shop_id = ""
        mock_settings.yookassa_secret_key = ""
        assert _yookassa_available() is False

        mock_settings.yookassa_shop_id = "123456"
        mock_settings.yookassa_secret_key = "test_key"
        assert _yookassa_available() is True


@pytest.mark.asyncio
async def test_webhook_succeeds_credits_balance():
    """Test that a successful payment webhook credits user balance."""
    engine, session_factory = _make_db()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await session.execute(
            Base.metadata.tables["users"].insert().values(
                telegram_id=100,
                username="test_user",
                first_name="Test",
                language_code="ru",
                balance=0,
                is_banned=False,
                is_admin=False,
                auto_renew=True,
                onboarding_completed=False,
                trial_used=False,
                referral_code="YKTEST01",
            )
        )
        await session.commit()

    # Create pending payment event
    async with session_factory() as session:
        repo = PaymentEventRepository(session)
        await repo.create(
            user_id=100,
            status=PaymentStatus.PENDING,
            amount_stars=0,
            amount_rub=500,
            charge_id="yk-payment-001",
            payload="yookassa:topup:500",
        )

    # Simulate webhook processing
    notify_path = (
        "bot.services.yookassa_webhook._notify_user_payment_success"
    )
    with patch(notify_path, new_callable=AsyncMock):
        from bot.services.yookassa_webhook import _handle_payment_succeeded

        payment_obj = {
            "id": "yk-payment-001",
            "status": "succeeded",
            "amount": {"value": "500.00", "currency": "RUB"},
            "metadata": {"telegram_id": "100", "amount_rub": "500", "type": "topup"},
        }

        # Use real session factory
        with patch("bot.services.yookassa_webhook.async_session_factory", session_factory):
            await _handle_payment_succeeded("yk-payment-001", payment_obj)

    # Verify balance was credited
    async with session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.telegram_id == 100))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.balance == 500

    await engine.dispose()


@pytest.mark.asyncio
async def test_webhook_duplicate_does_not_double_credit():
    """Test that duplicate webhook does not credit balance twice."""
    engine, session_factory = _make_db()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await session.execute(
            Base.metadata.tables["users"].insert().values(
                telegram_id=101,
                username="test_dup",
                first_name="TestDup",
                language_code="ru",
                balance=0,
                is_banned=False,
                is_admin=False,
                auto_renew=True,
                onboarding_completed=False,
                trial_used=False,
                referral_code="YKTEST02",
            )
        )
        await session.commit()

    payment_obj = {
        "id": "yk-payment-002",
        "status": "succeeded",
        "amount": {"value": "300.00", "currency": "RUB"},
        "metadata": {"telegram_id": "101", "amount_rub": "300", "type": "topup"},
    }

    notify_path = (
        "bot.services.yookassa_webhook._notify_user_payment_success"
    )
    with patch(notify_path, new_callable=AsyncMock):
        from bot.services.yookassa_webhook import _handle_payment_succeeded

        # First webhook
        sf_path = (
            "bot.services.yookassa_webhook.async_session_factory"
        )
        with patch(sf_path, session_factory):
            await _handle_payment_succeeded("yk-payment-002", payment_obj)

        # Duplicate webhook
        with patch(sf_path, session_factory):
            await _handle_payment_succeeded("yk-payment-002", payment_obj)

    # Verify balance credited only once
    async with session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.telegram_id == 101))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.balance == 300

    await engine.dispose()


@pytest.mark.asyncio
async def test_webhook_canceled_does_not_credit():
    """Test that a canceled payment does not credit balance."""
    engine, session_factory = _make_db()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await session.execute(
            Base.metadata.tables["users"].insert().values(
                telegram_id=102,
                username="test_cancel",
                first_name="TestCancel",
                language_code="ru",
                balance=100,
                is_banned=False,
                is_admin=False,
                auto_renew=True,
                onboarding_completed=False,
                trial_used=False,
                referral_code="YKTEST03",
            )
        )
        await session.commit()

    # Create pending payment event
    async with session_factory() as session:
        repo = PaymentEventRepository(session)
        await repo.create(
            user_id=102,
            status=PaymentStatus.PENDING,
            amount_stars=0,
            amount_rub=500,
            charge_id="yk-payment-003",
            payload="yookassa:topup:500",
        )

    payment_obj = {
        "id": "yk-payment-003",
        "status": "canceled",
        "cancellation_details": {"party": "yoo_money", "reason": "expired_on_confirmation"},
        "metadata": {"telegram_id": "102", "amount_rub": "500", "type": "topup"},
    }

    cancel_path = (
        "bot.services.yookassa_webhook"
        "._notify_user_payment_canceled"
    )
    with patch(cancel_path, new_callable=AsyncMock):
        from bot.services.yookassa_webhook import _handle_payment_canceled

        sf_path = (
            "bot.services.yookassa_webhook.async_session_factory"
        )
        with patch(sf_path, session_factory):
            await _handle_payment_canceled("yk-payment-003", payment_obj)

    # Verify balance unchanged
    async with session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.telegram_id == 102))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.balance == 100  # unchanged

    # Verify event status is failed
    async with session_factory() as session:
        repo = PaymentEventRepository(session)
        event = await repo.get_by_charge_id("yk-payment-003")
        assert event is not None
        assert event.status == PaymentStatus.FAILED

    await engine.dispose()


@pytest.mark.asyncio
async def test_webhook_unknown_payment_ignored():
    """Test that webhook for unknown payment ID is handled gracefully."""
    engine, session_factory = _make_db()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    payment_obj = {
        "id": "yk-unknown-999",
        "status": "succeeded",
        "amount": {"value": "100.00", "currency": "RUB"},
        "metadata": {"telegram_id": "999", "amount_rub": "100", "type": "topup"},
    }

    notify_path = (
        "bot.services.yookassa_webhook._notify_user_payment_success"
    )
    with patch(notify_path, new_callable=AsyncMock):
        from bot.services.yookassa_webhook import _handle_payment_succeeded

        # Should not crash even if user doesn't exist
        sf_path = (
            "bot.services.yookassa_webhook.async_session_factory"
        )
        with patch(sf_path, session_factory):
            await _handle_payment_succeeded("yk-unknown-999", payment_obj)

    await engine.dispose()


@pytest.mark.asyncio
async def test_ip_verification():
    """Test IP verification against YooKassa trusted ranges."""
    from bot.services.yookassa_webhook import _is_trusted_ip

    # Trusted IPs
    assert _is_trusted_ip("185.71.76.1") is True
    assert _is_trusted_ip("185.71.77.15") is True
    assert _is_trusted_ip("77.75.153.50") is True
    assert _is_trusted_ip("77.75.156.11") is True
    assert _is_trusted_ip("77.75.156.35") is True
    assert _is_trusted_ip("77.75.154.200") is True

    # Untrusted IPs
    assert _is_trusted_ip("1.2.3.4") is False
    assert _is_trusted_ip("192.168.1.1") is False
    assert _is_trusted_ip("10.0.0.1") is False
