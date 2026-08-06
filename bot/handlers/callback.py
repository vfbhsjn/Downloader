"""CallbackQuery handler: languages, admin panel, quality and post-download buttons."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot import config
from bot.database import Database
from bot.handlers.download import _send_result
from bot.i18n import get_text
from bot.keyboards.inline import admin_keyboard, main_keyboard, settings_keyboard
from bot.services import get_service
from bot.services.base import DownloadError
from bot.utils import url_parser

logger = logging.getLogger(__name__)


def get_handler() -> CallbackQueryHandler:
    """Return the callback query handler."""
    return CallbackQueryHandler(handle_callback)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route every callback_data to its action."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or query.message is None:
        return

    lang = await db.get_user_language(user_id)
    data = query.data or ""

    if data.startswith("lang_"):
        await _pick_language(query, context, data)
        return
    if data == "cancel":
        await query.message.delete()
        return
    if data == "main":
        await _show_main(query, context)
        return

    if _is_admin_callback(data):
        if user_id not in config.ADMIN_IDS:
            await query.message.reply_text(get_text("NO_ACCESS", lang))
            return
        await _route_admin(query, context, data, lang)
        return

    if data.startswith("q:"):
        await _handle_quality(query, context, data, lang)
        return
    if data.startswith("rd:"):
        await _handle_re_download(query, context, data, lang)
        return
    if data.startswith("mp3:"):
        await _handle_mp3(query, context, data, lang)
        return
    if data.startswith("dl:"):
        await _handle_direct_link(query, context, data, lang)
        return

    logger.info("Unhandled callback: %s", data)


def _is_admin_callback(data: str) -> bool:
    return data in {
        "admin",
        "admin_stats",
        "admin_top",
        "admin_broadcast",
        "admin_ban",
        "admin_unban",
        "admin_settings",
        "admin_set_welcome",
        "confirm_yes",
        "confirm_no",
    }


# ---------------------------------------------------------- language


async def _pick_language(query, context, data: str) -> None:
    """Handle the lang_fa / lang_en callbacks."""
    db: Database = context.bot_data["db"]
    user_id = query.from_user.id
    selected = data.split("_")[1]
    await db.set_user_language(user_id, selected)
    text = (
        get_text("LANG_SELECTED_FA", selected)
        if selected == "fa"
        else get_text("LANG_SELECTED_EN", selected)
    )
    await query.message.reply_text(text)


async def _show_main(query, context) -> None:
    """Show the welcome message with the main keyboard."""
    db: Database = context.bot_data["db"]
    user_id = query.from_user.id
    lang = await db.get_user_language(user_id)
    first_name = query.from_user.first_name or query.from_user.username or str(user_id)
    welcome = (await db.get_welcome_message()).format(
        user_name=first_name,
        date=date.today().isoformat(),
    )
    if "{bot_name}" in welcome:
        welcome = welcome.replace("{bot_name}", get_text("BOT_NAME", lang))
    await query.message.reply_text(welcome, reply_markup=main_keyboard())


# ---------------------------------------------------------- admin


async def _route_admin(query, context, data: str, lang: str) -> None:
    """Dispatch admin callback_data to its method."""
    if data == "admin":
        await _admin_panel(query, lang)
    elif data == "admin_stats":
        await _admin_stats(query, context, lang)
    elif data == "admin_top":
        await _admin_top(query, context, lang)
    elif data == "admin_broadcast":
        await _admin_broadcast(query, context, lang)
    elif data == "admin_ban":
        await _admin_ban(query, context, lang)
    elif data == "admin_unban":
        await _admin_unban(query, context, lang)
    elif data == "admin_settings":
        await _admin_settings(query, context, lang)
    elif data == "admin_set_welcome":
        await _admin_set_welcome(query, context, lang)
    elif data == "confirm_yes":
        await _broadcast_confirm_yes(query, context, lang)
    elif data == "confirm_no":
        await _broadcast_confirm_no(query, context, lang)


async def _admin_panel(query, lang: str) -> None:
    await query.message.edit_text(get_text("ADMIN_PANEL", lang), reply_markup=admin_keyboard())


async def _admin_stats(query, context, lang: str) -> None:
    db: Database = context.bot_data["db"]
    users = await db.get_total_users()
    downloads = await db.get_total_downloads()
    today = await db.get_today_downloads()
    week = await db.get_week_downloads()
    top = await db.get_top_platforms(1)
    top_name = top[0]["platform"] if top else "—"
    active = await db.get_most_active_user()
    active_name = (
        active["first_name"] or active["username"] or str(active["user_id"])
        if active
        else "—"
    )

    text = (
        get_text("STATS_USERS", lang).format(count=users)
        + "\n"
        + get_text("STATS_DOWNLOADS", lang).format(count=downloads)
        + "\n"
        + get_text("STATS_TODAY", lang).format(count=today)
        + "\n"
        + get_text("STATS_WEEK", lang).format(count=week)
        + "\n"
        + get_text("STATS_TOP", lang).format(
            platform=url_parser.get_platform_label(top_name)
        )
        + "\n"
        + get_text("STATS_ACTIVE", lang).format(name=active_name)
    )
    await query.message.edit_text(text, reply_markup=back_only("admin"))


async def _admin_top(query, context, lang: str) -> None:
    db: Database = context.bot_data["db"]
    rows = await db.get_top_platforms(5)
    if not rows:
        text = get_text("TOP_EMPTY", lang)
    else:
        lines = [get_text("TOP_TITLE", lang)]
        for i, row in enumerate(rows, start=1):
            label = url_parser.get_platform_label(row["platform"])
            lines.append(
                get_text("TOP_FORMAT", lang).format(
                    rank=i, platform=label, count=row["count"]
                )
            )
        text = "\n".join(lines)
    await query.message.edit_text(text, reply_markup=back_only("admin"))


async def _admin_broadcast(query, context, lang: str) -> None:
    context.bot_data["pending_broadcast"] = {query.from_user.id: "waiting_text"}
    await query.message.edit_text(
        get_text("BROADCAST_PROMPT", lang), reply_markup=back_only("admin")
    )


async def _admin_ban(query, context, lang: str) -> None:
    context.bot_data["pending_ban"] = {query.from_user.id: "waiting_id"}
    await query.message.edit_text(
        get_text("BAN_PROMPT", lang), reply_markup=back_only("admin")
    )


async def _admin_unban(query, context, lang: str) -> None:
    context.bot_data["pending_unban"] = {query.from_user.id: "waiting_id"}
    await query.message.edit_text(
        get_text("UNBAN_PROMPT", lang), reply_markup=back_only("admin")
    )


async def _admin_settings(query, context, lang: str) -> None:
    db: Database = context.bot_data["db"]
    welcome = await db.get_welcome_message()
    text = (
        get_text("SETTINGS_TITLE", lang)
        + "\n\n"
        + get_text("SETTINGS_WELCOME_CURRENT", lang).format(text=welcome[:200])
    )
    await query.message.edit_text(text, reply_markup=settings_keyboard())


async def _admin_set_welcome(query, context, lang: str) -> None:
    context.bot_data["pending_setwelcome"] = {query.from_user.id: "waiting_text"}
    await query.message.edit_text(
        get_text("SETWELCOME_PROMPT", lang), reply_markup=back_only("admin")
    )


async def _broadcast_confirm_yes(query, context, lang: str) -> None:
    db: Database = context.bot_data["db"]
    pending = context.bot_data.get("pending_broadcast", {})
    payload = pending.get("info")
    if not payload:
        await query.message.edit_text(get_text("BROADCAST_CANCELLED", lang))
        return

    users = await db.get_all_user_ids()
    sent = failed = 0
    await query.message.edit_text(get_text("BROADCAST_STARTED", lang))
    for uid in users:
        if uid == query.from_user.id:
            continue
        try:
            if payload.get("photo"):
                await context.bot.send_photo(
                    uid, photo=payload["photo"], caption=payload.get("text") or ""
                )
            elif payload.get("video"):
                await context.bot.send_video(
                    uid, video=payload["video"], caption=payload.get("text") or ""
                )
            elif payload.get("document"):
                await context.bot.send_document(
                    uid, document=payload["document"], caption=payload.get("text") or ""
                )
            else:
                await context.bot.send_message(uid, payload.get("text") or "")
            sent += 1
        except Exception:
            failed += 1

    await db.add_broadcast(query.from_user.id, payload.get("text") or "", sent, failed)
    await query.message.reply_text(
        get_text("BROADCAST_SENT", lang).format(count=sent)
        + "\n"
        + get_text("BROADCAST_FAILED", lang).format(count=failed)
    )
    context.bot_data["pending_broadcast"] = {}


async def _broadcast_confirm_no(query, context, lang: str) -> None:
    await query.message.edit_text(get_text("BROADCAST_CANCELLED", lang))
    context.bot_data["pending_broadcast"] = {}


def back_only(back_data: str):
    """Small keyboard with a single back button."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(get_text("BTN_BACK"), callback_data=back_data)]]
    )


