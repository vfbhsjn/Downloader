"""Spotify downloader service: extract track info, search YouTube, download MP3."""

import json
import logging
import re

import httpx

from bot.i18n import get_text
from bot.services.base import BaseDownloader, DownloadError
from bot.utils import media_handler

logger = logging.getLogger(__name__)

_URL_RE = re.compile(
    r"^(?:https?://)?(?:open\.spotify\.com|spotify\.link)/", re.IGNORECASE
)
_RESOURCE_RE = re.compile(r"/(track|album|playlist|artist|show|episode)/([A-Za-z0-9]+)")
_SHORT_RE = re.compile(r"spotify\.link/([A-Za-z0-9]+)", re.IGNORECASE)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class SpotifyDownloader(BaseDownloader):
    """Resolves Spotify links to track names, then grabs the MP3 from YouTube."""

    platform = "spotify"

    def detect(self, url: str) -> bool:
        return bool(_URL_RE.match(url))

    async def get_info(self, url: str, lang: str = "fa") -> dict:
        track = await self._resolve_track(url, lang)
        return {
            "platform": self.platform,
            "title": track.get("title") or "Spotify",
            "track": track.get("title") or "",
            "artist": track.get("artist") or "",
            "album": track.get("album") or "",
            "duration": int(track.get("duration") or 0),
        }

    async def download(self, url: str, quality: str = "320k", lang: str = "fa") -> dict:
        """Download the track as MP3 (320kbps) by searching YouTube."""
        track = await self._resolve_track(url, lang)
        query = f"{track.get('artist', '')} {track.get('title', '')}"
        dest = media_handler.temp_path("%(title)s.%(ext)s")
        opts = media_handler.ydl_opts(dest, kind="mp3", quality="320k")
        opts["format"] = "bestaudio/best"
        opts["default_search"] = "ytsearch1"

        try:
            await media_handler.ydl_download(opts, query)
            path = media_handler.best_path_after_ydl(dest)
            if not path or not self._size(path):
                raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="no file"))
            self._check_size(path)
            return {
                "path": path,
                "ext": media_handler.get_ext(path),
                "type": "audio",
                "info": track,
                "platform": self.platform,
            }
        except DownloadError:
            raise
        except Exception as err:
            logger.error("Spotify download failed for %s: %s", url, err)
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error=err)) from err

    async def _resolve_track(self, url: str, lang: str) -> dict:
        """Resolve the final Spotify page and extract the first track's info."""
        resolved = await self._resolve_redirect(url)
        match = _RESOURCE_RE.search(resolved)
        if not match:
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="bad link"))
        kind, resource_id = match.group(1), match.group(2)

        if kind == "track":
            return await self._track_info(resource_id)

        tracks = await self._list_tracks(resource_id)
        if not tracks:
            raise DownloadError(get_text("DOWNLOAD_FAILED", lang).format(error="no tracks"))
        return tracks[0]

    async def _resolve_redirect(self, url: str) -> str:
        """Follow spotify.link short links to the canonical open.spotify.com URL."""
        if "spotify.link" not in url:
            return url
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers=_HEADERS,
        ) as client:
            response = await client.get(url)
            return str(response.url)

    async def _track_info(self, track_id: str) -> dict:
        page = await self._fetch(f"https://open.spotify.com/embed/track/{track_id}")
        data = self._extract_json(page)
        return {
            "title": data.get("title") or data.get("name") or "Track",
            "artist": (data.get("artists") or [{}])[0].get("name") if data.get("artists") else "",
            "album": data.get("album", {}).get("name") if isinstance(data.get("album"), dict) else "",
            "duration": int(data.get("duration") or 0) / 1000,
        }

    async def _list_tracks(self, resource_id: str) -> list:
        """Fetch track metadata from the Spotify embed endpoint for an album/playlist."""
        for kind in ("album", "playlist"):
            page = await self._fetch(f"https://open.spotify.com/embed/{kind}/{resource_id}")
            data = self._extract_json(page)
            tracks = data.get("tracks") or []
            result = []
            for track in tracks:
                artists = track.get("artists") or []
                artist = artists[0].get("name") if artists else ""
                result.append({
                    "title": track.get("title") or track.get("name") or "Track",
                    "artist": artist,
                    "album": data.get("name") or "",
                    "duration": int(track.get("duration") or 0) / 1000,
                })
            if result:
                return result
        return []

    async def _fetch(self, url: str) -> str:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers=_HEADERS,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def _extract_json(self, page: str) -> dict:
        """Pull the embedded JSON state from a Spotify embed page."""
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            page,
            re.DOTALL,
        )
        if not match:
            return {}
        try:
            payload = json.loads(match.group(1))
            return (payload.get("props") or {}).get("pageProps") or {}
        except json.JSONDecodeError:
            return {}
