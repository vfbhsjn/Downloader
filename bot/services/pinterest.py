"""Pinterest image/video downloader service."""

import asyncio
import logging
import re

import yt_dlp

from bot.i18n import get_text
from bot.services.base import BaseDownloader, DownloadError
from bot.utils import media_handler

logger = logging.getLogger(__name__)

_URL_RE = re.compile(
    r"^(?:https?://)?(?:(?:www\.)?pinterest\.com|pin\.it)/", re.IGNORECASE
)


class PinterestDownloader(BaseDownloader):
    """Downloads Pinterest images and videos in original quality."""

    platform = "pinterest"

    def detect(self, url: str) -> bool:
        return bool(_URL_RE.match(url))

    async def get_info(self, url: str, lang: str = "fa") -> dict:
        try:
            info = await self._extract(url)
        except Exception as err:
            logger.error("Pinterest get_info failed for %s: %s", url, err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err

        media_type = "image"
        formats = info.get("formats") or []
        if formats or (info.get("url") or "").lower().endswith((".mp4", ".webm")):
            media_type = "video"
        return {
            "platform": self.platform,
            "title": info.get("title") or info.get("description") or "Pinterest",
            "username": info.get("uploader") or "",
            "media_type": media_type,
        }

    async def download(self, url: str, quality: str = "720p", lang: str = "fa") -> dict:
        dest = self._temp_path("%(title)s.%(ext)s")
        opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": dest,
            "noplaylist": True,
            "retries": 3,
        }
        try:
            await self._run(opts, url)
            path = media_handler.best_path_after_ydl(dest)
            if not path or not self._size(path):
                raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="no file"))
            self._check_size(path)
            ext = media_handler.get_ext(path)
            media_type = (
                "image"
                if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
                else "video"
            )
            return {
                "path": path,
                "ext": ext,
                "type": media_type,
                "platform": self.platform,
            }
        except DownloadError:
            raise
        except Exception as err:
            logger.error("Pinterest download failed for %s: %s", url, err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err

    async def _extract(self, url: str) -> dict:
        def run():
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
                return ydl.extract_info(url, download=False)

        return await asyncio.to_thread(run)

    async def _run(self, opts: dict, url: str) -> None:
        def run():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        await asyncio.to_thread(run)
