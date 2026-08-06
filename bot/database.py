"""SQLite database layer for the Downloader bot (aiosqlite)."""

import datetime
import logging

import aiosqlite

from bot.config import DB_PATH

logger = logging.getLogger(__name__)

_DEFAULT_WELCOME = (
    "👋 سلام {user_name}! خوش اومدی به ربات Downloader.\n"
    "🔗 لینک پست یا ویدیو رو بفرست تا برات دانلودش کنم."
)


class Database:
    """All database operations for users, downloads, settings and broadcasts."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init_db(self) -> None:
        """Open the connection and create all tables."""
        import os
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT,
                first_name    TEXT,
                language      TEXT DEFAULT 'fa',
                join_date     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_banned     INTEGER DEFAULT 0,
                total_downloads INTEGER DEFAULT 0,
                ban_reason    TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                platform    TEXT,
                url         TEXT,
                file_size   INTEGER DEFAULT 0,
                timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success     INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS banned_users (
                user_id   INTEGER PRIMARY KEY,
                ban_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reason    TEXT DEFAULT NULL,
                banned_by INTEGER
            );

            CREATE TABLE IF NOT EXISTS broadcasts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id     INTEGER,
                message_text TEXT,
                sent_count   INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self._db.commit()
        # Seed the default welcome message on first run.
        welcome = await self.get_setting("welcome_message")
        if welcome is None:
            await self.set_setting("welcome_message", _DEFAULT_WELCOME)
        logger.info("Database initialized at %s", self.db_path)

    async def _exec(self, query: str, params: tuple = ()) -> None:
        cursor = await self._db.execute(query, params)
        await self._db.commit()
        await cursor.close()

    async def _fetchone(self, query: str, params: tuple = ()):
        cursor = await self._db.execute(query, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def _fetchall(self, query: str, params: tuple = ()):
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

    # ---------------------------------------------------------- users

    async def add_user(self, user_id: int, username: str, first_name: str) -> None:
        await self._exec(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username or None, first_name or None),
        )

    async def update_user_activity(self, user_id: int) -> None:
        await self._exec(
            "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,),
        )

    async def get_user(self, user_id: int) -> dict | None:
        row = await self._fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(row) if row else None

    async def is_banned(self, user_id: int) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,)
        )
        return row is not None

    async def ban_user(self, user_id: int, reason: str | None, banned_by: int) -> None:
        await self._exec(
            """
            INSERT OR REPLACE INTO banned_users (user_id, reason, banned_by)
            VALUES (?, ?, ?)
            """,
            (user_id, reason, banned_by),
        )
        await self._exec(
            "UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?",
            (reason, user_id),
        )

    async def unban_user(self, user_id: int) -> None:
        await self._exec("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
        await self._exec(
            "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?",
            (user_id,),
        )

    # ------------------------------------------------------- downloads

    async def add_download(
        self, user_id: int, platform: str, url: str, file_size: int, success: int = 1
    ) -> None:
        await self._exec(
            """
            INSERT INTO downloads (user_id, platform, url, file_size, success)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, platform, url, file_size, success),
        )
        if success:
            await self._exec(
                """
                UPDATE users SET total_downloads = total_downloads + 1,
                                 last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (user_id,),
            )

    async def get_user_downloads(self, user_id: int) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS c FROM downloads WHERE user_id = ? AND success = 1",
            (user_id,),
        )
        return int(row["c"]) if row else 0

    async def get_total_downloads(self) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS c FROM downloads WHERE success = 1"
        )
        return int(row["c"]) if row else 0

    async def get_total_users(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS c FROM users")
        return int(row["c"]) if row else 0

    async def get_today_downloads(self) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS c FROM downloads "
            "WHERE success = 1 AND date(timestamp) = date('now', 'localtime')"
        )
        return int(row["c"]) if row else 0

    async def get_week_downloads(self) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS c FROM downloads "
            "WHERE success = 1 AND timestamp >= datetime('now', 'localtime', '-7 days')"
        )
        return int(row["c"]) if row else 0

    async def get_top_platforms(self, limit: int = 5) -> list:
        rows = await self._fetchall(
            """
            SELECT platform, COUNT(*) AS count
            FROM downloads
            WHERE success = 1
            GROUP BY platform
            ORDER BY count DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in rows]

    async def get_most_active_user(self) -> dict | None:
        row = await self._fetchone(
            """
            SELECT user_id, first_name, username, total_downloads
            FROM users
            ORDER BY total_downloads DESC, last_active DESC
            LIMIT 1
            """
        )
        return dict(row) if row else None

    async def get_all_user_ids(self) -> list:
        rows = await self._fetchall("SELECT user_id FROM users")
        return [int(r["user_id"]) for r in rows]

    async def get_user_language(self, user_id: int) -> str:
        row = await self._fetchone(
            "SELECT language FROM users WHERE user_id = ?", (user_id,)
        )
        return str(row["language"]) if row else "fa"

    async def set_user_language(self, user_id: int, language: str) -> None:
        await self._exec(
            """
            INSERT INTO users (user_id, language)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
            """,
            (user_id, language),
        )

    # ------------------------------------------------------- settings

    async def get_setting(self, key: str) -> str | None:
        row = await self._fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return str(row["value"]) if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self._exec(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )

    async def get_welcome_message(self) -> str:
        return await self.get_setting("welcome_message") or _DEFAULT_WELCOME

    async def set_welcome_message(self, text: str) -> None:
        await self.set_setting("welcome_message", text)

    # ----------------------------------------------------- broadcasts

    async def add_broadcast(
        self, admin_id: int, message_text: str, sent_count: int, failed_count: int
    ) -> None:
        await self._exec(
            """
            INSERT INTO broadcasts (admin_id, message_text, sent_count, failed_count)
            VALUES (?, ?, ?, ?)
            """,
            (admin_id, message_text, sent_count, failed_count),
        )

    # -------------------------------------------------------- helpers

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def get_join_date(self, user_id: int) -> str | None:
        """Join date of a user as YYYY-MM-DD, used for the {date} placeholder."""
        row = await self._fetchone(
            "SELECT join_date FROM users WHERE user_id = ?", (user_id,)
        )
        if not row:
            return None
        try:
            return str(datetime.datetime.fromisoformat(row["join_date"]).date())
        except ValueError:
            return str(row["join_date"])
