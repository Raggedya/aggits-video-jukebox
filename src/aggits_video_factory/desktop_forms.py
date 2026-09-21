from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from uuid import uuid4

from .config import MAX_TICKER_LENGTH
from .models import (
    BusinessConfig, MachineTheme, MusicConfig, PrimaryCta, PrimaryCtaType, Project, ProjectType,
    TourismConfig, project_primary_cta, utc_now,
)
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
CTA_CHOICES_BY_PROJECT = {
    ProjectType.BUSINESS: BUSINESS_CTA_CHOICES,
    ProjectType.MUSIC: CTA_CHOICES,
    ProjectType.TOURISM: TOURISM_CTA_CHOICES,
}
CTA_LABEL_TO_TYPE_BY_PROJECT = {kind: dict(choices) for kind, choices in CTA_CHOICES_BY_PROJECT.items()}
CTA_TYPE_TO_LABEL_BY_PROJECT = {kind: {cta_type: label for label, cta_type in choices} for kind, choices in CTA_CHOICES_BY_PROJECT.items()}
CTA_LABEL_TO_TYPE = dict(CTA_CHOICES)  # Backward-compatible Music aliases.
CTA_TYPE_TO_LABEL = {cta_type: label for label, cta_type in CTA_CHOICES}
DEFAULT_CTA_LABEL = CTA_CHOICES[0][0]
DEFAULT_CTA_LABEL_BY_PROJECT = {kind: choices[0][0] for kind, choices in CTA_CHOICES_BY_PROJECT.items()}
MACHINE_THEME_CHOICES: tuple[tuple[str, MachineTheme], ...] = (
    ("Classic", MachineTheme.CLASSIC),
    ("Candy", MachineTheme.CANDY),
)
MACHINE_THEME_LABEL_TO_VALUE = dict(MACHINE_THEME_CHOICES)
MACHINE_THEME_VALUE_TO_LABEL = {value: label for label, value in MACHINE_THEME_CHOICES}
DEFAULT_MACHINE_THEME_LABEL = MACHINE_THEME_CHOICES[0][0]
DEFAULT_STORY = "PULL THE LEVER. LET THE MACHINE CHOOSE WHAT YOU WATCH NEXT."


class FormValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(slots=True)
class ProjectFormValues:
    title: str = ""
    machine_theme: str = DEFAULT_MACHINE_THEME_LABEL
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

    def comparable(self) -> tuple[object, ...]:
        return (
            self.title,
            self.machine_theme,
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
        )


@dataclass(frozen=True, slots=True)
class ValidatedProjectForm:
    title: str
    machine_theme: MachineTheme
    channel_url: str
    additional_urls: list[str]
    story_text: str
    manual_video_urls: list[str]
    business_config: BusinessConfig | None
    music_config: MusicConfig | None
    tourism_config: TourismConfig | None


def _clean_urls(values: Iterable[str]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def validate_project_form(values: ProjectFormValues, project_type: ProjectType | str) -> ValidatedProjectForm:
    project_type = ProjectType(project_type)
    title = re.sub(r"\s+", " ", values.title).strip()
    if not title:
        raise FormValidationError("title", "Title is required.")
    if len(title) > 120:
        raise FormValidationError("title", "Title cannot exceed 120 characters.")

    machine_theme = MACHINE_THEME_LABEL_TO_VALUE.get(values.machine_theme)
    if machine_theme is None:
        raise FormValidationError("machine_theme", "Select a valid Machine Theme.")

    channel_url = values.channel_url.strip()
    manual_urls = _clean_urls(values.manual_video_urls)
    if not channel_url and not manual_urls:
        raise FormValidationError("channel_url", "Add a YouTube channel URL or at least one individual YouTube video.")
    invalid_videos = [url for url in manual_urls if not YouTubeClient.video_id_from_url(url)]
    if invalid_videos:
        raise FormValidationError("manual_video_urls", "One or more individual YouTube video links are invalid.")

    story_text = values.story_text.strip()
    if len(story_text) > MAX_TICKER_LENGTH:
        raise FormValidationError("story_text", f"Bio / Story Information cannot exceed {MAX_TICKER_LENGTH} characters.")

    additional_urls = _clean_urls(values.additional_urls)
    if len(additional_urls) > 3:
        raise FormValidationError("additional_urls", "A project can contain no more than three additional URLs.")

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
        if project_type is ProjectType.BUSINESS:
            legacy_shop_url = destination_url if cta_type is PrimaryCtaType.SHOP_NOW and destination_url else values.shop_url
            business_config = BusinessConfig(shop_url=legacy_shop_url or None, primary_cta=primary_cta)
            music_config = None
            tourism_config = None
        elif project_type is ProjectType.MUSIC:
            business_config = None
            music_config = MusicConfig(primary_cta=primary_cta)
            tourism_config = None
        else:
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

        # Project construction is the authoritative validation for shared URL
        # limits and type-specific configuration.
        validated = Project(
            slug="form-validation",
            title=title,
            machine_theme=machine_theme,
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
        elif "custom" in lowered or "label" in lowered:
            field_name = "custom_label"
        elif "cta" in lowered:
            field_name = "destination_url"
        else:
            field_name = "additional_urls"
        raise FormValidationError(field_name, message) from error

    return ValidatedProjectForm(
        title=validated.title,
        machine_theme=validated.machine_theme,
        channel_url=channel_url,
        additional_urls=list(validated.additional_urls),
        story_text=validated.ticker_text,
        manual_video_urls=manual_urls,
        business_config=validated.business_config,
        music_config=validated.music_config,
        tourism_config=validated.tourism_config,
    )


def project_to_form_values(project: Project) -> ProjectFormValues:
    cta = project_primary_cta(project)
    default_label = DEFAULT_CTA_LABEL_BY_PROJECT[project.project_type]
    return ProjectFormValues(
        title=project.title,
        machine_theme=MACHINE_THEME_VALUE_TO_LABEL[project.machine_theme],
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
        machine_theme=values.machine_theme,
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
