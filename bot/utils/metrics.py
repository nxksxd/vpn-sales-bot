"""Lightweight in-process metrics counters.

Process-local counters incremented at key events (payments, 3x-ui errors).
Exposed via :func:`snapshot` for the admin stats screen and periodic logs.
Not a replacement for Prometheus, but gives at-a-glance operational signal
without external infrastructure. Counters reset on process restart.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

PAYMENTS_SUCCEEDED = "payments_succeeded"
PAYMENTS_FAILED = "payments_failed"
XUI_ERRORS = "xui_errors"

_counters: dict[str, int] = defaultdict(int)
_lock = Lock()


def inc(name: str, amount: int = 1) -> None:
    with _lock:
        _counters[name] += amount


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counters)


def reset() -> None:
    with _lock:
        _counters.clear()
