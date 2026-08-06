"""/help handler: show usage instructions in the user's language."""

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot.database import Database
from bot.i18n import get_text
from bot.keyboards.inline import help_keyboard_back

logger = logging.getLogger(__name__)


def get_handler() -> CommandHandler:
    """Return the /help command handler."""
    return CommandHandler("help", help_command)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the localized help text."""
    if update.effective_message is None:
        return
    db: Database = context.bot_data["db"]
    lang = await db.get_user_language(update.effective_user.id) if update.effective_user else "fa"
    text = get_text("HELP_MESSAGE", lang).format(bot_name=get_text("BOT_NAME", lang))
    await update.effective_message.reply_text(text, reply_markup=help_keyboard_back())
