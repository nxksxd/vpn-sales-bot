import datetime
import tempfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.config import settings
from bot.database.models import Base, Subscription, User, VpnKey
from bot.utils import crypto

_KEY = Fernet.generate_key().decode()


def _enable_encryption() -> None:
    settings.encryption_key = _KEY
    crypto._warned = False


def test_encrypt_decrypt_roundtrip() -> None:
    _enable_encryption()
    plaintext = "vless://abc-123@host:443?type=tcp#node"
    token = crypto.encrypt(plaintext)
    assert token != plaintext
    assert token.startswith("gAAAAA")  # Fernet token marker
    assert crypto.decrypt(token) == plaintext


def test_decrypt_legacy_plaintext_passthrough() -> None:
    _enable_encryption()
    # A value stored before encryption was enabled is not a valid token.
    assert crypto.decrypt("plain-legacy-value") == "plain-legacy-value"


def test_passthrough_without_key() -> None:
    settings.encryption_key = ""
    crypto._warned = False
    assert crypto.encrypt("secret") == "secret"
    assert crypto.decrypt("secret") == "secret"


@pytest.mark.asyncio
async def test_model_stores_ciphertext_returns_plaintext() -> None:
    _enable_encryption()
    db_path = Path(tempfile.mkdtemp()) / "test_encryption.sqlite"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    link = "vless://uuid@1.2.3.4:443#vpn"
    email = "user_42_deadbeef"

    async with session_factory() as session:
        session.add(User(telegram_id=42, referral_code="REF42"))
        await session.flush()
        sub = Subscription(
            user_id=42,
            plan_type="1m",
            price_rub=200,
            status="active",
            starts_at=datetime.datetime.utcnow(),
            expires_at=datetime.datetime.utcnow(),
            vless_link=link,
        )
        session.add(sub)
        await session.flush()
        session.add(
            VpnKey(
                subscription_id=sub.id,
                user_id=42,
                xui_client_id="cid-1",
                xui_inbound_id=1,
                email=email,
                vless_link=link,
            )
        )
        await session.commit()

    # Raw stored values must be ciphertext, not plaintext.
    async with engine.begin() as conn:
        raw_email = (
            await conn.execute(text("SELECT email FROM vpn_keys"))
        ).scalar_one()
        raw_link = (
            await conn.execute(text("SELECT vless_link FROM vpn_keys"))
        ).scalar_one()
    assert raw_email != email and raw_email.startswith("gAAAAA")
    assert raw_link != link and raw_link.startswith("gAAAAA")

    # ORM reads transparently decrypt.
    async with session_factory() as session:
        key = (
            await session.execute(text("SELECT id FROM vpn_keys"))
        ).scalar_one()
        obj = await session.get(VpnKey, key)
        assert obj is not None
        assert obj.email == email
        assert obj.vless_link == link

    await engine.dispose()
