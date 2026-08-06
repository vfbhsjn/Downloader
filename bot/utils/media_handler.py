"""File handling: download, inspect, convert and clean up temp files."""

import asyncio
import logging
import os
import re
import uuid

import httpx
import yt_dlp

from bot.config import TEMP_DIR

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4a"}


def _clean_name(name: str) -> str:
    """Safely normalize a filename fragment."""
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]", "_", str(name))
    name = name.strip(" ._")
    return name[:80] if name else "download"


def _best_format(kind: str, quality: str = "720p") -> str:
    """Pick a yt-dlp format string for the requested kind and quality."""
    if kind == "mp3":
        return "bestaudio/best"
    height = quality.lower().rstrip("p")
    if height == "audio":
        return "bestaudio/best"
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"


def temp_path(extension: str = "") -> str:
    """Generate a unique temp file path in the configured temp dir."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    token = uuid.uuid4().hex
    return os.path.join(TEMP_DIR, f"{token}{extension}")


def media_filename(info: dict, ext: str) -> str:
    """Build a safe filename from yt-dlp info; falls back to a unique temp path."""
    title = info.get("title") or "download"
    sanitized = _clean_name(title)
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    path = temp_path(ext)
    base, _, _ = os.path.basename(path).rpartition(".")
    return os.path.join(TEMP_DIR, f"{sanitized}-{base}{ext}")


async def download_file(url: str, dest: str | None = None) -> str:
    """Download `url` to a temp file (streaming, with size limit). Returns the path."""
    target = dest or unique_temp()
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=httpx.Timeout(60.0, connect=15.0)
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            os.makedirs(TEMP_DIR, exist_ok=True)
            with open(target, "wb") as output:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    if len(chunk) == 0:
                        continue
                    output.write(chunk)
    logger.info("Downloaded %s -> %s (%d bytes)", url, target, get_file_size(target))
    return target


def delete_file(path: str) -> None:
    """Remove a temp file if it exists (no error if missing)."""
    if path:
        try:
            if os.path.isfile(path):
                os.remove(path)
                logger.debug("Deleted %s", path)
        except OSError as err:
            logger.warning("Could not delete %s: %s", path, err)


def get_file_size(path: str) -> int:
    """Return the size of a file in bytes."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def basename(path: str) -> str:
    """Return the base name of a temp file path."""
    return os.path.basename(path)


def unique_temp() -> str:
    """Generate a unique empty temp file path (no extension)."""
    return temp_path()


def get_ext(path: str) -> str:
    """Return a lowercase file extension including the dot."""
    _, ext = os.path.splitext(path)
    return ext.lower()


def is_audio_file(path: str | None) -> bool:
    """True if the file looks like an audio file."""
    return bool(path) and get_ext(path) in AUDIO_EXTENSIONS


def is_video_file(path: str | None) -> bool:
    """True if the file looks like a video file."""
    return bool(path) and (
        get_ext(path) in VIDEO_EXTENSIONS
        or get_ext(path) in {".m4v"}
    )


def human_size(size: int) -> str:
    """Format a byte count as a human readable string."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def format_seconds(seconds: float) -> str:
    """Format a duration in seconds as MM:SS or H:MM:SS."""
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


async def convert_to_mp3(input_path: str, output_path: str) -> bool:
    """Convert `input_path` to MP3 (320kbps) at `output_path` in a subprocess."""
    command = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-b:a",
        "320k",
        output_path,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error("ffmpeg failed: %s", stderr.decode(errors="replace")[:500])
            return False
        if os.path.exists(output_path):
            return True
    except FileNotFoundError:
        logger.error("ffmpeg binary not found. Install ffmpeg.")
    except Exception as err:  # pragma: no cover - defensive
        logger.error("Conversion error: %s", err)
    return False


def ydl_opts(dest: str, kind: str = "mp4", quality: str = "720p", message_fn=None) -> dict:
    """Common yt-dlp options; `message_fn` receives status lines for logging."""
    postprocessors = []
    if kind == "mp3":
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }
        ]

    def _hook(status):
        if message_fn is None:
            return
        if status.get("status") == "downloading":
            progress = status.get("_percent_str", "").strip()
            message_fn(f"⬇️ {progress}")

    opts = {
        "format": _best_format(kind),
        "quiet": True,
        "no_warnings": True,
        "outtmpl": dest,
        "noplaylist": True,
        "postprocessors": postprocessors,
        "progress_hooks": [_hook] if message_fn else [],
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "nocheckcertificate": True,
        "ignoreerrors": False,
    }
    return opts


async def ydl_download(opts: dict, url: str) -> None:
    """Run yt-dlp for a single URL using the given options in a thread."""
    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    await asyncio.to_thread(_run)


def best_path_after_ydl(dest: str) -> str:
    """Resolve the actual file yt-dlp wrote, tolerating ffmpeg-merged variants."""
    dest = dest.replace("%(title)s", "download")
    candidates = [dest]
    for ext in (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".opus", ".avi"):
        if not dest.lower().endswith(ext):
            candidates.append(dest + ext)
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return dest