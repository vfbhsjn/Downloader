"""Inline keyboard builders. Every button callback_data is short and unique."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import get_text


def language_keyboard() -> InlineKeyboardMarkup:
    """Language selection keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa"),
                InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            ]
        ]
    )


def _main_buttons(buttons: list, back_data: str | None = None, max_cols: int = 2) -> InlineKeyboardMarkup:
    """Wrap buttons in rows of up to `max_cols`; optional trailing back button."""
    rows = [buttons[i : i + max_cols] for i in range(0, len(buttons), max_cols)]
    if back_data:
        rows.append([InlineKeyboardButton("🔙", callback_data=back_data)])
    return InlineKeyboardMarkup(rows)


def main_keyboard() -> InlineKeyboardMarkup:
    """Persistent command-like keyboard under a message."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠", callback_data="main")]]
    )


def help_keyboard_back() -> InlineKeyboardMarkup:
    """Keyboard shown under the help text."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙", callback_data="main")]]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    """Admin panel keyboard (6 buttons)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(get_text("BTN_ADMIN_STATS"), callback_data="admin_stats"),
                InlineKeyboardButton(get_text("BTN_ADMIN_TOP"), callback_data="admin_top"),
            ],
            [
                InlineKeyboardButton(get_text("BTN_ADMIN_BROADCAST"), callback_data="admin_broadcast"),
                InlineKeyboardButton(get_text("BTN_ADMIN_BAN"), callback_data="admin_ban"),
            ],
            [
                InlineKeyboardButton(get_text("BTN_ADMIN_UNBAN"), callback_data="admin_unban"),
                InlineKeyboardButton(get_text("BTN_ADMIN_SETTINGS"), callback_data="admin_settings"),
            ],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    """Settings submenu."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    get_text("BTN_ADMIN_SET_WELCOME"), callback_data="admin_set_welcome"
                )
            ],
            [InlineKeyboardButton(get_text("BTN_BACK"), callback_data="admin")],
        ]
    )


def quality_keyboard(url: str, convert_type: str) -> InlineKeyboardMarkup:
    """YouTube quality selection; MP3 row only for video downloads."""
    rows = [
        [
            InlineKeyboardButton(get_text("QUALITY_360"), callback_data=f"q:{url}:360"),
            InlineKeyboardButton(get_text("QUALITY_480"), callback_data=f"q:{url}:480"),
        ],
        [
            InlineKeyboardButton(get_text("QUALITY_720"), callback_data=f"q:{url}:720"),
            InlineKeyboardButton(get_text("QUALITY_1080"), callback_data=f"q:{url}:1080"),
        ],
    ]
    if convert_type != "mp3":
        rows.append(
            [
                InlineKeyboardButton(
                    get_text("BTN_MP3"), callback_data=f"q:{url}:mp3"
                )
            ]
        )
    rows.append([InlineKeyboardButton(get_text("BTN_BACK"), callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


def post_download_keyboard(url: str, platform: str, supports_mp3: bool = False) -> InlineKeyboardMarkup:
    """Buttons shown under a finished download. MP3 only for capable platforms."""
    rows = [
        [
            InlineKeyboardButton(get_text("BTN_REDOWNLOAD"), callback_data=f"rd:{platform}:{url}"),
        ],
    ]
    if supports_mp3:
        rows.append([
            InlineKeyboardButton(get_text("BTN_MP3"), callback_data=f"mp3:{platform}:{url}"),
        ])
    rows.append([
        InlineKeyboardButton(get_text("BTN_LINK"), callback_data=f"dl:{platform}:{url}"),
    ])
    return InlineKeyboardMarkup(rows)


def confirm_keyboard(back_data: str = "cancel") -> InlineKeyboardMarkup:
    """Yes/No confirmation keyboard."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(get_text("BTN_CONFIRM_YES"), callback_data="confirm_yes"),
                InlineKeyboardButton(get_text("BTN_CONFIRM_NO"), callback_data="confirm_no"),
            ]
        ]
    )


def back_only_keyboard() -> InlineKeyboardMarkup:
    """Single back button."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(get_text("BTN_BACK"), callback_data="cancel")]]
    )