# ------------------------------------------- quality / post-download


async def _handle_quality(query, context, data: str, lang: str) -> None:
    """User picked a YouTube quality; download and send."""
    parts = data.split(":")
    if len(parts) < 4:
        return
    y_url = ":".join(parts[1:-1])
    quality = parts[-1]

    await query.message.edit_text(get_text("PROCESSING", lang))
    service = get_service("youtube")
    try:
        result = await service.download(y_url, quality=quality, lang=lang)
    except DownloadError as err:
        await query.message.reply_text(
            get_text("DOWNLOAD_FAILED", lang).format(error=err.message)
        )
        return
    await _send_result(_from_query(query), context, service, y_url, lang, result)


async def _handle_direct_link(query, context, data: str, lang: str) -> None:
    """'dl:' button: give the direct download URL for the content."""
    parts = _split_callback(data, "dl")
    platform, dl_url = parts[0], parts[1]

    # For direct-file links the URL itself is the download link.
    if platform == "direct":
        await query.message.reply_text(
            get_text("DIRECT_LINK_READY", lang).format(url=dl_url)
        )
        return

    # For social platforms, try to resolve the direct media URL via yt-dlp.
    service = _service_for(platform)
    try:
        info = await service.get_info(dl_url, lang)
    except Exception:
        info = {}
    direct_url = (
        info.get("direct_url")
        or (info.get("url") if isinstance(info.get("url"), str) and info["url"].startswith("http") else "")
        or dl_url
    )
    await query.message.reply_text(
        get_text("DIRECT_LINK_READY", lang).format(url=direct_url)
    )


