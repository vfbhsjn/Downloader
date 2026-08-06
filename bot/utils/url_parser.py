"""URL parsing: detect which platform a link belongs to via regex."""

import re

# Platform slugs used across services, handlers and the database.
INSTAGRAM = "instagram"
YOUTUBE = "youtube"
TIKTOK = "tiktok"
SPOTIFY = "spotify"
PINTEREST = "pinterest"
SOUNDCLOUD = "soundcloud"
TWITTER = "twitter"
APARAT = "aparat"
REDDIT = "reddit"
TWITCH = "twitch"
FACEBOOK = "facebook"
RUMBLE = "rumble"
DIRECT = "direct"

_PATTERNS = {
    INSTAGRAM: re.compile(
        r"^(?:https?://)?(?:www\.)?(?:instagram\.com|instagr\.am)/", re.IGNORECASE
    ),
    YOUTUBE: re.compile(
        r"^(?:https?://)?(?:(?:www\.|m\.|music\.)?youtube\.com|youtu\.be)/",
        re.IGNORECASE,
    ),
    TIKTOK: re.compile(
        r"^(?:https?://)?(?:(?:www\.|m\.)?tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/",
        re.IGNORECASE,
    ),
    SPOTIFY: re.compile(
        r"^(?:https?://)?(?:open\.spotify\.com|spotify\.link)/", re.IGNORECASE
    ),
    PINTEREST: re.compile(
        r"^(?:https?://)?(?:(?:www\.)?pinterest\.com|pin\.it)/", re.IGNORECASE
    ),
    SOUNDCLOUD: re.compile(
        r"^(?:https?://)?(?:(?:www\.)?soundcloud\.com|on\.soundcloud\.com)/",
        re.IGNORECASE,
    ),
    TWITTER: re.compile(
        r"^(?:https?://)?(?:(?:www\.)?twitter\.com|x\.com)/", re.IGNORECASE
    ),
    APARAT: re.compile(
        r"^(?:https?://)?(?:www\.)?aparat\.com/", re.IGNORECASE
    ),
    REDDIT: re.compile(
        r"^(?:https?://)?(?:(?:www\.)?reddit\.com|redd\.it|v\.redd\.it)/",
        re.IGNORECASE,
    ),
    TWITCH: re.compile(
        r"^(?:https?://)?(?:(?:www\.)?twitch\.tv|clips\.twitch\.tv)/", re.IGNORECASE
    ),
    FACEBOOK: re.compile(
        r"^(?:https?://)?(?:(?:www\.)?facebook\.com|fb\.watch|fb\.com)/",
        re.IGNORECASE,
    ),
    RUMBLE: re.compile(
        r"^(?:https?://)?(?:(?:www\.)?rumble\.com|rumble\.media)/", re.IGNORECASE
    ),
}

# Ordered as listed on the bot's platform cards.
_PLATFORM_ORDER = [
    INSTAGRAM,
    YOUTUBE,
    TIKTOK,
    SPOTIFY,
    PINTEREST,
    SOUNDCLOUD,
    TWITTER,
    APARAT,
    REDDIT,
    TWITCH,
    FACEBOOK,
    RUMBLE,
]

_PLATFORM_LABELS = {
    INSTAGRAM: "📸 اینستاگرام / Instagram",
    YOUTUBE: "🎬 یوتیوب / YouTube",
    TIKTOK: "📱 تیک‌تاک / TikTok",
    SPOTIFY: "🎵 اسپاتیفای / Spotify",
    PINTEREST: "📌 پینترست / Pinterest",
    SOUNDCLOUD: "🎧 ساندکلاد / SoundCloud",
    TWITTER: "🐦 توییتر / Twitter",
    APARAT: "🎥 آپارات / Aparat",
    REDDIT: "🟠 Reddit",
    TWITCH: "🟣 Twitch",
    FACEBOOK: "🔵 Facebook",
    RUMBLE: "⚫ Rumble",
    DIRECT: "🔗 لینک مستقیم / Direct",
}


def _normalize(url: str) -> str:
    url = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "http://" + url
    return url


def detect_platform(url: str) -> str:
    """Return the platform slug for `url`, or DIRECT as fallback."""
    url = _normalize(url)
    for platform in _PLATFORM_ORDER:
        if _PATTERNS[platform].match(url):
            return platform
    return DIRECT


def get_platform_label(platform: str) -> str:
    """Human-readable label for a platform slug."""
    return _PLATFORM_LABELS.get(platform, platform)


def get_supported_list() -> list:
    """Ordered list of all platform slugs."""
    return list(_PLATFORM_ORDER) + [DIRECT]
