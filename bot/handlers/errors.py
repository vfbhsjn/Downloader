"""Global error handler: log everything, answer users with a friendly message."""

import logging
import traceback

from telegram import Update
from telegram.ext import ContextTypes

from bot.database import Database
from bot.i18n import get_text

logger = logging.getLogger(__name__)


def get_handler():
    """Return the error handler callable (passed to add_error_handler)."""
    return error_handler


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the full traceback and notify the affected user if possible."""
    logger.error("Unhandled error: %s", traceback.format_exc())

    if not isinstance(update, Update) or update.effective_message is None:
        return
    if update.effective_user is None:
        return

    try:
        db: Database = context.bot_data["db"]
        lang = await db.get_user_language(update.effective_user.id)
        text = get_text("DOWNLOAD_FAILED", lang).format(
            error=str(context.error or "unknown error")
        )
        await update.effective_message.reply_text(text)
    except Exception:
        logger.exception("Failed to notify user about the error")


