"""Admin commands: /admin, /stats, /top, /broadcast, /ban, /unban, /setwelcome, /language."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from bot import config
from bot.database import Database
from bot.i18n import get_text
from bot.keyboards.inline import admin_keyboard, language_keyboard
from bot.utils import url_parser

logger = logging.getLogger(__name__)


def get_handler() -> CommandHandler:
    """Return a handler covering every admin/utility command."""
    return CommandHandler(
        [
            "admin",
            "stats",
            "top",
            "broadcast",
            "ban",
            "unban",
            "setwelcome",
            "language",
        ],
        dispatch,
    )


async def dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route a command to its implementation."""
    if update.effective_message is None:
        return
    command = update.effective_message.text.lstrip("/").split(" ")[0].split("@")[0]
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None:
        return
    lang = await db.get_user_language(user_id)

    if command == "language":
        await _language(update, lang)
        return

    if user_id not in config.ADMIN_IDS:
        await update.effective_message.reply_text(get_text("NO_ACCESS", lang))
        return

    if command == "admin":
        await update.effective_message.reply_text(
            get_text("ADMIN_PANEL", lang), reply_markup=admin_keyboard()
        )
    elif command == "stats":
        await _stats(update, context, lang)
    elif command == "top":
        await _top(update, context, lang)
    elif command == "broadcast":
        await _broadcast(update, context, lang)
    elif command == "ban":
        await _ban(update, context, lang)
    elif command == "unban":
        await _unban(update, context, lang)
    elif command == "setwelcome":
        await _setwelcome(update, context, lang)


# ----------------------------------------------------------- commands


async def _language(update: Update, lang: str) -> None:
    await update.effective_message.reply_text(
        get_text("LANG_SELECT_MESSAGE", lang), reply_markup=language_keyboard()
    )


async def _stats(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
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
    await update.effective_message.reply_text(text)


async def _top(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    db: Database = context.bot_data["db"]
    rows = await db.get_top_platforms(5)
    if not rows:
        await update.effective_message.reply_text(get_text("TOP_EMPTY", lang))
        return
    lines = [get_text("TOP_TITLE", lang)]
    for i, row in enumerate(rows, start=1):
        label = url_parser.get_platform_label(row["platform"])
        lines.append(
            get_text("TOP_FORMAT", lang).format(
                rank=i, platform=label, count=row["count"]
            )
        )
    await update.effective_message.reply_text("\n".join(lines))


async def _broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    context.bot_data["pending_broadcast"] = {update.effective_user.id: "waiting_text"}
    await update.effective_message.reply_text(get_text("BROADCAST_PROMPT", lang))


async def _ban(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    args = (update.effective_message.text or "").split()
    if len(args) > 1:
        target = args[1].strip()
        try:
            target_id = int(target)
        except ValueError:
            await update.effective_message.reply_text(get_text("BAN_INVALID_ID", lang))
            return
        if target_id == update.effective_user.id:
            await update.effective_message.reply_text(get_text("BAN_SELF", lang))
            return
        await _do_ban(update, context, target_id, lang)
        return
    context.bot_data["pending_ban"] = {update.effective_user.id: "waiting_id"}
    await update.effective_message.reply_text(get_text("BAN_PROMPT", lang))


async def _unban(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    args = (update.effective_message.text or "").split()
    if len(args) > 1:
        try:
            target_id = int(args[1].strip())
        except ValueError:
            await update.effective_message.reply_text(get_text("BAN_INVALID_ID", lang))
            return
        await _do_unban(update, context, target_id, lang)
        return
    context.bot_data["pending_unban"] = {update.effective_user.id: "waiting_id"}
    await update.effective_message.reply_text(get_text("UNBAN_PROMPT", lang))


async def _setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    args = (update.effective_message.text or "").split(" ", 1)
    if len(args) > 1 and args[1].strip():
        db: Database = context.bot_data["db"]
        await db.set_welcome_message(args[1].strip())
        await update.effective_message.reply_text(get_text("SETWELCOME_SUCCESS", lang))
        return
    context.bot_data["pending_setwelcome"] = {update.effective_user.id: "waiting_text"}
    await update.effective_message.reply_text(get_text("SETWELCOME_PROMPT", lang))


# ----------------------------------------------------------- helpers


async def _do_ban(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int, lang: str
) -> None:
    db: Database = context.bot_data["db"]
    if target_id == update.effective_user.id:
        await update.effective_message.reply_text(get_text("BAN_SELF", lang))
        return
    await db.ban_user(target_id, None, update.effective_user.id)
    try:
        await context.bot.send_message(
            target_id, get_text("BANNED_MESSAGE", await db.get_user_language(target_id))
        )
    except Exception:
        pass
    await update.effective_message.reply_text(get_text("BAN_SUCCESS", lang).format(id=target_id))


async def _do_unban(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int, lang: str
) -> None:
    db: Database = context.bot_data["db"]
    if not await db.is_banned(target_id):
        await update.effective_message.reply_text(get_text("UNBAN_NOT_FOUND", lang).format(id=target_id))
        return
    await db.unban_user(target_id)
    await update.effective_message.reply_text(get_text("UNBAN_SUCCESS", lang).format(id=target_id))
