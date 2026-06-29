from bot.keyboards.user_kb import (
    MENU_BTN_BUY,
    MENU_BTN_GUIDE,
    MENU_BTN_KEY,
    MENU_BTN_PROFILE,
    MENU_BTN_REF,
    MENU_BTN_SETTINGS,
    MENU_BTN_SUBS,
    MENU_BTN_SUPPORT,
    MENU_BTN_TOPUP,
    persistent_menu_kb,
)


def test_persistent_menu_removes_key_button_and_adds_support() -> None:
    keyboard = persistent_menu_kb().keyboard
    labels = [[button.text for button in row] for row in keyboard]

    assert labels == [
        [MENU_BTN_PROFILE, MENU_BTN_REF],
        [MENU_BTN_SUBS, MENU_BTN_SETTINGS],
        [MENU_BTN_TOPUP, MENU_BTN_GUIDE],
        [MENU_BTN_BUY, MENU_BTN_SUPPORT],
    ]
    assert MENU_BTN_KEY not in [label for row in labels for label in row]
