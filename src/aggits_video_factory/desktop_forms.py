from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .banjo import BANJO_TITLE, validate_sponsor_logo, validate_sponsor_mp4
from .config import MAX_BANJO_VIDEOS, MAX_CHANNEL_MASTER_VIDEOS, ticker_limit_for_project_type
from .models import (
    BusinessConfig, ChannelMasterConfig, MusicConfig, PrimaryCta, PrimaryCtaType, Project, ProjectType,
    TourismConfig, WhiteLabelConfig, project_primary_cta, utc_now,
)
from .white_label import inspect_white_label_logo
from .youtube_api import YouTubeClient


CTA_CHOICES: tuple[tuple[str, PrimaryCtaType], ...] = (
    ("Listen on Spotify", PrimaryCtaType.SPOTIFY),
    ("Buy on Bandcamp", PrimaryCtaType.BANDCAMP),
    ("Buy Music", PrimaryCtaType.BUY_MUSIC),
    ("Buy Merch", PrimaryCtaType.MERCH),
    ("Get Tickets", PrimaryCtaType.TICKETS),
    ("Apple Music", PrimaryCtaType.APPLE_MUSIC),
    ("Official Website", PrimaryCtaType.OFFICIAL_WEBSITE),
    ("Book Now", PrimaryCtaType.BOOK_NOW),
    ("Book Us", PrimaryCtaType.BOOK_US),
    ("SoundCloud", PrimaryCtaType.SOUNDCLOUD),
    ("Custom", PrimaryCtaType.CUSTOM),
)
BUSINESS_CTA_CHOICES: tuple[tuple[str, PrimaryCtaType], ...] = (
    ("Shop Now", PrimaryCtaType.SHOP_NOW),
    ("View Products", PrimaryCtaType.VIEW_PRODUCTS),
    ("Get a Quote", PrimaryCtaType.GET_A_QUOTE),
    ("Book Now", PrimaryCtaType.BOOK_NOW),
    ("Enquire Now", PrimaryCtaType.ENQUIRE_NOW),
    ("Find a Store", PrimaryCtaType.FIND_A_STORE),
    ("Find a Dealer", PrimaryCtaType.FIND_A_DEALER),
    ("Book a Demo", PrimaryCtaType.BOOK_A_DEMO),
    ("Contact Us", PrimaryCtaType.CONTACT_US),
    ("Visit Website", PrimaryCtaType.VISIT_WEBSITE),
    ("Custom", PrimaryCtaType.CUSTOM),
)
TOURISM_CTA_CHOICES: tuple[tuple[str, PrimaryCtaType], ...] = (
    ("More Info", PrimaryCtaType.MORE_INFO),
    ("Stay", PrimaryCtaType.STAY),
    ("Explore", PrimaryCtaType.EXPLORE),
    ("Book Now", PrimaryCtaType.BOOK_NOW),
    ("What's On", PrimaryCtaType.WHATS_ON),
    ("Plan Your Visit", PrimaryCtaType.PLAN_YOUR_VISIT),
    ("Visit Website", PrimaryCtaType.VISIT_WEBSITE),
    ("Custom", PrimaryCtaType.CUSTOM),
)


def _channel_master_cta_choices() -> tuple[tuple[str, PrimaryCtaType], ...]:
    """Controlled current-head union; first approved display order wins."""
    result: list[tuple[str, PrimaryCtaType]] = []
    seen: set[PrimaryCtaType] = set()
    custom_choice: tuple[str, PrimaryCtaType] | None = None
    for choice in (*BUSINESS_CTA_CHOICES, *CTA_CHOICES, *TOURISM_CTA_CHOICES):
        if choice[1] is PrimaryCtaType.CUSTOM:
            custom_choice = custom_choice or choice
            continue
        if choice[1] not in seen:
            result.append(choice)
            seen.add(choice[1])
    if custom_choice:
        result.append(custom_choice)
    return tuple(result)


