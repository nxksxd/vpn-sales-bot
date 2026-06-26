import asyncio
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Base
from bot.services.payment import PaymentService


@pytest.mark.asyncio
async def test_process_topup_is_idempotent() -> None:
    db_path = Path("/var/folders/kl/frv_wd1s22l2_2j521g5t0n80000gn/T/opencode/test_topup.sqlite")
    if db_path.exists():
        db_path.unlink()

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
