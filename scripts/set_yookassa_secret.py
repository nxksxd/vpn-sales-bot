"""Safely set YOOKASSA_SECRET_KEY in local .env without printing it.

Run from the repository root:
    python scripts/set_yookassa_secret.py
"""

from __future__ import annotations

from getpass import getpass
from pathlib import Path

ENV_PATH = Path(".env")
EXAMPLE_ENV_PATH = Path(".env.example")
SECRET_KEY = "YOOKASSA_SECRET_KEY"


def _load_env_lines() -> list[str]:
    if ENV_PATH.exists():
        return ENV_PATH.read_text().splitlines()
    if EXAMPLE_ENV_PATH.exists():
        return EXAMPLE_ENV_PATH.read_text().splitlines()
    raise SystemExit("Neither .env nor .env.example exists")


def _set_env_value(lines: list[str], key: str, value: str) -> list[str]:
    updated = False
    result: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            result.append(f"{key}={value}")
            updated = True
        else:
            result.append(line)
    if not updated:
        if result and result[-1] != "":
            result.append("")
        result.append(f"{key}={value}")
    return result


def main() -> None:
    secret = getpass("Paste YOOKASSA_SECRET_KEY (input hidden): ").strip()
    if not secret.startswith(("test_", "live_")):
        raise SystemExit("Secret key must start with test_ or live_")

    lines = _load_env_lines()
    lines = _set_env_value(lines, SECRET_KEY, secret)
    ENV_PATH.write_text("\n".join(lines) + "\n")
    ENV_PATH.chmod(0o600)
    print("YOOKASSA_SECRET_KEY saved to .env (value was not printed).")


if __name__ == "__main__":
    main()