CHANNEL_MASTER_CTA_CHOICES = _channel_master_cta_choices()
CTA_CHOICES_BY_PROJECT = {
    ProjectType.BUSINESS: BUSINESS_CTA_CHOICES,
    ProjectType.MUSIC: CTA_CHOICES,
    ProjectType.TOURISM: TOURISM_CTA_CHOICES,
    ProjectType.BANJO: (),
    ProjectType.CHANNEL_MASTER: CHANNEL_MASTER_CTA_CHOICES,
    ProjectType.WHITE_LABEL: CHANNEL_MASTER_CTA_CHOICES,
}
CTA_LABEL_TO_TYPE_BY_PROJECT = {kind: dict(choices) for kind, choices in CTA_CHOICES_BY_PROJECT.items()}
CTA_TYPE_TO_LABEL_BY_PROJECT = {kind: {cta_type: label for label, cta_type in choices} for kind, choices in CTA_CHOICES_BY_PROJECT.items()}
CTA_LABEL_TO_TYPE = dict(CTA_CHOICES)  # Backward-compatible Music aliases.
CTA_TYPE_TO_LABEL = {cta_type: label for label, cta_type in CTA_CHOICES}
DEFAULT_CTA_LABEL = CTA_CHOICES[0][0]
DEFAULT_CTA_LABEL_BY_PROJECT = {kind: choices[0][0] if choices else "" for kind, choices in CTA_CHOICES_BY_PROJECT.items()}
DEFAULT_STORY = "PULL THE LEVER. LET THE MACHINE CHOOSE WHAT YOU WATCH NEXT."
MAX_INDIVIDUAL_VIDEO_URLS = 25


def manual_url_limit_for_project_type(project_type: ProjectType | str) -> int:
    kind = ProjectType(project_type)
    if kind is ProjectType.BANJO:
        return MAX_BANJO_VIDEOS
    if kind in {ProjectType.CHANNEL_MASTER, ProjectType.WHITE_LABEL}:
        return MAX_CHANNEL_MASTER_VIDEOS
    return MAX_INDIVIDUAL_VIDEO_URLS


class FormValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(slots=True)
class ProjectFormValues:
    title: str = ""
    channel_url: str = ""
    additional_urls: list[str] = field(default_factory=list)
    story_text: str = DEFAULT_STORY
    manual_video_urls: list[str] = field(default_factory=list)
    shop_url: str = ""
    cta_label: str = DEFAULT_CTA_LABEL
    destination_url: str = ""
    custom_label: str = ""
    more_info_url: str = ""
    stay_url: str = ""
    banjo_choice_urls: list[str] = field(default_factory=list)
    banjo_choice_titles: list[str] = field(default_factory=list)
    banjo_choice_active: list[bool] = field(default_factory=list)
    sponsor_active: bool = False
    sponsor_title: str = ""
    sponsor_url: str = ""
    sponsor_logo_path: str = ""
    sponsor_creative_paths: list[str] = field(default_factory=list)
    sponsor_creative_active: list[bool] = field(default_factory=list)
    palette: str = "MIDNIGHT"
    custom_primary: str = "#172033"
    custom_accent: str = "#6D80AF"
    contact_url: str = ""
    custom_logo_path: str = ""

    def comparable(self) -> tuple[object, ...]:
        return (
            self.title,
            self.channel_url,
            tuple(self.additional_urls),
            self.story_text,
            tuple(self.manual_video_urls),
            self.shop_url,
            self.cta_label,
            self.destination_url,
            self.custom_label,
            self.more_info_url,
            self.stay_url,
            tuple(self.banjo_choice_urls),
            tuple(self.banjo_choice_titles),
            tuple(self.banjo_choice_active),
            bool(self.sponsor_active),
            self.sponsor_title,
            self.sponsor_url,
            self.sponsor_logo_path,
            tuple(self.sponsor_creative_paths),
            tuple(self.sponsor_creative_active),
            self.palette,
            self.custom_primary,
            self.custom_accent,
            self.contact_url,
            self.custom_logo_path,
        )


@dataclass(frozen=True, slots=True)
class ValidatedProjectForm:
    title: str
    channel_url: str
    additional_urls: list[str]
    story_text: str
    manual_video_urls: list[str]
    business_config: BusinessConfig | None
    music_config: MusicConfig | None
    tourism_config: TourismConfig | None
    channel_master_config: ChannelMasterConfig | None = None
    white_label_config: WhiteLabelConfig | None = None
    banjo_choice_urls: list[str] = field(default_factory=list)
    banjo_choice_titles: list[str] = field(default_factory=list)
    banjo_choice_active: list[bool] = field(default_factory=list)
    sponsor_active: bool = False
    sponsor_title: str = ""
    sponsor_url: str = ""
    sponsor_logo_path: str = ""
    sponsor_creative_paths: list[str] = field(default_factory=list)
    sponsor_creative_active: list[bool] = field(default_factory=list)


