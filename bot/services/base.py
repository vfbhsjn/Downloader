"""Base downloader service: contract and shared temp-file handling."""

import abc
import logging

from bot.config import MAX_FILE_SIZE
from bot.utils import media_handler

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when a platform download cannot be completed."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BaseDownloader(abc.ABC):
    """Abstract base class every platform service inherits from."""

    platform: str = "base"

    def detect(self, url: str) -> bool:
        """Return True if this downloader handles the given URL."""
        raise DownloadError(f"{self.platform}: detect() not implemented")

    @abc.abstractmethod
    async def get_info(self, url: str, lang: str = "fa") -> dict:
        """Return metadata about the content."""

    @abc.abstractmethod
    async def download(self, url: str, quality: str = "720p", lang: str = "fa") -> dict:
        """Download the content and return {path, ext, type, info}."""

    # --------------------------------------------------------- helpers

    @staticmethod
    def _temp_path(ext: str = "") -> str:
        return media_handler.temp_path(ext)

    @staticmethod
    def _delete(path: str | None) -> None:
        media_handler.delete_file(path)

    @staticmethod
    def _size(path: str) -> int:
        return media_handler.get_file_size(path)

    @staticmethod
    def _human_size(size: int) -> str:
        return media_handler.human_size(size)

    @staticmethod
    def _check_size(path: str) -> None:
        if media_handler.get_file_size(path) > MAX_FILE_SIZE:
            raise DownloadError("file_too_large")

    def _log_download(self, url: str, path: str) -> None:
        logger.info(
            "[%s] url=%s path=%s size=%d",
            self.platform,
            url,
            path,
            media_handler.get_file_size(path),
        )