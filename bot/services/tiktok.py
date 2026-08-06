"""TikTok downloader service (watermark-free via yt-dlp)."""

import asyncio
import logging
import re

import yt_dlp

from bot.i18n import get_text
from bot.services.base import BaseDownloader, DownloadError
from bot.utils import media_handler

logger = logging.getLogger(__name__)

_URL_RE = re.compile(
    r"^(?:https?://)?(?:(?:www\.|m\.)?tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/",
    re.IGNORECASE,
)


class TikTokDownloader(BaseDownloader):
    """Downloads TikTok videos without a watermark."""

    platform = "tiktok"

    def detect(self, url: str) -> bool:
        return bool(_URL_RE.match(url))

    async def get_info(self, url: str, lang: str = "fa") -> dict:
        try:
            info = await self._extract(url)
        except Exception as err:
            logger.error("TikTok get_info failed for %s: %s", url, err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err
        return {
            "platform": self.platform,
            "title": info.get("title") or "TikTok",
            "username": info.get("uploader") or info.get("channel") or "",
            "likes": int(info.get("like_count") or 0),
            "views": int(info.get("view_count") or 0),
            "caption": info.get("description") or "",
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
            return {
                "path": path,
                "ext": media_handler.get_ext(path),
                "type": "video",
                "platform": self.platform,
            }
        except DownloadError:
            raise
        except Exception as err:
            logger.error("TikTok download failed for %s: %s", url, err)
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