def _clean_urls(values: Iterable[str]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def youtube_urls_for_project_review(
    values: ValidatedProjectForm,
    project_type: ProjectType | str,
) -> list[str]:
    """Return explicit videos to resolve, automatically including Banjo awards."""
    candidates = list(values.manual_video_urls)
    if ProjectType(project_type) is ProjectType.BANJO:
        candidates.extend(values.banjo_choice_urls)
    result: list[str] = []
    seen: set[str] = set()
    for url in candidates:
        video_id = YouTubeClient.video_id_from_url(url)
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        result.append(url)
    return result


def validate_project_form(values: ProjectFormValues, project_type: ProjectType | str) -> ValidatedProjectForm:
    project_type = ProjectType(project_type)
    title = BANJO_TITLE if project_type is ProjectType.BANJO else re.sub(r"\s+", " ", values.title).strip()
    if not title:
        raise FormValidationError("title", "Title is required.")
    if len(title) > 120:
        raise FormValidationError("title", "Title cannot exceed 120 characters.")

    channel_url = values.channel_url.strip()
    additional_urls = _clean_urls(values.additional_urls)
    if len(additional_urls) > 3:
        raise FormValidationError("additional_urls", "A project can contain no more than three additional URLs.")

    manual_urls = _clean_urls(values.manual_video_urls)
    if project_type in {ProjectType.MUSIC, ProjectType.BANJO}:
        # Festival and multi-artist Music projects do not need a channel. If a
        # YouTube video was pasted into an Additional Web Page field, route it
        # into the authoritative individual-video list instead of attempting
        # to download the YouTube watch page as supplementary prose.
        supplementary_urls: list[str] = []
        for url in additional_urls:
            if YouTubeClient.video_id_from_url(url):
                manual_urls.append(url)
            else:
                supplementary_urls.append(url)
        additional_urls = supplementary_urls

    invalid_videos = [url for url in manual_urls if not YouTubeClient.video_id_from_url(url)]
    if invalid_videos:
        raise FormValidationError("manual_video_urls", "One or more individual YouTube video links are invalid.")
    unique_manual_urls: list[str] = []
    seen_video_ids: set[str] = set()
    for url in manual_urls:
        video_id = YouTubeClient.video_id_from_url(url)
        if video_id in seen_video_ids:
            continue
        seen_video_ids.add(video_id)
        unique_manual_urls.append(url)
    manual_urls = unique_manual_urls
    manual_limit = manual_url_limit_for_project_type(project_type)
    if len(manual_urls) > manual_limit:
        raise FormValidationError(
            "manual_video_urls",
            f"No more than {manual_limit} individual YouTube videos can be added during project creation.",
        )

    choice_rows: list[tuple[str, str, bool]] = []
    if project_type is ProjectType.BANJO:
        choice_rows = [
            (str(url or "").strip(), str(values.banjo_choice_titles[index] if index < len(values.banjo_choice_titles) else "").strip(),
             bool(values.banjo_choice_active[index]) if index < len(values.banjo_choice_active) else True)
            for index, url in enumerate(values.banjo_choice_urls)
            if str(url or "").strip()
        ]
        choice_urls = [row[0] for row in choice_rows]
        choice_titles = [row[1] for row in choice_rows]
        choice_active = [row[2] for row in choice_rows]
        if len(choice_urls) > 4 or sum(choice_active) > 4:
            raise FormValidationError("banjo_choices", "A Banjo project can have no more than four active Banjo's Choice awards.")
        choice_video_ids = [YouTubeClient.video_id_from_url(url) for url in choice_urls]
        if any(not video_id for video_id in choice_video_ids):
            raise FormValidationError("banjo_choices", "Banjo's Choice entries must use recognised YouTube video URLs.")
        if len(choice_video_ids) != len(set(choice_video_ids)):
            raise FormValidationError("banjo_choices", "Each Banjo's Choice award must use a different YouTube video.")
        if any(len(choice_title) > 80 for choice_title in choice_titles):
            raise FormValidationError("banjo_choices", "Banjo's Choice display titles cannot exceed 80 characters.")
        combined_video_ids = seen_video_ids | set(choice_video_ids)
        if len(combined_video_ids) > manual_limit:
            raise FormValidationError(
                "banjo_choices",
                f"Banjo YouTube videos, including Banjo's Choice awards, cannot exceed {manual_limit} in total.",
            )

    if not channel_url and not manual_urls and not choice_rows:
        raise FormValidationError(
            "channel_url",
            "Add a YouTube channel URL or an individual YouTube video."
            if project_type in {ProjectType.CHANNEL_MASTER, ProjectType.WHITE_LABEL}
            else "Add a YouTube channel URL, an individual YouTube video, or a Banjo's Choice video.",
        )

    story_text = values.story_text.strip()
    ticker_limit = ticker_limit_for_project_type(project_type)
    if len(story_text) > ticker_limit:
        label = (
            "Banjo Ticker Text" if project_type is ProjectType.BANJO
            else "Ticker Text" if project_type in {ProjectType.CHANNEL_MASTER, ProjectType.WHITE_LABEL}
            else "Bio / Story Information"
        )
        raise FormValidationError("story_text", f"{label} cannot exceed {ticker_limit} characters.")

    if project_type is ProjectType.BANJO:
        choice_urls = [row[0] for row in choice_rows]
        choice_titles = [row[1] for row in choice_rows]
        choice_active = [row[2] for row in choice_rows]
        sponsor_title = str(values.sponsor_title or "").strip()
        sponsor_url = str(values.sponsor_url or "").strip()
        if len(sponsor_title) > 40:
            raise FormValidationError("sponsor_title", "Sponsor Title cannot exceed 40 characters.")
        if values.sponsor_active and (not sponsor_title or not sponsor_url):
            raise FormValidationError("sponsor_title", "Active sponsorship requires Sponsor Title and Sponsor URL.")
        if sponsor_url:
            try:
                PrimaryCta(PrimaryCtaType.CUSTOM, sponsor_url, custom_label="SPONSOR")
            except ValueError as error:
                raise FormValidationError("sponsor_url", str(error)) from error
        sponsor_logo_path = str(values.sponsor_logo_path or "").strip()
        if sponsor_logo_path and not sponsor_logo_path.replace("\\", "/").startswith("assets/sponsor-logo-"):
            try:
                validate_sponsor_logo(Path(sponsor_logo_path))
            except ValueError as error:
                raise FormValidationError("sponsor_logo", str(error)) from error
        creative_rows = [
            (str(path or "").strip(), bool(values.sponsor_creative_active[index]) if index < len(values.sponsor_creative_active) else True)
            for index, path in enumerate(values.sponsor_creative_paths)
            if str(path or "").strip()
        ]
        creative_paths = [row[0] for row in creative_rows]
        if len(creative_paths) > 4:
            raise FormValidationError("sponsor_creatives", "A Banjo project can contain no more than four sponsor MP4s.")
        for path in creative_paths:
            # Existing project-relative assets are validated during build. New
            # operator selections are validated before any project mutation.
            if not path.replace("\\", "/").startswith("assets/sponsor-"):
                try:
                    validate_sponsor_mp4(Path(path))
                except ValueError as error:
                    raise FormValidationError("sponsor_creatives", str(error)) from error
        return ValidatedProjectForm(
            title=BANJO_TITLE, channel_url=channel_url, additional_urls=[], story_text=story_text,
            manual_video_urls=manual_urls, business_config=None, music_config=None, tourism_config=None,
            banjo_choice_urls=choice_urls,
            banjo_choice_titles=choice_titles[:len(choice_urls)],
            banjo_choice_active=choice_active[:len(choice_urls)],
            sponsor_active=bool(values.sponsor_active), sponsor_title=sponsor_title, sponsor_url=sponsor_url,
            sponsor_logo_path=sponsor_logo_path,
            sponsor_creative_paths=creative_paths,
            sponsor_creative_active=[row[1] for row in creative_rows],
        )

    try:
        selected_label = values.cta_label
        # ProjectFormValues predates per-type CTA selectors and its historical
        # default is the Music default.  Treat that untouched constructor
        # default as "use this project's default" for compatibility.
        if selected_label == DEFAULT_CTA_LABEL and selected_label not in CTA_LABEL_TO_TYPE_BY_PROJECT[project_type]:
            selected_label = DEFAULT_CTA_LABEL_BY_PROJECT[project_type]
        cta_type = CTA_LABEL_TO_TYPE_BY_PROJECT[project_type].get(selected_label)
        if cta_type is None:
            raise FormValidationError("cta_type", "Select a valid Primary Call to Action.")
        destination_url = values.destination_url
        if project_type is ProjectType.BUSINESS and cta_type is PrimaryCtaType.SHOP_NOW and not destination_url.strip():
            destination_url = values.shop_url
        elif project_type is ProjectType.TOURISM and not destination_url.strip():
            if cta_type is PrimaryCtaType.MORE_INFO:
                destination_url = values.more_info_url
            elif cta_type is PrimaryCtaType.STAY:
                destination_url = values.stay_url
        primary_cta = PrimaryCta(
            cta_type=cta_type,
            destination_url=destination_url,
            custom_label=values.custom_label if cta_type is PrimaryCtaType.CUSTOM else None,
        )
        channel_master_config = None
        white_label_config = None
        if project_type is ProjectType.BUSINESS:
            legacy_shop_url = destination_url if cta_type is PrimaryCtaType.SHOP_NOW and destination_url else values.shop_url
            business_config = BusinessConfig(shop_url=legacy_shop_url or None, primary_cta=primary_cta)
            music_config = None
            tourism_config = None
        elif project_type is ProjectType.MUSIC:
            business_config = None
            music_config = MusicConfig(primary_cta=primary_cta)
            tourism_config = None
        elif project_type is ProjectType.TOURISM:
            business_config = None
            music_config = None
            legacy_more_info_url = values.more_info_url
            legacy_stay_url = values.stay_url
            if cta_type is PrimaryCtaType.MORE_INFO and destination_url:
                legacy_more_info_url = destination_url
            elif cta_type is PrimaryCtaType.STAY and destination_url:
                legacy_stay_url = destination_url
            tourism_config = TourismConfig(
                more_info_url=legacy_more_info_url or None,
                stay_url=legacy_stay_url or None,
                primary_cta=primary_cta,
            )
        else:
            business_config = None
            music_config = None
            tourism_config = None
            channel_master_config = ChannelMasterConfig(
                palette=values.palette,
                custom_primary=values.custom_primary,
                custom_accent=values.custom_accent,
                primary_cta=primary_cta,
                contact_url=values.contact_url,
            )
            if project_type is ProjectType.WHITE_LABEL:
                logo_path = str(values.custom_logo_path or "").strip()
                if not logo_path:
                    raise FormValidationError("custom_logo", "Please upload a logo before saving this White Label project.")
                try:
                    details = inspect_white_label_logo(Path(logo_path))
                except ValueError as error:
                    raise FormValidationError("custom_logo", str(error)) from error
                white_label_config = WhiteLabelConfig(
                    logo_asset_path=str(details.source),
                    original_filename=details.source.name,
                    media_type=details.media_type,
                    width=details.width,
                    height=details.height,
                )

        # Project construction is the authoritative validation for shared URL
        # limits and type-specific configuration.
        validated = Project(
            slug="form-validation",
            title=title,
            ticker_text=story_text,
            channel_url=channel_url,
            channel_id="",
            channel_title="",
            channel_thumbnail="",
            project_type=project_type,
            additional_urls=additional_urls,
            business_config=business_config,
            music_config=music_config,
            tourism_config=tourism_config,
            channel_master_config=channel_master_config,
            white_label_config=white_label_config,
            source_channel_url=channel_url,
            manual_video_urls=manual_urls,
        )
    except FormValidationError:
        raise
    except ValueError as error:
        message = str(error)
        lowered = message.casefold()
        if "shop" in lowered:
            field_name = "shop_url"
        elif "more info" in lowered:
            field_name = "more_info_url"
        elif "stay" in lowered:
            field_name = "stay_url"
        elif "destination" in lowered:
            field_name = "destination_url"
        elif "contact url" in lowered:
            field_name = "contact_url"
        elif "primary colour" in lowered:
            field_name = "custom_primary"
        elif "accent colour" in lowered:
            field_name = "custom_accent"
        elif "palette" in lowered:
            field_name = "palette"
        elif "custom" in lowered or "label" in lowered:
            field_name = "custom_label"
        elif "cta" in lowered:
            field_name = "destination_url"
        else:
            field_name = "additional_urls"
        raise FormValidationError(field_name, message) from error

    return ValidatedProjectForm(
        title=validated.title,
        channel_url=channel_url,
        additional_urls=list(validated.additional_urls),
        story_text=validated.ticker_text,
        manual_video_urls=manual_urls,
        business_config=validated.business_config,
        music_config=validated.music_config,
        tourism_config=validated.tourism_config,
        channel_master_config=validated.channel_master_config,
        white_label_config=validated.white_label_config,
    )


def project_to_form_values(project: Project) -> ProjectFormValues:
    if project.project_type is ProjectType.BANJO:
        config = project.banjo_config
        choices = list(config.banjos_choice) if config else []
        sponsor = config.sponsor if config else None
        by_id = {video.video_id: video.url for video in project.videos}
        return ProjectFormValues(
            title=BANJO_TITLE,
            channel_url=project.source_channel_url or project.channel_url,
            manual_video_urls=list(project.manual_video_urls),
            story_text=project.ticker_text,
            cta_label="",
            banjo_choice_urls=[by_id.get(item.video_id, "") for item in choices],
            banjo_choice_titles=[item.display_title for item in choices],
            banjo_choice_active=[item.active for item in choices],
            sponsor_active=bool(sponsor and sponsor.active),
            sponsor_title=sponsor.title if sponsor else "",
            sponsor_url=sponsor.url or "" if sponsor else "",
            sponsor_logo_path=sponsor.logo_asset_path if sponsor else "",
            sponsor_creative_paths=[item.asset_path for item in sponsor.creatives] if sponsor else [],
            sponsor_creative_active=[item.active for item in sponsor.creatives] if sponsor else [],
        )
    cta = project_primary_cta(project)
    default_label = DEFAULT_CTA_LABEL_BY_PROJECT[project.project_type]
    channel_master = (
        project.channel_master_config
        if project.project_type in {ProjectType.CHANNEL_MASTER, ProjectType.WHITE_LABEL}
        else None
    )
    return ProjectFormValues(
        title=project.title,
        channel_url=project.source_channel_url or project.channel_url,
        additional_urls=list(project.additional_urls),
        story_text=project.ticker_text,
        manual_video_urls=list(project.manual_video_urls),
        shop_url=project.business_config.shop_url or "" if project.business_config else "",
        cta_label=CTA_TYPE_TO_LABEL_BY_PROJECT[project.project_type].get(cta.cta_type, default_label) if cta else default_label,
        destination_url=cta.destination_url if cta else "",
        custom_label=cta.custom_label or "" if cta else "",
        more_info_url=project.tourism_config.more_info_url or "" if project.tourism_config else "",
        stay_url=project.tourism_config.stay_url or "" if project.tourism_config else "",
        palette=channel_master.palette if channel_master else "MIDNIGHT",
        custom_primary=channel_master.custom_primary or "#172033" if channel_master else "#172033",
        custom_accent=channel_master.custom_accent or "#6D80AF" if channel_master else "#6D80AF",
        contact_url=channel_master.contact_url or "" if channel_master else "",
        custom_logo_path=(
            project.white_label_config.logo_asset_path
            if project.project_type is ProjectType.WHITE_LABEL and project.white_label_config
            else ""
        ),
    )


def build_local_music_project(
    values: ValidatedProjectForm,
    slug: str,
    existing: Project | None = None,
) -> Project:
    if values.music_config is None:
        raise ValueError("Music configuration is required for a Music project.")
    if existing and existing.project_type is not ProjectType.MUSIC:
        raise ValueError("An existing project cannot change project type.")
    return Project(
        slug=existing.slug if existing else slug,
        title=values.title,
        ticker_text=values.story_text,
        channel_url=existing.channel_url if existing else values.channel_url,
        channel_id=existing.channel_id if existing else "",
        channel_title=existing.channel_title if existing else values.title,
        channel_thumbnail=existing.channel_thumbnail if existing else "",
        id=existing.id if existing else str(uuid4()),
        project_type=ProjectType.MUSIC,
        additional_urls=list(values.additional_urls),
        business_config=None,
        music_config=values.music_config,
        tourism_config=None,
        source_channel_url=values.channel_url,
        manual_video_urls=list(values.manual_video_urls),
        excluded_video_ids=list(existing.excluded_video_ids) if existing else [],
        videos=list(existing.videos) if existing else [],
        status=existing.status if existing else "draft",
        created_at=existing.created_at if existing else utc_now(),
        published_at=existing.published_at if existing else None,
        published_url=existing.published_url if existing else None,
        delivery_status=existing.delivery_status if existing else "not_requested",
        publication_revision=existing.publication_revision if existing else None,
        delivery_record=existing.delivery_record if existing else None,
        publication_operation=existing.publication_operation if existing else None,
        extra_fields=dict(existing.extra_fields) if existing else {},
    )


def project_is_visible_in_tab(project: Project, project_type: ProjectType | str) -> bool:
    return project.project_type is ProjectType(project_type)
