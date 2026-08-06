"""Input validation helpers."""

import re

_FULL_URL_RE = re.compile(r"https?://\S+")
_BARE_URL_RE = re.compile(
    r"(?:www\.)?"
    r"(?:instagram\.com|instagr\.am|youtube\.com|youtu\.be|tiktok\.com|"
    r"vm\.tiktok\.com|vt\.tiktok\.com|m\.tiktok\.com|"
    r"open\.spotify\.com|spotify\.link|pinterest\.com|pin\.it|"
    r"soundcloud\.com|on\.soundcloud\.com|twitter\.com|x\.com|"
    r"aparat\.com|reddit\.com|redd\.it|v\.redd\.it|"
    r"clips\.twitch\.com|twitch\.tv|facebook\.com|fb\.watch|fb\.com|"
    r"rumble\.com|rumble\.media)"
    r"(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)


def is_valid_url(url: str) -> bool:
    """Check that the input looks like a full HTTP(S)/FTP URL."""
    return bool(re.match(r"^(?:https?|ftp)://[^\s<>\"']+$", url.strip()))


def extract_first_url(text: str) -> str | None:
    """Return the first URL found inside arbitrary user text.

    Handles both full URLs (https://...) and bare social-media domains
    (e.g. tiktok.com/...).
    """
    # Try full URLs first — they're unambiguous.
    match = _FULL_URL_RE.search(text)
    if match:
        return match.group(0)

    # Try bare social-media URLs (no protocol).
    match = _BARE_URL_RE.search(text)
    if match:
        raw = match.group(0)
        return "https://" + raw

    return None
