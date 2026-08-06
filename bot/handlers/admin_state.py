"""Admin state machine: intercepts text messages when the admin is waiting
for input (broadcast text, ban ID, unban ID, welcome message).

Runs in group=0 so it processes admin pending states before the
download handler in group=1.  When it handles a message, it marks
the message ID so the download handler can skip it.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from bot import config
from bot.database import Database
from bot.i18n import get_text

logger = logging.getLogger(__name__)


def get_handler() -> MessageHandler:
    """Return the admin state handler (filters.TEXT, group=0)."""
    return MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_state)


async def handle_admin_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if the user is an admin in a pending state; if so, process the message."""
    message = update.effective_message
    if message is None or message.text is None:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None:
        return

    if user_id not in config.ADMIN_IDS:
        return

    db: Database = context.bot_data["db"]
    lang = await db.get_user_language(user_id)
    pending = context.bot_data
    handled = False

    # --- broadcast: waiting for the message text ---
    if pending.get("pending_broadcast", {}).get(user_id) == "waiting_text":
        text = message.text.strip()
        if not text:
            return

        users = await db.get_all_user_ids()
        total = len([uid for uid in users if uid != user_id])

        if total == 0:
            await message.reply_text(get_text("BROADCAST_NO_USERS", lang))
            pending["pending_broadcast"] = {}
            return

        pending["pending_broadcast"][user_id] = "confirming"
        pending["pending_broadcast"]["info"] = {
            "text": text,
            "photo": None,
            "video": None,
            "document": None,
        }
        from bot.keyboards.inline import confirm_keyboard
        await message.reply_text(
            get_text("BROADCAST_CONFIRM", lang).format(count=total),
            reply_markup=confirm_keyboard(),
        )
        handled = True

    # --- ban: waiting for user ID ---
    elif pending.get("pending_ban", {}).get(user_id) == "waiting_id":
        text = message.text.strip()
        parts = text.split("|", 1)
        try:
            target_id = int(parts[0].strip())
        except ValueError:
            await message.reply_text(get_text("BAN_INVALID_ID", lang))
            pending["pending_ban"] = {}
            return

        if target_id == user_id:
            await message.reply_text(get_text("BAN_SELF", lang))
            pending["pending_ban"] = {}
            return

        reason = parts[1].strip() if len(parts) > 1 else None
        await db.ban_user(target_id, reason, user_id)
        try:
            user_lang = await db.get_user_language(target_id)
            reason_text = (
                get_text("BANNED_WITH_REASON", user_lang).format(reason=reason)
                if reason
                else get_text("BANNED_MESSAGE", user_lang)
            )
            await context.bot.send_message(target_id, reason_text)
        except Exception:
            pass
        await message.reply_text(get_text("BAN_SUCCESS", lang).format(id=target_id))
        pending["pending_ban"] = {}
        handled = True

    # --- unban: waiting for user ID ---
    elif pending.get("pending_unban", {}).get(user_id) == "waiting_id":
        text = message.text.strip()
        try:
            target_id = int(text)
        except ValueError:
            await message.reply_text(get_text("BAN_INVALID_ID", lang))
            pending["pending_unban"] = {}
            return

        if not await db.is_banned(target_id):
            await message.reply_text(
                get_text("UNBAN_NOT_FOUND", lang).format(id=target_id)
            )
            pending["pending_unban"] = {}
            return

        await db.unban_user(target_id)
        await message.reply_text(get_text("UNBAN_SUCCESS", lang).format(id=target_id))
        pending["pending_unban"] = {}
        handled = True

    # --- setwelcome: waiting for the new welcome text ---
    elif pending.get("pending_setwelcome", {}).get(user_id) == "waiting_text":
        text = message.text.strip()
        if not text:
            return

        await db.set_welcome_message(text)
        await message.reply_text(get_text("SETWELCOME_SUCCESS", lang))
        pending["pending_setwelcome"] = {}
        handled = True

    # Prevent the download handler (group=1) from also processing this message.
    if handled:
        context.bot_data.setdefault("_admin_handled_ids", set()).add(message.message_id)
