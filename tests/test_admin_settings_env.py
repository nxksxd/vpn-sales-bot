from pathlib import Path

import pytest

from bot.handlers.admin import settings as admin_settings


def test_update_env_file_quotes_shell_sensitive_values(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(admin_settings, "BASE_DIR", tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("XUI_URL=http://old.example\nUNCHANGED=value\n")

    admin_settings._update_env_file("XUI_URL", "https://new.example/a path?x=1&y=2")

    assert env_path.read_text() == (
        "XUI_URL='https://new.example/a path?x=1&y=2'\n"
        "UNCHANGED=value\n"
    )


@pytest.mark.parametrize("bad_value", ["line1\nline2", "line1\rline2", "bad\x00value"])
def test_update_env_file_rejects_multiline_and_nul_values(
    tmp_path: Path,
    monkeypatch,
    bad_value: str,
) -> None:
    monkeypatch.setattr(admin_settings, "BASE_DIR", tmp_path)

    with pytest.raises(ValueError, match="переносы строк или NUL"):
        admin_settings._update_env_file("XUI_PASSWORD", bad_value)

    assert not (tmp_path / ".env").exists()
