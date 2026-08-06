"""Bot configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

ADMIN_IDS = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_IDS", "").split(",")
    if uid.strip().isdigit()
]

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB in bytes (Telegram limit)
MAX_DURATION = 30 * 60  # 30 minutes in seconds
TEMP_DIR = "/tmp/"

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bot.db")

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot.log")
