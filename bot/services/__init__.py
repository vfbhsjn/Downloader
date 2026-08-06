"""Service registry: maps platform slugs to downloader instances."""

from bot.services.instagram import InstagramDownloader
from bot.services.youtube import YouTubeDownloader
from bot.services.tiktok import TikTokDownloader
from bot.services.spotify import SpotifyDownloader
from bot.services.pinterest import PinterestDownloader
from bot.services.soundcloud import SoundCloudDownloader
from bot.services.twitter import TwitterDownloader
from bot.services.aparat import AparatDownloader
from bot.services.reddit import RedditDownloader
from bot.services.twitch import TwitchDownloader
from bot.services.facebook import FacebookDownloader
from bot.services.rumble import RumbleDownloader
from bot.services.direct_link import DirectLinkDownloader
from bot.services.base import BaseDownloader

REGISTRY: dict[str, BaseDownloader] = {
    "instagram": InstagramDownloader(),
    "youtube": YouTubeDownloader(),
    "tiktok": TikTokDownloader(),
    "spotify": SpotifyDownloader(),
    "pinterest": PinterestDownloader(),
    "soundcloud": SoundCloudDownloader(),
    "twitter": TwitterDownloader(),
    "aparat": AparatDownloader(),
    "reddit": RedditDownloader(),
    "twitch": TwitchDownloader(),
    "facebook": FacebookDownloader(),
    "rumble": RumbleDownloader(),
    "direct": DirectLinkDownloader(),
}


def get_service(platform: str) -> BaseDownloader:
    """Return the downloader for a platform slug (direct as fallback)."""
    return REGISTRY.get(platform, DirectLinkDownloader())
