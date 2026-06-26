from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Base, ServerRegion
from bot.database.repositories.server_region import ServerRegionRepository


@pytest.mark.asyncio
async def test_server_region_repository_returns_active_regions() -> None:
    db_path = Path("/var/folders/kl/frv_wd1s22l2_2j521g5t0n80000gn/T/opencode/test_server_regions.sqlite")
    if db_path.exists():
        db_path.unlink()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add(ServerRegion(code="de", label="Germany", server_address="de.example.com", inbound_id=2, is_active=True))
        session.add(ServerRegion(code="fr", label="France", server_address="fr.example.com", inbound_id=3, is_active=False))
        await session.commit()

    async with session_factory() as session:
        repo = ServerRegionRepository(session)
        regions = await repo.get_active_regions()
        assert len(regions) == 1
        assert regions[0].code == "de"

    await engine.dispose()
