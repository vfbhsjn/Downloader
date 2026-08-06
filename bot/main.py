"""Application entry point: logging, database, handlers and polling."""

import logging
import sys

from telegram import BotCommand
from telegram.ext import ApplicationBuilder

from bot import config
from bot.database import Database
from bot.handlers import admin, admin_state, callback, download, errors, help as help_handler, start


def setup_logging() -> None:
    """Configure console + file logging."""
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # File logging is best-effort; console keeps working without it.
        pass

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    if not config.BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set. Create a .env file from .env.example")
        sys.exit(1)

    db = Database()
    app = (
        ApplicationBuilder()
        .token(config.BOT_TOKEN)
        .post_init(startup)
        .build()
    )

    app.bot_data["db"] = db
    app.bot_data["pending_broadcast"] = {}
    app.bot_data["pending_ban"] = {}
    app.bot_data["pending_unban"] = {}
    app.bot_data["pending_setwelcome"] = {}
    app.bot_data["download_state"] = {}
    app.bot_data["_admin_handled_ids"] = set()

    # Commands shown in the Telegram command menu.
    app.bot_data["commands"] = [
        BotCommand("start", "شروع / Start"),
        BotCommand("help", "راهنما / Help"),
        BotCommand("language", "زبان / Language"),
        BotCommand("stats", "آمار من / My stats"),
        BotCommand("admin", "پنل ادمین / Admin panel"),
        BotCommand("broadcast", "ارسال همگانی / Broadcast"),
        BotCommand("ban", "بن کاربر / Ban user"),
        BotCommand("unban", "رفع بن / Unban user"),
        BotCommand("setwelcome", "پیام خوشامد / Welcome message"),
    ]

    # Message handlers (also used by the admin state machine).
    start_handler = start.get_handler()
    help_handler = help_handler.get_handler()
    admin_handler = admin.get_handler()
    admin_state_handler = admin_state.get_handler()
    download_handler = download.get_handler()
    callback_handler = callback.get_handler()
    error_handler = errors.get_handler()

    app.add_handler(start_handler)
    app.add_handler(help_handler)
    app.add_handler(admin_handler)
    # Admin state runs BEFORE download (group=0 < group=1) so pending states
    # intercept the message before link detection processes it.
    app.add_handler(admin_state_handler, group=0)
    app.add_handler(download_handler, group=1)
    app.add_handler(callback_handler)
    app.add_error_handler(error_handler)

    logger.info("Downloader bot is starting...")
    app.run_polling(allowed_updates=None)


async def startup(app) -> None:
    """Initialize the database before the bot starts serving updates."""
    db: Database = app.bot_data["db"]
    await db.init_db()
    logger = logging.getLogger(__name__)
    logger.info("Database ready. Admins: %s", config.ADMIN_IDS)
    await app.bot.set_my_commands(app.bot_data["commands"])


if __name__ == "__main__":
    main()
