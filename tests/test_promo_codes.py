from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.models import Base, PromoCode
from bot.database.repositories.promo_code import PromoCodeRepository


@pytest.mark.asyncio
async def test_promo_code_repository_increments_usage_and_deactivates() -> None:
    db_path = Path("/var/folders/kl/frv_wd1s22l2_2j521g5t0n80000gn/T/opencode/test_promos.sqlite")
    if db_path.exists():
        db_path.unlink()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add(PromoCode(code="PROMO10", discount_percent=10, is_active=True, usage_limit=1, used_count=0))
        await session.commit()

    async with session_factory() as session:
        repo = PromoCodeRepository(session)
        promo = await repo.get_active_by_code("PROMO10")
        assert promo is not None
        await repo.increment_usage(promo.id)
        updated = await repo.get_active_by_code("PROMO10")
        assert updated is None

    await engine.dispose()
