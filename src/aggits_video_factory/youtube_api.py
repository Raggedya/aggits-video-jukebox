from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

import requests

from .config import MAX_VIDEOS
from .models import Video


API_ROOT = "https://www.googleapis.com/youtube/v3"
ISO_DURATION = re.compile(r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$")


class YouTubeError(RuntimeError):
    pass


@dataclass(slots=True)
class ChannelCatalogue:
    channel_id: str
    channel_title: str
    channel_url: str
    channel_thumbnail: str
    videos: list[Video]


def parse_duration(value: str) -> int:
    match = ISO_DURATION.fullmatch(value or "")
    if not match:
        return 0
    parts = {key: int(number or 0) for key, number in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def clean_display_title(title: str, channel_title: str, limit: int = 42) -> str:
    value = html.unescape(re.sub(r"\s+", " ", title)).strip()
    value = re.sub(r"\s*[\[(](?:official\s+)?(?:music\s+)?video(?:clip)?[\])]\s*$", "", value, flags=re.I)
    value = re.sub(r"\s*[\[(]official\s+audio[\])]\s*$", "", value, flags=re.I)
    escaped = re.escape(channel_title.strip())
    if escaped:
        value = re.sub(rf"\s*[-|•]\s*{escaped}\s*$", "", value, flags=re.I)
    value = value.strip(" -|•") or html.unescape(title).strip()
    if len(value) <= limit:
        return value
    clipped = value[: limit - 1].rsplit(" ", 1)[0].strip()
    if len(clipped) < max(16, limit // 2):
        clipped = value[: limit - 1].strip()
    return f"{clipped}…"


def best_thumbnail(snippet: dict[str, Any]) -> tuple[str, float]:
    thumbnails = snippet.get("thumbnails") if isinstance(snippet.get("thumbnails"), dict) else {}
    best: tuple[int, str, float] = (0, "", 0.0)
    for value in thumbnails.values():
        if not isinstance(value, dict):
            continue
        width = int(value.get("width") or 0)
        height = int(value.get("height") or 0)
        url = str(value.get("url") or "")
        area = width * height
        ratio = width / height if height else 0.0
        if url and area >= best[0]:
            best = (area, url, ratio)
    return best[1], best[2]


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


class YouTubeClient:
    def __init__(self, api_key: str, timeout: float = 25.0) -> None:
        self.api_key = api_key.strip()
        self.timeout = timeout
        if not self.api_key:
            raise YouTubeError("A YouTube Data API key is required. Open SETTINGS and save the key once.")

    def _get(self, resource: str, **params: object) -> dict[str, Any]:
        query = {key: value for key, value in params.items() if value not in (None, "")}
        query["key"] = self.api_key
        try:
            response = requests.get(f"{API_ROOT}/{resource}", params=query, timeout=self.timeout)
        except requests.RequestException as error:
            raise YouTubeError("YouTube could not be reached. Check the internet connection and try again.") from error
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.ok:
            reason = ""
            if isinstance(body, dict):
                reason = str(body.get("error", {}).get("message") or "")
            if response.status_code in {400, 403} and ("key" in reason.lower() or "quota" in reason.lower()):
                raise YouTubeError(f"YouTube rejected the configured API key or quota. {reason}".strip())
            raise YouTubeError(f"YouTube catalogue request failed ({response.status_code}). {reason}".strip())
        return body if isinstance(body, dict) else {}

    def resolve_channel(self, channel_url: str) -> dict[str, Any]:
        raw = channel_url.strip()
        if not raw:
            raise YouTubeError("Paste a YouTube channel URL.")
        if not re.match(r"^https?://", raw, flags=re.I):
            raw = f"https://{raw.lstrip('/')}"
        parsed = urlparse(raw)
        host = parsed.hostname.lower().removeprefix("www.") if parsed.hostname else ""
        if host not in {"youtube.com", "m.youtube.com"}:
            raise YouTubeError("The channel link must be on youtube.com.")
        segments = [segment for segment in parsed.path.split("/") if segment]
        criteria: dict[str, str] = {}
        if segments and segments[0].startswith("@"):
            criteria["forHandle"] = segments[0]
        elif len(segments) >= 2 and segments[0] == "channel":
            criteria["id"] = segments[1]
        elif len(segments) >= 2 and segments[0] == "user":
            criteria["forUsername"] = segments[1]
        elif len(segments) >= 2 and segments[0] in {"c", "profile"}:
            criteria["forHandle"] = segments[1]
        elif parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
            if video_id:
                detail = self._get("videos", part="snippet", id=video_id)
                item = next(iter(detail.get("items", [])), None)
                if isinstance(item, dict):
                    criteria["id"] = str(item.get("snippet", {}).get("channelId") or "")
        if not criteria:
            raise YouTubeError("Use the channel’s main /@handle or /channel/ link, not an individual playlist page.")
        result = self._get("channels", part="snippet,contentDetails", **criteria)
        items = result.get("items") if isinstance(result.get("items"), list) else []
        if not items and "forHandle" in criteria:
            # Legacy custom URLs sometimes no longer equal the current handle.
            search = self._get("search", part="snippet", type="channel", maxResults=5, q=criteria["forHandle"].lstrip("@"))
            candidates = search.get("items") if isinstance(search.get("items"), list) else []
            if candidates:
                channel_id = str(candidates[0].get("snippet", {}).get("channelId") or candidates[0].get("id", {}).get("channelId") or "")
                if channel_id:
                    result = self._get("channels", part="snippet,contentDetails", id=channel_id)
                    items = result.get("items") if isinstance(result.get("items"), list) else []
        if len(items) != 1:
            raise YouTubeError("A unique public YouTube channel could not be identified from that link.")
        return dict(items[0])

    def fetch_catalogue(self, channel_url: str, maximum: int = MAX_VIDEOS) -> ChannelCatalogue:
        maximum = max(1, min(MAX_VIDEOS, int(maximum)))
        channel = self.resolve_channel(channel_url)
        channel_id = str(channel.get("id") or "")
        snippet = channel.get("snippet") if isinstance(channel.get("snippet"), dict) else {}
        details = channel.get("contentDetails") if isinstance(channel.get("contentDetails"), dict) else {}
        uploads = str(details.get("relatedPlaylists", {}).get("uploads") or "")
        if not channel_id or not uploads:
            raise YouTubeError("The channel does not expose a public uploads catalogue.")

        playlist_items: list[dict[str, Any]] = []
        page_token = ""
        while len(playlist_items) < 100:
            page = self._get(
                "playlistItems",
                part="contentDetails,snippet",
                playlistId=uploads,
                maxResults=50,
                pageToken=page_token,
            )
            playlist_items.extend(item for item in page.get("items", []) if isinstance(item, dict))
            page_token = str(page.get("nextPageToken") or "")
            if not page_token:
                break

        ids: list[str] = []
        for item in playlist_items:
            video_id = str(item.get("contentDetails", {}).get("videoId") or item.get("snippet", {}).get("resourceId", {}).get("videoId") or "")
            if video_id and video_id not in ids:
                ids.append(video_id)

        videos_by_id: dict[str, dict[str, Any]] = {}
        for group in chunks(ids, 50):
            page = self._get("videos", part="snippet,contentDetails,status", id=",".join(group), maxResults=50)
            for item in page.get("items", []):
                if isinstance(item, dict) and item.get("id"):
                    videos_by_id[str(item["id"])] = item

        primary: list[Video] = []
        fallback: list[Video] = []
        for video_id in ids:
            item = videos_by_id.get(video_id)
            if not item:
                continue
            status = item.get("status") if isinstance(item.get("status"), dict) else {}
            video_snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            if status.get("privacyStatus") != "public" or status.get("embeddable") is not True:
                continue
            if str(video_snippet.get("liveBroadcastContent") or "none") != "none":
                continue
            title = html.unescape(str(video_snippet.get("title") or "")).strip()
            if not title:
                continue
            duration = parse_duration(str(item.get("contentDetails", {}).get("duration") or ""))
            thumbnail_url, ratio = best_thumbnail(video_snippet)
            record = Video(
                video_id=video_id,
                title=title,
                display_title=clean_display_title(title, str(snippet.get("title") or "")),
                url=f"https://www.youtube.com/watch?v={video_id}",
                embed_url=f"https://www.youtube.com/embed/{video_id}?enablejsapi=1&autoplay=0&playsinline=1&rel=0",
                thumbnail_url=thumbnail_url,
                published_at=str(video_snippet.get("publishedAt") or ""),
                duration_seconds=duration,
                channel_title=str(video_snippet.get("channelTitle") or snippet.get("title") or ""),
            )
            looks_like_short = duration and duration <= 60 or "#shorts" in title.lower() or (ratio and ratio < 0.9)
            (fallback if looks_like_short else primary).append(record)

        selected = (primary + fallback)[:maximum]
        if not selected:
            raise YouTubeError("No public, embeddable videos were available on this channel.")
        channel_thumbnail, _ = best_thumbnail(snippet)
        return ChannelCatalogue(
            channel_id=channel_id,
            channel_title=html.unescape(str(snippet.get("title") or "YouTube Channel")),
            channel_url=f"https://www.youtube.com/channel/{channel_id}",
            channel_thumbnail=channel_thumbnail,
            videos=selected,
        )

