from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from .migrations import CURRENT_PROJECT_SCHEMA_VERSION, migrate_project_dict


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ProjectValidationError(ValueError):
    pass


class ProjectType(str, Enum):
    BUSINESS = "business"
    MUSIC = "music"
    TOURISM = "tourism"


class MachineTheme(str, Enum):
    CLASSIC = "classic"
    CANDY = "candy"


class PrimaryCtaType(str, Enum):
    SHOP_NOW = "shop_now"
    VIEW_PRODUCTS = "view_products"
    GET_A_QUOTE = "get_a_quote"
    ENQUIRE_NOW = "enquire_now"
    FIND_A_STORE = "find_a_store"
    FIND_A_DEALER = "find_a_dealer"
    BOOK_A_DEMO = "book_a_demo"
    CONTACT_US = "contact_us"
    VISIT_WEBSITE = "visit_website"
    SPOTIFY = "spotify"
    BANDCAMP = "bandcamp"
    BUY_MUSIC = "buy_music"
    MERCH = "merch"
    TICKETS = "tickets"
    APPLE_MUSIC = "apple_music"
    OFFICIAL_WEBSITE = "official_website"
    BOOK_NOW = "book_now"
    BOOK_US = "book_us"
    SOUNDCLOUD = "soundcloud"
    MORE_INFO = "more_info"
    STAY = "stay"
    EXPLORE = "explore"
    WHATS_ON = "whats_on"
    PLAN_YOUR_VISIT = "plan_your_visit"
    CUSTOM = "custom"


@dataclass(slots=True)
class DeliveryRecord:
    recipient: str
    revision: str
    status: str = "not_requested"
    sent_at: str | None = None
    last_attempt_at: str | None = None
    error_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipient": self.recipient,
            "revision": self.revision,
            "status": self.status,
            "sent_at": self.sent_at,
            "last_attempt_at": self.last_attempt_at,
            "error_summary": self.error_summary,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "DeliveryRecord | None":
        if not value:
            return None
        return cls(
            recipient=str(value.get("recipient") or ""),
            revision=str(value.get("revision") or ""),
            status=str(value.get("status") or "not_requested"),
            sent_at=value.get("sent_at", value.get("sentAt")),
            last_attempt_at=value.get("last_attempt_at", value.get("lastAttemptAt")),
            error_summary=value.get("error_summary", value.get("errorSummary")),
        )


@dataclass(slots=True)
class PublicationOperation:
    operation_id: str
    operation_type: str
    project_id: str
    slug: str
    target_revision: str | None
    expected_url: str
    started_at: str
    git_confirmed_at: str | None = None
    verification_status: str = "not_started"
    verified_at: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "project_id": self.project_id,
            "slug": self.slug,
            "target_revision": self.target_revision,
            "expected_url": self.expected_url,
            "started_at": self.started_at,
            "git_confirmed_at": self.git_confirmed_at,
            "verification_status": self.verification_status,
            "verified_at": self.verified_at,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "PublicationOperation | None":
        if not value:
            return None
        return cls(
            operation_id=str(value.get("operation_id") or value.get("operationId") or ""),
            operation_type=str(value.get("operation_type") or value.get("operationType") or ""),
            project_id=str(value.get("project_id") or value.get("projectId") or ""),
            slug=str(value.get("slug") or ""),
            target_revision=value.get("target_revision", value.get("targetRevision")),
            expected_url=str(value.get("expected_url") or value.get("expectedUrl") or ""),
            started_at=str(value.get("started_at") or value.get("startedAt") or ""),
            git_confirmed_at=value.get("git_confirmed_at", value.get("gitConfirmedAt")),
            verification_status=str(value.get("verification_status") or value.get("verificationStatus") or "not_started"),
            verified_at=value.get("verified_at", value.get("verifiedAt")),
            last_error=value.get("last_error", value.get("lastError")),
        )


