"""Link handler: detect the platform, run the service, send the file."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from bot import config
from bot.database import Database
from bot.i18n import get_text
from bot.keyboards.inline import quality_keyboard
from bot.services import get_service
from bot.services.base import DownloadError
from bot.services.direct_link import DirectLinkDownloader
from bot.utils import media_handler, url_parser, validators

logger = logging.getLogger(__name__)

# Platforms that can convert to MP3 via yt-dlp.
_MP3_CAPABLE = {"youtube", "soundcloud", "spotify"}


def get_handler() -> MessageHandler:
    """Return the message handler that processes any text with a link."""
    return MessageHandler(filters.TEXT & ~filters.COMMAND, process_link)


async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Full download flow for a user-sent link."""
    message = update.effective_message
    if message is None or message.text is None:
        return

    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None:
        return

    # Skip if admin_state handler already consumed this message.
    handled_ids = context.bot_data.get("_admin_handled_ids", set())
    if message.message_id in handled_ids:
        handled_ids.discard(message.message_id)
        return

    # Banned users cannot download anything.
    if await db.is_banned(user_id):
        reason = (await db.get_user(user_id) or {}).get("ban_reason")
        text = (
            get_text("BANNED_WITH_REASON", "fa").format(reason=reason)
            if reason
            else get_text("BANNED_MESSAGE", "fa")
        )
        await message.reply_text(text)
        return

    lang = await db.get_user_language(user_id)
    await db.update_user_activity(user_id)

    url = validators.extract_first_url(message.text)
    if not url:
        return

    platform = url_parser.detect_platform(url)
    if platform == url_parser.DIRECT:
        # Direct file fallback: check extension before proceeding.
        service = DirectLinkDownloader()
        try:
            info = await service.get_info(url, lang)
        except DownloadError as err:
            await message.reply_text(get_text(err.message, lang) if err.message in (
                "DIRECT_LINK_UNKNOWN_EXT",
            ) else err.message)
            return
        if info.get("too_large"):
            await message.reply_text(
                get_text("FILE_TOO_LARGE", lang).format(size=info.get("size_mb", 0))
            )
            return
    else:
        service = get_service(platform)
        if service is None:
            await message.reply_text(
                get_text("UNSUPPORTED_PLATFORM", lang) + "\n" + get_text("SUPPORTED_LIST", lang)
            )
            return

    # Show the processing message with the typing indicator.
    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
    await message.reply_text(get_text("PROCESSING", lang))

    try:
        if platform == "youtube":
            await _handle_youtube(update, context, service, url, lang)
        elif platform == "instagram":
            await _handle_instagram(update, context, service, url, lang)
        else:
            await _handle_generic(update, context, service, url, platform, lang)
    except DownloadError as err:
        await message.reply_text(get_text("DOWNLOAD_FAILED", lang).format(error=err.message))
        await db.add_download(user_id, platform, url, 0, 0)
    except Exception as err:
        logger.exception("Unexpected download error for %s", url)
        await message.reply_text(get_text("DOWNLOAD_FAILED", lang).format(error=str(err)))
        await db.add_download(user_id, platform, url, 0, 0)


async def _handle_youtube(update, context, service, url, lang) -> None:
    """YouTube flow: info first, then quality selection."""
    message = update.effective_message
    info = await service.get_info(url, lang)

    # Too long to download.
    if info.get("duration", 0) > config.MAX_DURATION:
        raise DownloadError(get_text("DURATION_LIMIT", lang).format(
            limit=config.MAX_DURATION // 60
        ))

    text = (
        get_text("INFO_VIDEO_TITLE", lang).format(title=info.get("title", ""))
        + "\n"
        + get_text("INFO_CHANNEL", lang).format(channel=info.get("channel", ""))
        + "\n"
        + get_text("INFO_DURATION", lang).format(
            duration=media_handler.format_seconds(info.get("duration", 0))
        )
        + "\n"
        + get_text("INFO_VIEWS", lang).format(views=info.get("views", 0))
        + "\n\n"
        + get_text("QUALITY_PROMPT", lang)
    )
    await message.reply_text(
        text,
        reply_markup=quality_keyboard(url, "video"),
    )


async def _handle_instagram(update, context, service, url, lang) -> None:
    """Instagram flow: fetch info, then download (carousel aware)."""
    message = update.effective_message
    info = await service.get_info(url, lang)

    if info.get("media_type") == "carousel" or (info.get("media_count") or 1) > 1:
        await message.reply_text(
            get_text("PREPARING_CAROUSEL", lang).format(count=info.get("media_count", 0))
        )

    await context.bot.send_chat_action(chat_id=message.chat_id, action="upload_video")
    result = await service.download(url, lang=lang)

    paths = result.get("paths") or [result.get("path")]
    paths = [p for p in paths if p]
    if not paths:
        raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="no file"))

    await _send_result(update, context, service, url, lang, result)


async def _handle_generic(update, context, service, url, platform, lang) -> None:
    """Non-YouTube, non-Instagram platforms: download and send."""
    message = update.effective_message
    await context.bot.send_chat_action(chat_id=message.chat_id, action="upload_document")
    result = await service.download(url, lang=lang)
    await _send_result(update, context, service, url, lang, result)


async def _send_result(update, context, service, url, lang, result) -> None:
    """Upload the downloaded file(s) and show the info + action buttons."""
    from bot.keyboards.inline import post_download_keyboard

    message = update.effective_message
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    paths = result.get("paths") or [result.get("path")]
    paths = [p for p in paths if p]
    file_size = sum(media_handler.get_file_size(p) for p in paths)
    file_size = file_size or result.get("file_size") or 0

    platform = result.get("platform") or service.platform
    keyboard = post_download_keyboard(url, platform, supports_mp3=platform in _MP3_CAPABLE)

    caption = (
        get_text("INFO_PLATFORM", lang).format(platform=url_parser.get_platform_label(platform))
        + "\n📅 "
        + date.today().isoformat()
    )

    try:
        for path in paths:
            ext = media_handler.get_ext(path)
            fsize = media_handler.get_file_size(path)
            file_caption = caption if len(paths) == 1 else f"📅 {date.today().isoformat()}"
            if media_handler.is_audio_file(path):
                await message.reply_audio(
                    open(path, "rb"),
                    caption=file_caption,
                    filename=media_handler.basename(path),
                )
            elif media_handler.is_video_file(path):
                await message.reply_video(
                    open(path, "rb"),
                    caption=file_caption,
                    supports_streaming=True,
                    filename=media_handler.basename(path),
                )
            elif ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                await message.reply_photo(open(path, "rb"), caption=file_caption)
            else:
                await message.reply_document(
                    open(path, "rb"),
                    caption=file_caption,
                    filename=media_handler.basename(path),
                )
        # Attach action buttons to the last sent file.
        await message.reply_text(
            get_text("DOWNLOAD_SUCCESS", lang),
            reply_markup=keyboard,
        )
        await db.add_download(user_id, result.get("platform") or "direct", url, file_size, 1)
    finally:
        for path in paths:
            media_handler.delete_file(path)
