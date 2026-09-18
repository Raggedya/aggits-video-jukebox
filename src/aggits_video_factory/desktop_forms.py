from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from uuid import uuid4

from .config import MAX_TICKER_LENGTH
from .models import BusinessConfig, MusicConfig, PrimaryCta, PrimaryCtaType, Project, ProjectType, utc_now
from .youtube_api import YouTubeClient


CTA_CHOICES: tuple[tuple[str, PrimaryCtaType], ...] = (
    ("Listen on Spotify", PrimaryCtaType.SPOTIFY),
    ("Buy on Bandcamp", PrimaryCtaType.BANDCAMP),
    ("Buy Music", PrimaryCtaType.BUY_MUSIC),
    ("Buy Merch", PrimaryCtaType.MERCH),
    ("Get Tickets", PrimaryCtaType.TICKETS),
    ("Apple Music", PrimaryCtaType.APPLE_MUSIC),
    ("Official Website", PrimaryCtaType.OFFICIAL_WEBSITE),
    ("Custom", PrimaryCtaType.CUSTOM),
)
CTA_LABEL_TO_TYPE = dict(CTA_CHOICES)
CTA_TYPE_TO_LABEL = {cta_type: label for label, cta_type in CTA_CHOICES}
DEFAULT_CTA_LABEL = CTA_CHOICES[0][0]
DEFAULT_STORY = "PULL THE LEVER. LET THE MACHINE CHOOSE WHAT YOU WATCH NEXT."


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


def _clean_urls(values: Iterable[str]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def validate_project_form(values: ProjectFormValues, project_type: ProjectType | str) -> ValidatedProjectForm:
    project_type = ProjectType(project_type)
    title = re.sub(r"\s+", " ", values.title).strip()
    if not title:
        raise FormValidationError("title", "Title is required.")
    if len(title) > 120:
        raise FormValidationError("title", "Title cannot exceed 120 characters.")

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
        if project_type is ProjectType.BUSINESS:
            business_config = BusinessConfig(shop_url=values.shop_url)
            music_config = None
        else:
            cta_type = CTA_LABEL_TO_TYPE.get(values.cta_label)
            if cta_type is None:
                raise FormValidationError("cta_type", "Select a valid Primary Call to Action.")
            primary_cta = PrimaryCta(
                cta_type=cta_type,
                destination_url=values.destination_url,
                custom_label=values.custom_label if cta_type is PrimaryCtaType.CUSTOM else None,
            )
            business_config = None
            music_config = MusicConfig(primary_cta=primary_cta)

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
        elif "custom" in lowered or "label" in lowered:
            field_name = "custom_label"
        elif "destination" in lowered or "cta" in lowered:
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
    )


def project_to_form_values(project: Project) -> ProjectFormValues:
    cta = project.music_config.primary_cta if project.music_config else None
    return ProjectFormValues(
        title=project.title,
        channel_url=project.source_channel_url or project.channel_url,
        additional_urls=list(project.additional_urls),
        story_text=project.ticker_text,
        manual_video_urls=list(project.manual_video_urls),
        shop_url=project.business_config.shop_url or "" if project.business_config else "",
        cta_label=CTA_TYPE_TO_LABEL.get(cta.cta_type, DEFAULT_CTA_LABEL) if cta else DEFAULT_CTA_LABEL,
        destination_url=cta.destination_url if cta else "",
        custom_label=cta.custom_label or "" if cta else "",
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
        extra_fields=dict(existing.extra_fields) if existing else {},
    )


def project_is_visible_in_tab(project: Project, project_type: ProjectType | str) -> bool:
    return project.project_type is ProjectType(project_type)
