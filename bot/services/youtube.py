"""YouTube downloader service."""

import asyncio
import logging
import re

import yt_dlp

from bot.config import MAX_DURATION
from bot.i18n import get_text
from bot.services.base import BaseDownloader, DownloadError
from bot.utils import media_handler

logger = logging.getLogger(__name__)

_QUALITY_MAP = {
    "360": "360p",
    "480": "480p",
    "720": "720p",
    "1080": "1080p",
    "mp3": "320k",
}

_VIDEO_ID_RE = re.compile(r"(?:v=|/shorts/|youtu\.be/)([A-Za-z0-9_-]{11})")


class YouTubeDownloader(BaseDownloader):
    """Downloads YouTube videos, Shorts and audio via yt-dlp."""

    platform = "youtube"

    def detect(self, url: str) -> bool:
        return bool(
            re.match(
                r"^(?:https?://)?(?:(?:www\.|m\.|music\.)?youtube\.com|youtu\.be)/",
                url,
                re.IGNORECASE,
            )
        )

    async def get_info(self, url: str, lang: str = "fa") -> dict:
        try:
            info = await asyncio.to_thread(self._extract, url, None)
        except Exception as err:
            logger.error("YouTube get_info failed for %s: %s", url, err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err

        duration = int(info.get("duration") or 0)
        if duration > MAX_DURATION:
            raise DownloadError(
                get_text("DURATION_LIMIT", lang).format(limit=MAX_DURATION // 60)
            )

        return {
            "platform": self.platform,
            "title": info.get("title") or "YouTube",
            "channel": info.get("channel") or info.get("uploader") or "",
            "duration": duration,
            "views": int(info.get("view_count") or 0),
            "quality_options": ["360", "480", "720", "1080"],
            "mp3_available": True,
        }

    async def download(self, url: str, quality: str = "720p", lang: str = "fa") -> dict:
        """Download a video (or MP3 if quality == 'mp3') and return file info."""
        is_audio = quality == "mp3"
        height = _QUALITY_MAP.get(quality, "720")

        dest = media_handler.temp_path("%(title)s.%(ext)s")
        opts = media_handler.ydl_opts(
            dest, kind="mp3" if is_audio else "mp4", quality=height
        )

        try:
            await media_handler.ydl_download(opts, url)
            path = media_handler.best_path_after_ydl(dest)
            if not path or not media_handler.get_file_size(path):
                raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="no file"))
            self._check_size(path)
            return {
                "path": path,
                "ext": media_handler.get_ext(path),
                "type": "audio" if is_audio else "video",
                "quality": height if is_audio else f"{height}p",
                "platform": self.platform,
            }
        except DownloadError:
            raise
        except Exception as err:
            logger.error("YouTube download failed for %s: %s", url, err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err

    def _extract(self, url: str, quality: str | None) -> dict:
        """Extract metadata with yt-dlp (no download)."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
        }
        if quality:
            opts["format"] = media_handler._best_format("mp4", quality)
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)


def extract_video_id(url: str) -> str | None:
    """Return the 11-character YouTube video id or None."""
    match = _VIDEO_ID_RE.search(url)
    return match.group(1) if match else None