async def _handle_re_download(query, context, data: str, lang: str) -> None:
    """'rd:' button: download the same link again."""
    parts = _split_callback(data, "rd")
    platform, redl_url = parts[0], parts[1]
    await query.message.edit_text(get_text("PROCESSING", lang))

    service = _service_for(platform)
    try:
        result = await service.download(redl_url, lang=lang)
    except DownloadError as err:
        await query.message.reply_text(
            get_text("DOWNLOAD_FAILED", lang).format(error=err.message)
        )
        return
    await _send_result(_from_query(query), context, service, redl_url, lang, result)


async def _handle_mp3(query, context, data: str, lang: str) -> None:
    """'mp3:' button → re-download the content as MP3."""
    _MP3_CAPABLE = {"youtube", "soundcloud", "spotify"}
    parts = _split_callback(data, "mp3")
    platform, mp3_url = parts[0], parts[1]
    if platform not in _MP3_CAPABLE:
        await query.message.reply_text(get_text("MP3_FAILED", lang))
        return
    await query.message.edit_text(get_text("PROCESSING", lang))
    service = get_service(platform)
    try:
        result = await service.download(mp3_url, quality="mp3", lang=lang)
    except DownloadError as err:
        await query.message.reply_text(
            get_text("DOWNLOAD_FAILED", lang).format(error=err.message)
        )
        return
    await _send_result(_from_query(query), context, service, mp3_url, lang, result)


def _service_for(platform: str):
    """Return the downloader for a platform slug (direct as fallback)."""
    return get_service(platform)


def _split_callback(data: str, prefix: str) -> tuple:
    """Split a `prefix:platform:url` callback into (platform, url)."""
    if not data.startswith(prefix + ":"):
        return "", ""
    platform, _, rest = data[len(prefix) + 1 :].partition(":")
    return platform, rest


def _from_query(query):
    """Build an Update-like adapter so sending helpers can reuse query data."""

    class _Adapter:
        def __init__(self, q):
            self._q = q

        @property
        def effective_message(self):
            return self._q.message

        @property
        def effective_user(self):
            return self._q.from_user

    return _Adapter(query)
