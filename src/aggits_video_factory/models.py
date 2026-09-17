from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(slots=True)
class Video:
    video_id: str
    title: str
    display_title: str
    url: str
    embed_url: str
    thumbnail_url: str
    published_at: str
    duration_seconds: int
    channel_title: str
    channel_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Video":
        return cls(
            video_id=str(value.get("video_id") or value.get("videoId") or ""),
            title=str(value.get("title") or ""),
            display_title=str(value.get("display_title") or value.get("displayTitle") or value.get("title") or ""),
            url=str(value.get("url") or ""),
            embed_url=str(value.get("embed_url") or value.get("embedUrl") or ""),
            thumbnail_url=str(value.get("thumbnail_url") or value.get("thumbnailUrl") or ""),
            published_at=str(value.get("published_at") or value.get("publishedAt") or ""),
            duration_seconds=int(value.get("duration_seconds") or value.get("durationSeconds") or 0),
            channel_title=str(value.get("channel_title") or value.get("channelTitle") or ""),
            channel_id=str(value.get("channel_id") or value.get("channelId") or ""),
        )


@dataclass(slots=True)
class Project:
    slug: str
    title: str
    ticker_text: str
    channel_url: str
    channel_id: str
    channel_title: str
    channel_thumbnail: str
    source_channel_url: str = ""
    manual_video_urls: list[str] = field(default_factory=list)
    excluded_video_ids: list[str] = field(default_factory=list)
    videos: list[Video] = field(default_factory=list)
    status: str = "draft"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    published_at: str | None = None
    published_url: str | None = None
    delivery_status: str = "not_requested"
    publication_revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["videos"] = [video.to_dict() for video in self.videos]
        value["schemaVersion"] = 2
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Project":
        return cls(
            slug=str(value.get("slug") or ""),
            title=str(value.get("title") or ""),
            ticker_text=str(value.get("ticker_text") or value.get("tickerText") or ""),
            channel_url=str(value.get("channel_url") or value.get("channelUrl") or ""),
            channel_id=str(value.get("channel_id") or value.get("channelId") or ""),
            channel_title=str(value.get("channel_title") or value.get("channelTitle") or ""),
            channel_thumbnail=str(value.get("channel_thumbnail") or value.get("channelThumbnail") or ""),
            source_channel_url=str(value.get("source_channel_url") or value.get("sourceChannelUrl") or value.get("channel_url") or value.get("channelUrl") or ""),
            manual_video_urls=[str(item) for item in (value.get("manual_video_urls", value.get("manualVideoUrls", [])) or []) if str(item).strip()],
            excluded_video_ids=[str(item) for item in (value.get("excluded_video_ids", value.get("excludedVideoIds", [])) or []) if str(item).strip()],
            videos=[Video.from_dict(item) for item in value.get("videos", []) if isinstance(item, dict)],
            status=str(value.get("status") or "draft"),
            created_at=str(value.get("created_at") or value.get("createdAt") or utc_now()),
            updated_at=str(value.get("updated_at") or value.get("updatedAt") or utc_now()),
            published_at=value.get("published_at") or value.get("publishedAt"),
            published_url=value.get("published_url") or value.get("publishedUrl"),
            delivery_status=str(value.get("delivery_status") or value.get("deliveryStatus") or "not_requested"),
            publication_revision=value.get("publication_revision") or value.get("publicationRevision"),
        )
