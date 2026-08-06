"""Direct link downloader service (fallback for unrecognized URLs)."""

import logging
import re

import httpx

from bot.config import MAX_FILE_SIZE
from bot.i18n import get_text
from bot.services.base import BaseDownloader, DownloadError
from bot.utils import media_handler

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".mp4": "MP4",
    ".mp3": "MP3",
    ".pdf": "PDF",
    ".zip": "ZIP",
    ".apk": "APK",
    ".mkv": "MKV",
    ".avi": "AVI",
    ".gif": "GIF",
    ".png": "PNG",
    ".jpg": "JPG",
    ".jpeg": "JPEG",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


class DirectLinkDownloader(BaseDownloader):
    """Downloads a file straight from its URL when no platform matched."""

    platform = "direct"

    def detect(self, url: str) -> bool:
        # Always True: this is the final fallback downloader.
        return True

    async def get_info(self, url: str, lang: str = "fa") -> dict:
        """Resolve the URL, check the extension and report file size."""
        try:
            final_url, size, content_type = await self._head(url)
        except Exception as err:
            logger.error("Direct link info failed for %s: %s", url, err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err

        extension = self._extension_from(final_url, content_type)
        if extension not in SUPPORTED_EXTENSIONS:
            raise DownloadError(get_text("DIRECT_LINK_UNKNOWN_EXT", lang))

        return {
            "platform": self.platform,
            "title": "Direct file",
            "file_type": SUPPORTED_EXTENSIONS[extension],
            "file_size": size,
            "size_mb": round(size / (1024 * 1024), 1),
            "url": final_url,
            "too_large": size > MAX_FILE_SIZE,
        }

    async def download(self, url: str, quality: str = "720p", lang: str = "fa") -> dict:
        """Download the file to a temp location and return its path."""
        try:
            final_url, _, content_type = await self._head(url)
        except Exception as err:
            logger.error("Direct link download failed for %s: %s", url, err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err

        extension = self._extension_from(final_url, content_type)
        if extension not in SUPPORTED_EXTENSIONS:
            raise DownloadError(get_text("DIRECT_LINK_UNKNOWN_EXT", lang))

        dest = media_handler.temp_path(extension)
        try:
            await self._download(final_url, dest)
            if not media_handler.get_file_size(dest):
                raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="empty file"))
            self._check_size(dest)
            return {
                "path": dest,
                "ext": extension,
                "type": "file",
                "file_type": SUPPORTED_EXTENSIONS[extension],
                "platform": self.platform,
            }
        except DownloadError:
            self._delete(dest)
            raise
        except Exception as err:
            self._delete(dest)
            logger.error("Direct link download failed for %s: %s", url, err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err

    async def _head(self, url: str) -> tuple:
        """Follow redirects and return (final_url, content_length, content_type)."""
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers=_HEADERS,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_length = int(response.headers.get("content-length") or 0)
            content_type = response.headers.get("content-type") or ""
            return str(response.url), content_length, content_type

    async def _download(self, url: str, dest: str) -> None:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(120.0, connect=15.0),
            headers=_HEADERS,
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with open(dest, "wb") as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        if chunk:
                            output.write(chunk)

    @staticmethod
    def _extension_from(url: str, content_type: str) -> str:
        """Determine the file extension from the URL or Content-Type header."""
        path = url.split("?", 1)[0]
        match = re.search(r"\.([A-Za-z0-9]+)$", path)
        if match:
            ext = "." + match.group(1).lower()
            if ext in SUPPORTED_EXTENSIONS:
                return ext
        content_mapping = {
            "video/mp4": ".mp4",
            "audio/mpeg": ".mp3",
            "application/pdf": ".pdf",
            "application/zip": ".zip",
            "application/vnd.android.package-archive": ".apk",
            "video/x-matroska": ".mkv",
            "video/x-msvideo": ".avi",
            "image/gif": ".gif",
            "image/png": ".png",
            "image/jpeg": ".jpg",
        }
        primary = content_type.split(";")[0].strip().lower()
        return content_mapping.get(primary, "")