PRIMARY_CTA_LABELS: dict[PrimaryCtaType, str] = {
    PrimaryCtaType.SHOP_NOW: "SHOP NOW",
    PrimaryCtaType.VIEW_PRODUCTS: "VIEW PRODUCTS",
    PrimaryCtaType.GET_A_QUOTE: "GET A QUOTE",
    PrimaryCtaType.ENQUIRE_NOW: "ENQUIRE NOW",
    PrimaryCtaType.FIND_A_STORE: "FIND A STORE",
    PrimaryCtaType.FIND_A_DEALER: "FIND A DEALER",
    PrimaryCtaType.BOOK_A_DEMO: "BOOK A DEMO",
    PrimaryCtaType.CONTACT_US: "CONTACT US",
    PrimaryCtaType.VISIT_WEBSITE: "VISIT WEBSITE",
    PrimaryCtaType.SPOTIFY: "LISTEN ON SPOTIFY",
    PrimaryCtaType.BANDCAMP: "BUY ON BANDCAMP",
    PrimaryCtaType.BUY_MUSIC: "BUY MUSIC",
    PrimaryCtaType.MERCH: "BUY MERCH",
    PrimaryCtaType.TICKETS: "GET TICKETS",
    PrimaryCtaType.APPLE_MUSIC: "APPLE MUSIC",
    PrimaryCtaType.OFFICIAL_WEBSITE: "OFFICIAL WEBSITE",
    PrimaryCtaType.BOOK_NOW: "BOOK NOW",
    PrimaryCtaType.BOOK_US: "BOOK US",
    PrimaryCtaType.SOUNDCLOUD: "SOUNDCLOUD",
    PrimaryCtaType.MORE_INFO: "MORE INFO",
    PrimaryCtaType.STAY: "STAY",
    PrimaryCtaType.EXPLORE: "EXPLORE",
    PrimaryCtaType.WHATS_ON: "WHAT'S ON",
    PrimaryCtaType.PLAN_YOUR_VISIT: "PLAN YOUR VISIT",
}

BUSINESS_CTA_TYPES = frozenset({
    PrimaryCtaType.SHOP_NOW, PrimaryCtaType.VIEW_PRODUCTS, PrimaryCtaType.GET_A_QUOTE,
    PrimaryCtaType.BOOK_NOW, PrimaryCtaType.ENQUIRE_NOW, PrimaryCtaType.FIND_A_STORE,
    PrimaryCtaType.FIND_A_DEALER, PrimaryCtaType.BOOK_A_DEMO, PrimaryCtaType.CONTACT_US,
    PrimaryCtaType.VISIT_WEBSITE, PrimaryCtaType.CUSTOM,
})
MUSIC_CTA_TYPES = frozenset({
    PrimaryCtaType.SPOTIFY, PrimaryCtaType.BANDCAMP, PrimaryCtaType.BUY_MUSIC,
    PrimaryCtaType.MERCH, PrimaryCtaType.TICKETS, PrimaryCtaType.APPLE_MUSIC,
    PrimaryCtaType.OFFICIAL_WEBSITE, PrimaryCtaType.BOOK_NOW, PrimaryCtaType.BOOK_US,
    PrimaryCtaType.SOUNDCLOUD, PrimaryCtaType.CUSTOM,
})
TOURISM_CTA_TYPES = frozenset({
    PrimaryCtaType.MORE_INFO, PrimaryCtaType.STAY, PrimaryCtaType.EXPLORE,
    PrimaryCtaType.BOOK_NOW, PrimaryCtaType.WHATS_ON, PrimaryCtaType.PLAN_YOUR_VISIT,
    PrimaryCtaType.VISIT_WEBSITE, PrimaryCtaType.CUSTOM,
})


def _optional_http_url(value: object, field_name: str) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProjectValidationError(f"{field_name} must be a complete http or https URL.")
    return cleaned


def _extra_fields(value: dict[str, Any], known: set[str]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in known}


@dataclass(slots=True)
class BusinessConfig:
    shop_url: str | None = None
    primary_cta: "PrimaryCta | None" = None
    extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.shop_url = _optional_http_url(self.shop_url, "Business shop URL")

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.extra_fields,
            "shop_url": self.shop_url,
            "primary_cta": self.primary_cta.to_dict() if self.primary_cta else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "BusinessConfig":
        source = dict(value or {})
        cta = source.get("primary_cta", source.get("primaryCta"))
        if cta is not None and not isinstance(cta, dict):
            raise ProjectValidationError("Business primary_cta must be an object or null.")
        shop_url = source.get("shop_url", source.get("shopUrl"))
        return cls(
            shop_url=shop_url,
            primary_cta=PrimaryCta.from_dict(cta) if isinstance(cta, dict) else (
                PrimaryCta(PrimaryCtaType.SHOP_NOW, str(shop_url)) if shop_url else None
            ),
            extra_fields=_extra_fields(source, {"shop_url", "shopUrl", "primary_cta", "primaryCta"}),
        )


