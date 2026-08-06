"""Translation helper: returns locale strings based on the user's language."""

from bot.locales import en, fa

_LANGUAGES = {
    "fa": fa,
    "en": en,
}


def get_text(key: str, lang: str = "fa") -> str:
    """Return the text for `key` in `lang`, falling back to Persian."""
    module = _LANGUAGES.get(lang, fa)
    value = getattr(module, key, None)
    if value is None and lang != "fa":
        value = getattr(fa, key, key)
    if value is None:
        return key
    return value
