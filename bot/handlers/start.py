"""/start handler: register the user, show the welcome message, pick language."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.database import Database
from bot.i18n import get_text
from bot.keyboards.inline import language_keyboard, main_keyboard

logger = logging.getLogger(__name__)


def get_handler() -> CommandHandler:
    """Return the /start command handler."""
    return CommandHandler("start", start_command)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register the user, then show the welcome message (with language picker)."""
    db: Database = context.bot_data["db"]
    user = update.effective_user
    if user is None or update.effective_message is None:
        return

    first_name = user.first_name or user.username or str(user.id)

    # Check if user exists BEFORE adding them — new users need language picker.
    existing = await db.get_user(user.id)
    await db.add_user(user.id, user.username or "", first_name)
    await db.update_user_activity(user.id)

    lang = await db.get_user_language(user.id)
    needs_language = existing is None  # They didn't exist before add_user → brand new

    welcome = (await db.get_welcome_message()).format(
        user_name=first_name,
        date=date.today().isoformat(),
    )
    if "{bot_name}" in welcome:
        welcome = welcome.replace("{bot_name}", get_text("BOT_NAME", lang))

    reply_markup = language_keyboard() if needs_language else main_keyboard()
    await update.effective_message.reply_text(welcome, reply_markup=reply_markup)
