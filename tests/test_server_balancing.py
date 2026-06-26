import datetime
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Base, ServerRegion, Subscription
from bot.database.repositories.server_region import ServerRegionRepository
from bot.domain_enums import SubscriptionStatus


@pytest.mark.asyncio
async def test_least_loaded_region_picks_fewest_active() -> None:
    db_path = Path(tempfile.mkdtemp()) / "test_balancing.sqlite"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = datetime.datetime.utcnow()

    async with session_factory() as session:
        session.add_all(
            [
                ServerRegion(code="de", label="DE", server_address="de.x", inbound_id=1),
                ServerRegion(code="nl", label="NL", server_address="nl.x", inbound_id=2),
            ]
        )
        # de has 2 active subs, nl has none -> nl should win.
        for i in range(2):
            session.add(
                Subscription(
                    user_id=1000 + i,
                    plan_type="1m",
                    price_rub=200,
                    status=SubscriptionStatus.ACTIVE,
                    starts_at=now,
                    expires_at=now,
                    region_code="de",
                )
            )
        await session.commit()

    async with session_factory() as session:
        repo = ServerRegionRepository(session)
        region = await repo.get_least_loaded_region()
        assert region is not None
        assert region.code == "nl"

    await engine.dispose()
