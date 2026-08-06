"""Instagram downloader service: reels, stories, posts, videos and carousels."""

import json
import logging
import re

import httpx

from bot.config import MAX_FILE_SIZE
from bot.i18n import get_text
from bot.services.base import BaseDownloader, DownloadError
from bot.utils import media_handler

logger = logging.getLogger(__name__)

_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:instagram\.com|instagr\.am)/", re.IGNORECASE
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class InstagramDownloader(BaseDownloader):
    """Downloads Instagram posts without login. Carousels are fetched fully."""

    platform = "instagram"

    def detect(self, url: str) -> bool:
        return bool(_URL_RE.match(url))

    async def get_info(self, url: str, lang: str = "fa") -> dict:
        """Return info via the public GraphQL post page."""
        page = await self._fetch_page(url)
        state = self._parse_state(page)
        if not state:
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="private or unavailable"))
        item = state.get("items") or [state]
        first = item[0]
        caption = (first.get("caption") or "").strip() or (first.get("text") or "")
        return {
            "platform": self.platform,
            "title": caption[:120] or "Instagram",
            "username": first.get("owner_username") or state.get("owner_username") or "",
            "likes": int(first.get("likes") or 0),
            "media_count": len(item),
            "media_type": self._media_type(first),
            "caption": caption,
        }

    async def download(self, url: str, quality: str = "720p", lang: str = "fa") -> dict:
        """Download a single post. For carousels, return a list of file paths."""
        page = await self._fetch_page(url)
        state = self._parse_state(page)
        if not state:
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="private or unavailable"))

        items = state.get("items") or [state]
        if len(items) == 1:
            path = await self._download_one(items[0], lang)
            ext = media_handler.get_ext(path)
            return {
                "path": path,
                "ext": ext,
                "type": "image" if ext in _IMAGE_EXTS else "video",
                "paths": [path],
                "platform": self.platform,
            }

        # Carousel: download every image, cap total size at the Telegram limit.
        paths = []
        total_size = 0
        try:
            for index, item in enumerate(items):
                path = await self._download_one(item, lang, f"_{index + 1}")
                total_size += media_handler.get_file_size(path)
                if total_size > MAX_FILE_SIZE:
                    raise DownloadError(get_text("FILE_TOO_LARGE", lang).format(
                        size=round(total_size / (1024 * 1024), 1)
                    ))
                paths.append(path)
            return {
                "path": paths[0],
                "ext": media_handler.get_ext(paths[0]),
                "type": "carousel",
                "paths": paths,
                "platform": self.platform,
            }
        except Exception:
            for path in paths:
                self._delete(path)
            raise

    async def _download_one(self, item: dict, lang: str, suffix: str = "") -> str:
        """Download one media item (photo or video) and return the file path."""
        media_type = item.get("media_type", 1)
        if media_type == 1:
            image_url = item.get("image_url")
            if not image_url:
                raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="no image"))
            path = self._temp_path(".jpg")
            await self._download_http(image_url, path)
            return path

        # Video: use yt-dlp so the best quality is picked automatically.
        video_url = item.get("video_url")
        if not video_url:
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="no video"))
        dest = self._temp_path("%(title)s%(id)s.%(ext)s")
        opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": dest,
            "noplaylist": True,
            "retries": 3,
        }
        try:
            await media_handler.ydl_download(opts, video_url)
            path = media_handler.best_path_after_ydl(dest)
            if not path or not self._size(path):
                raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="no file"))
            return path
        except DownloadError:
            raise
        except Exception as err:
            logger.error("Instagram video download failed: %s", err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err

    async def _download_http(self, image_url: str, path: str) -> None:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=httpx.Timeout(60.0, connect=15.0),
            headers=_HEADERS,
        ) as client:
            async with client.stream("GET", image_url) as response:
                response.raise_for_status()
                with open(path, "wb") as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        if chunk:
                            output.write(chunk)

    async def _fetch_page(self, url: str) -> str:
        """Fetch the public post page HTML."""
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers=_HEADERS,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def _parse_state(self, page: str) -> dict | None:
        """Extract the embedded GraphQL state from the page HTML."""
        # Modern Instagram embeds it as a script with `window._sharedData` or
        # as a JSON blob inside `__additionalDataLoaded`. We try both.
        match = re.search(r"window\._sharedData\s*=\s*({.*?})\s*;", page, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                media = data.get("entry_data", {}).get("PostPage", [{}])[0].get(
                    "graphql", {}
                ).get("shortcode_media", {})
                return self._convert_graphql(media)
            except (json.JSONDecodeError, IndexError, AttributeError):
                pass

        match = re.search(r'"shortcode_media":\s*({.*?})\s*,\s*"display_url"', page, re.DOTALL)
        if not match:
            return None
        try:
            raw = "{" + match.group(1) + "}"
            data = json.loads(raw)
            return self._convert_graphql(data)
        except json.JSONDecodeError:
            return None

    def _convert_graphql(self, media: dict) -> dict | None:
        """Convert a GraphQL shortcode_media dict into our flat item shape."""
        if not media or not isinstance(media, dict):
            return None
        owner = media.get("owner") or {}
        edge = media.get("edge_media_to_caption") or {}
        caption = ""
        for node in edge.get("edges", []):
            node_text = node.get("node", {}).get("text")
            if node_text:
                caption = node_text
                break
        items = [{
            "media_type": 2 if media.get("is_video") else 1,
            "image_url": media.get("display_url"),
            "video_url": media.get("video_url"),
            "likes": (media.get("edge_media_preview_like") or {}).get("count", 0),
            "caption": caption,
        }]
        children = media.get("edge_sidecar_to_children", {}).get("edges", [])
        for child in children:
            node = child.get("node", {})
            items.append({
                "media_type": 2 if node.get("is_video") else 1,
                "image_url": node.get("display_url"),
                "video_url": node.get("video_url"),
                "likes": 0,
                "caption": "",
            })
        return {
            "items": items,
            "owner_username": owner.get("username"),
        }

    @staticmethod
    def _media_type(item: dict) -> str:
        if item.get("media_type") == 2:
            return "video"
        return "image"
