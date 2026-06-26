from bot.config import settings


def test_flat_bonus_when_no_tiers() -> None:
    settings.referral_tiers_json = "[]"
    settings.referral_bonus_rub = 20
    assert settings.referral_bonus_for(1) == 20
    assert settings.referral_bonus_for(100) == 20
    assert settings.referral_total_earned(3) == 60


def test_tiered_bonus_escalates() -> None:
    settings.referral_bonus_rub = 20
    settings.referral_tiers_json = (
        '[{"min_referrals": 5, "bonus_rub": 30}, '
        '{"min_referrals": 20, "bonus_rub": 50}]'
    )
    assert settings.referral_bonus_for(1) == 20   # base, below first tier
    assert settings.referral_bonus_for(4) == 20
    assert settings.referral_bonus_for(5) == 30   # reaches tier 1
    assert settings.referral_bonus_for(19) == 30
    assert settings.referral_bonus_for(20) == 50  # reaches tier 2


def test_total_earned_sums_per_referral() -> None:
    settings.referral_bonus_rub = 20
    settings.referral_tiers_json = '[{"min_referrals": 3, "bonus_rub": 100}]'
    # referrals 1,2 -> 20 each; referral 3 -> 100
    assert settings.referral_total_earned(3) == 20 + 20 + 100


def test_malformed_tiers_falls_back_to_flat() -> None:
    settings.referral_bonus_rub = 15
    settings.referral_tiers_json = "not-json"
    assert settings.referral_bonus_for(10) == 15