@dataclass(slots=True)
class PrimaryCta:
    cta_type: PrimaryCtaType | str
    destination_url: str
    display_label: str = ""
    custom_label: str | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        try:
            self.cta_type = PrimaryCtaType(self.cta_type)
        except ValueError as error:
            raise ProjectValidationError(f"Unsupported primary CTA type: {self.cta_type!r}.") from error
        self.destination_url = _optional_http_url(self.destination_url, "Primary CTA destination URL") or ""
        self.custom_label = str(self.custom_label or "").strip() or None
        self.display_label = str(self.display_label or "").strip()
        if self.cta_type is PrimaryCtaType.CUSTOM:
            if not self.custom_label:
                raise ProjectValidationError("A custom primary CTA requires a custom label.")
            if len(self.custom_label) > 40:
                raise ProjectValidationError("A custom primary CTA label cannot exceed 40 characters.")
            self.display_label = self.custom_label
        else:
            self.display_label = PRIMARY_CTA_LABELS[self.cta_type]
        if self.cta_type is PrimaryCtaType.CUSTOM and not self.destination_url:
            raise ProjectValidationError("A custom primary CTA requires a destination URL.")

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.extra_fields,
            "type": self.cta_type.value,
            "display_label": self.display_label,
            "destination_url": self.destination_url,
            "custom_label": self.custom_label,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PrimaryCta":
        source = dict(value)
        known = {"type", "cta_type", "ctaType", "display_label", "displayLabel", "destination_url", "destinationUrl", "custom_label", "customLabel"}
        return cls(
            cta_type=source.get("type", source.get("cta_type", source.get("ctaType", ""))),
            display_label=str(source.get("display_label", source.get("displayLabel", "")) or ""),
            destination_url=str(source.get("destination_url", source.get("destinationUrl", "")) or ""),
            custom_label=source.get("custom_label", source.get("customLabel")),
            extra_fields=_extra_fields(source, known),
        )


@dataclass(slots=True)
class MusicConfig:
    primary_cta: PrimaryCta | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {**self.extra_fields, "primary_cta": self.primary_cta.to_dict() if self.primary_cta else None}

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "MusicConfig":
        source = dict(value or {})
        cta = source.get("primary_cta", source.get("primaryCta"))
        if cta is not None and not isinstance(cta, dict):
            raise ProjectValidationError("Music primary_cta must be an object or null.")
        return cls(
            primary_cta=PrimaryCta.from_dict(cta) if isinstance(cta, dict) else None,
            extra_fields=_extra_fields(source, {"primary_cta", "primaryCta"}),
        )


@dataclass(slots=True)
class TourismConfig:
    more_info_url: str | None = None
    stay_url: str | None = None
    primary_cta: PrimaryCta | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.more_info_url = _optional_http_url(self.more_info_url, "More Info URL")
        self.stay_url = _optional_http_url(self.stay_url, "Stay URL")

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.extra_fields,
            "more_info_url": self.more_info_url,
            "stay_url": self.stay_url,
            "primary_cta": self.primary_cta.to_dict() if self.primary_cta else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "TourismConfig":
        source = dict(value or {})
        more_info_url = source.get("more_info_url", source.get("moreInfoUrl"))
        stay_url = source.get("stay_url", source.get("stayUrl"))
        cta = source.get("primary_cta", source.get("primaryCta"))
        if cta is not None and not isinstance(cta, dict):
            raise ProjectValidationError("Tourism primary_cta must be an object or null.")
        compatible_cta = None
        if isinstance(cta, dict):
            compatible_cta = PrimaryCta.from_dict(cta)
        elif more_info_url:
            compatible_cta = PrimaryCta(PrimaryCtaType.MORE_INFO, str(more_info_url))
        elif stay_url:
            compatible_cta = PrimaryCta(PrimaryCtaType.STAY, str(stay_url))
        return cls(
            more_info_url=more_info_url,
            stay_url=stay_url,
            primary_cta=compatible_cta,
            extra_fields=_extra_fields(source, {"more_info_url", "moreInfoUrl", "stay_url", "stayUrl", "primary_cta", "primaryCta"}),
        )


