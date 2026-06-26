from bot.config import Settings


def test_rub_to_stars_rounds_up() -> None:
    settings = Settings(
        bot_token="test",
        database_url="sqlite+aiosqlite:///./test.db",
        stars_to_rub_rate=2.0,
    )
    assert settings.rub_to_stars(201) == 101


def test_stars_to_rub_rounds_down() -> None:
    settings = Settings(
        bot_token="test",
        database_url="sqlite+aiosqlite:///./test.db",
        stars_to_rub_rate=2.5,
    )
    assert settings.stars_to_rub(3) == 7


def test_plans_are_derived_in_rubles_and_stars() -> None:
    settings = Settings(
        bot_token="test",
        database_url="sqlite+aiosqlite:///./test.db",
        plan_1m_rub=200,
        plan_3m_rub=500,
        plan_6m_rub=900,
        plan_12m_rub=1600,
        stars_to_rub_rate=2.0,
    )

    plans = settings.plans

    assert plans["1m"]["rub"] == 200
    assert plans["1m"]["stars"] == 100
    assert plans["3m"]["discount"] == 17
    assert plans["12m"]["days"] == 365
