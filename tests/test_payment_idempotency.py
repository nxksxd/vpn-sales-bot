import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Base
from bot.services.payment import PaymentService


@pytest.mark.asyncio
async def test_process_topup_is_idempotent() -> None:
    db_path = Path(tempfile.mkdtemp()) / "test_topup.sqlite"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await session.execute(
            Base.metadata.tables["users"].insert().values(
                telegram_id=1,
                username="tester",
                first_name="Tester",
                language_code="ru",
                balance=0,
                is_banned=False,
                is_admin=False,
                auto_renew=True,
                referral_code="TEST1234",
            )
        )
        await session.commit()

    async with session_factory() as session:
        service = PaymentService(session)
        credited = await service.process_topup(1, 100, "charge-1")
        duplicate = await service.process_topup(1, 100, "charge-1")
        assert credited > 0
        assert duplicate == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_process_telegram_successful_topup_handles_duplicate_event() -> None:
    db_path = Path(tempfile.mkdtemp()) / "test_telegram_successful_topup.sqlite"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await session.execute(
            Base.metadata.tables["users"].insert().values(
                telegram_id=2,
                username="telegram_payer",
                first_name="Telegram",
                language_code="ru",
                balance=0,
                is_banned=False,
                is_admin=False,
                auto_renew=True,
                onboarding_completed=False,
                trial_used=False,
                referral_code="TGPAID02",
            )
        )
        await session.commit()

    async with session_factory() as session:
        service = PaymentService(session)
        first = await service.process_telegram_successful_topup(
            telegram_id=2,
            amount_stars=100,
            charge_id="charge-telegram-2",
            payload="topup:v1:100",
        )
        duplicate = await service.process_telegram_successful_topup(
            telegram_id=2,
            amount_stars=100,
            charge_id="charge-telegram-2",
            payload="topup:v1:100",
        )

        assert first > 0
        assert duplicate == 0

        rows = (
            await session.execute(
                Base.metadata.tables["payment_events"].select().where(
                    Base.metadata.tables["payment_events"].c.charge_id == "charge-telegram-2"
                )
            )
        ).all()
        assert len(rows) == 1

    await engine.dispose()