def project_primary_cta(project: "Project") -> PrimaryCta | None:
    """Return the one active CTA, adapting legacy URLs without mutating them."""
    if project.project_type is ProjectType.BUSINESS:
        config = project.business_config
        if not config:
            return None
        return config.primary_cta or PrimaryCta(PrimaryCtaType.SHOP_NOW, config.shop_url or "")
    if project.project_type is ProjectType.MUSIC:
        return project.music_config.primary_cta if project.music_config else None
    config = project.tourism_config
    if not config:
        return None
    return config.primary_cta or (
        PrimaryCta(PrimaryCtaType.MORE_INFO, config.more_info_url)
        if config.more_info_url else
        PrimaryCta(PrimaryCtaType.STAY, config.stay_url)
        if config.stay_url else
        PrimaryCta(PrimaryCtaType.MORE_INFO, "")
    )


def allowed_primary_cta_types(project_type: ProjectType | str) -> frozenset[PrimaryCtaType]:
    kind = ProjectType(project_type)
    if kind is ProjectType.BUSINESS:
        return BUSINESS_CTA_TYPES
    if kind is ProjectType.MUSIC:
        return MUSIC_CTA_TYPES
    return TOURISM_CTA_TYPES


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
    extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.extra_fields,
            "video_id": self.video_id,
            "title": self.title,
            "display_title": self.display_title,
            "url": self.url,
            "embed_url": self.embed_url,
            "thumbnail_url": self.thumbnail_url,
            "published_at": self.published_at,
            "duration_seconds": self.duration_seconds,
            "channel_title": self.channel_title,
            "channel_id": self.channel_id,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Video":
        known = {
            "video_id", "videoId", "title", "display_title", "displayTitle", "url", "embed_url", "embedUrl",
            "thumbnail_url", "thumbnailUrl", "published_at", "publishedAt", "duration_seconds", "durationSeconds",
            "channel_title", "channelTitle", "channel_id", "channelId",
        }
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
            extra_fields=_extra_fields(value, known),
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
    id: str = field(default_factory=lambda: str(uuid4()))
    project_type: ProjectType | str = ProjectType.BUSINESS
    machine_theme: MachineTheme | str = MachineTheme.CLASSIC
    additional_urls: list[str] = field(default_factory=list)
    business_config: BusinessConfig | None = None
    music_config: MusicConfig | None = None
    tourism_config: TourismConfig | None = None
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
    delivery_record: DeliveryRecord | None = None
    publication_operation: PublicationOperation | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __setattr__(self, name: str, value: object) -> None:
        if name == "id":
            try:
                current = object.__getattribute__(self, "id")
            except AttributeError:
                pass
            else:
                try:
                    replacement = str(UUID(str(value)))
                except (ValueError, TypeError, AttributeError) as error:
                    raise ProjectValidationError("Project id must be a valid UUID.") from error
                if current != replacement:
                    raise ProjectValidationError("Project id is immutable once assigned.")
                value = replacement
        object.__setattr__(self, name, value)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "id", str(UUID(str(self.id))))
        except (ValueError, TypeError, AttributeError) as error:
            raise ProjectValidationError("Project id must be a valid UUID.") from error
        try:
            self.project_type = ProjectType(self.project_type)
        except ValueError as error:
            raise ProjectValidationError(f"Unsupported project type: {self.project_type!r}.") from error
        try:
            self.machine_theme = MachineTheme(self.machine_theme)
        except ValueError as error:
            raise ProjectValidationError(f"Unsupported machine theme: {self.machine_theme!r}.") from error
        if len(self.additional_urls) > 3:
            raise ProjectValidationError("A project can contain no more than three additional URLs.")
        self.additional_urls = [
            _optional_http_url(url, "Additional URL") or "" for url in self.additional_urls if str(url or "").strip()
        ]
        if self.project_type is ProjectType.BUSINESS:
            if self.music_config is not None or self.tourism_config is not None:
                raise ProjectValidationError("A Business project cannot have active Music or Tourism configuration.")
            self.business_config = self.business_config or BusinessConfig()
        elif self.project_type is ProjectType.MUSIC:
            if self.business_config is not None or self.tourism_config is not None:
                raise ProjectValidationError("A Music project cannot have active Business or Tourism configuration.")
            self.music_config = self.music_config or MusicConfig()
        else:
            if self.business_config is not None or self.music_config is not None:
                raise ProjectValidationError("A Tourism project cannot have active Business or Music configuration.")
            self.tourism_config = self.tourism_config or TourismConfig()
        primary_cta = project_primary_cta(self)
        if primary_cta and primary_cta.cta_type not in allowed_primary_cta_types(self.project_type):
            raise ProjectValidationError(
                f"Primary CTA type {primary_cta.cta_type.value!r} is not allowed for {self.project_type.value}."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.extra_fields,
            "slug": self.slug,
            "title": self.title,
            "ticker_text": self.ticker_text,
            "channel_url": self.channel_url,
            "channel_id": self.channel_id,
            "channel_title": self.channel_title,
            "channel_thumbnail": self.channel_thumbnail,
            "id": self.id,
            "project_type": self.project_type.value,
            "machine_theme": self.machine_theme.value,
            "additional_urls": list(self.additional_urls),
            "business_config": self.business_config.to_dict() if self.business_config else None,
            "music_config": self.music_config.to_dict() if self.music_config else None,
            "tourism_config": self.tourism_config.to_dict() if self.tourism_config else None,
            "source_channel_url": self.source_channel_url,
            "manual_video_urls": list(self.manual_video_urls),
            "excluded_video_ids": list(self.excluded_video_ids),
            "videos": [video.to_dict() for video in self.videos],
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
            "published_url": self.published_url,
            "delivery_status": self.delivery_status,
            "publication_revision": self.publication_revision,
            "delivery_record": self.delivery_record.to_dict() if self.delivery_record else None,
            "publication_operation": self.publication_operation.to_dict() if self.publication_operation else None,
            "schemaVersion": CURRENT_PROJECT_SCHEMA_VERSION,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Project":
        migration = migrate_project_dict(value)
        value = migration.data
        known = {
            "schemaVersion", "slug", "title", "ticker_text", "tickerText", "channel_url", "channelUrl",
            "channel_id", "channelId", "channel_title", "channelTitle", "channel_thumbnail", "channelThumbnail",
            "id", "project_id", "projectId", "project_type", "projectType", "additional_urls", "additionalUrls",
            "machine_theme", "machineTheme",
            "business_config", "businessConfig", "music_config", "musicConfig", "tourism_config", "tourismConfig",
            "source_channel_url", "sourceChannelUrl",
            "manual_video_urls", "manualVideoUrls", "excluded_video_ids", "excludedVideoIds", "videos", "status",
            "created_at", "createdAt", "updated_at", "updatedAt", "published_at", "publishedAt", "published_url",
            "publishedUrl", "delivery_status", "deliveryStatus", "publication_revision", "publicationRevision",
            "delivery_record", "deliveryRecord", "publication_operation", "publicationOperation",
        }
        project_type = value.get("project_type", value.get("projectType", ProjectType.BUSINESS.value))
        business_value = value.get("business_config", value.get("businessConfig"))
        music_value = value.get("music_config", value.get("musicConfig"))
        tourism_value = value.get("tourism_config", value.get("tourismConfig"))
        if business_value is not None and not isinstance(business_value, dict):
            raise ProjectValidationError("business_config must be an object or null.")
        if music_value is not None and not isinstance(music_value, dict):
            raise ProjectValidationError("music_config must be an object or null.")
        if tourism_value is not None and not isinstance(tourism_value, dict):
            raise ProjectValidationError("tourism_config must be an object or null.")
        return cls(
            slug=str(value.get("slug") or ""),
            title=str(value.get("title") or ""),
            ticker_text=str(value.get("ticker_text") or value.get("tickerText") or ""),
            channel_url=str(value.get("channel_url") or value.get("channelUrl") or ""),
            channel_id=str(value.get("channel_id") or value.get("channelId") or ""),
            channel_title=str(value.get("channel_title") or value.get("channelTitle") or ""),
            channel_thumbnail=str(value.get("channel_thumbnail") or value.get("channelThumbnail") or ""),
            id=str(value.get("id") or value.get("project_id") or value.get("projectId") or ""),
            project_type=project_type,
            machine_theme=value.get("machine_theme", value.get("machineTheme", MachineTheme.CLASSIC.value)),
            additional_urls=[str(item) for item in (value.get("additional_urls", value.get("additionalUrls", [])) or []) if str(item).strip()],
            business_config=BusinessConfig.from_dict(business_value) if business_value is not None else None,
            music_config=MusicConfig.from_dict(music_value) if music_value is not None else None,
            tourism_config=TourismConfig.from_dict(tourism_value) if tourism_value is not None else None,
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
            delivery_record=DeliveryRecord.from_dict(value.get("delivery_record", value.get("deliveryRecord"))),
            publication_operation=PublicationOperation.from_dict(value.get("publication_operation", value.get("publicationOperation"))),
            extra_fields=_extra_fields(value, known),
        )
