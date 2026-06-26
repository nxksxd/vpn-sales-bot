from __future__ import annotations

import json
from pathlib import Path

from loguru import logger


def log_event(event: str, **fields: object) -> None:
    logger.info("event={} data={}", event, json.dumps(fields, ensure_ascii=False, default=str))


def ensure_directory(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def init_sentry() -> bool:
    """Initialise Sentry if a DSN is configured and the SDK is installed.

    Returns True when error reporting is active, False otherwise.
    """
    from bot.config import settings

    dsn = settings.sentry_dsn.strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return False

    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)
    logger.info("Sentry error reporting enabled")
    return True
