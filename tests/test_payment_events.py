import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Base
from bot.database.repositories.payment_event import PaymentEventRepository
from bot.domain_enums import PaymentStatus
from bot.services.payment import PaymentService


@pytest.mark.asyncio
async def test_payment_event_status_update() -> None:
    db_path = Path(tempfile.mkdtemp()) / "test_payment_event.sqlite"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await session.execute(
            Base.metadata.tables["users"].insert().values(
                telegram_id=2,
                username="payer",
                first_name="Payer",
                language_code="ru",
                balance=0,
                is_banned=False,
                is_admin=False,
                auto_renew=True,
                onboarding_completed=False,
                trial_used=False,
                referral_code="PAYR1234",
            )
        )
        await session.commit()

    async with session_factory() as session:
        repo = PaymentEventRepository(session)
        event = await repo.create(
            user_id=2,
            status=PaymentStatus.PENDING,
            amount_stars=100,
            amount_rub=200,
            charge_id="charge-2",
            payload="topup:v1:100",
        )
        assert event.status == PaymentStatus.PENDING

        updated = await repo.update_status("charge-2", PaymentStatus.PAID)
        assert updated is not None
        assert updated.status == PaymentStatus.PAID

    await engine.dispose()


@pytest.mark.asyncio
async def test_process_refund_marks_event_refunded() -> None:
    db_path = Path(tempfile.mkdtemp()) / "test_refund.sqlite"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await session.execute(
            Base.metadata.tables["users"].insert().values(
                telegram_id=3,
                referral_code="RFND1234",
                balance=200,
            )
        )
        await session.commit()
        repo = PaymentEventRepository(session)
        await repo.create(
            user_id=3,
            status=PaymentStatus.PAID,
            amount_stars=100,
            amount_rub=200,
            charge_id="charge-3",
        )

    async with session_factory() as session:
        service = PaymentService(session)
        ok = await service.process_refund(3, 200, charge_id="charge-3")
        assert ok is True

    async with session_factory() as session:
        repo = PaymentEventRepository(session)
        event = await repo.get_by_charge_id("charge-3")
        assert event is not None
        assert event.status == PaymentStatus.REFUNDED

    await engine.dispose()
