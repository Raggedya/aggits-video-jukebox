from __future__ import annotations

from uuid import uuid4

from .desktop_forms import ValidatedProjectForm
from .models import Project, ProjectType, Video, utc_now
from .supplementary_sources import SupplementarySourceResult
from .youtube_api import ChannelCatalogue


def assemble_reviewed_project(
    *,
    project_type: ProjectType,
    values: ValidatedProjectForm,
    catalogue: ChannelCatalogue,
    selected_videos: list[Video],
    reviewed_videos: list[Video],
    source_results: list[SupplementarySourceResult],
    slug: str,
    existing: Project | None = None,
) -> Project:
    """Create a persisted project after the shared authoritative video review."""
    if project_type is ProjectType.BUSINESS:
        if values.business_config is None or values.music_config is not None or values.tourism_config is not None:
            raise ValueError("Validated Business configuration is required.")
    elif project_type is ProjectType.MUSIC:
        if values.music_config is None or values.music_config.primary_cta is None or values.business_config is not None or values.tourism_config is not None:
            raise ValueError("Validated Music configuration is required.")
    elif project_type is ProjectType.TOURISM:
        if values.tourism_config is None or values.business_config is not None or values.music_config is not None:
            raise ValueError("Validated Tourism configuration is required.")
    else:
        raise ValueError(f"Unsupported project type: {project_type!r}.")
    if existing and existing.project_type is not project_type:
        raise ValueError("An existing project cannot change project type.")

    selected_ids = {video.video_id for video in selected_videos}
    reviewed_ids = {video.video_id for video in reviewed_videos}
    excluded_ids = (set(existing.excluded_video_ids) if existing else set()) | (reviewed_ids - selected_ids)
    excluded_ids -= selected_ids
    changes_pending = bool(existing and existing.published_url)
    extra_fields = dict(existing.extra_fields) if existing else {}
    extra_fields["additional_source_context"] = [result.to_dict() for result in source_results]

    return Project(
        slug=existing.slug if existing else slug,
        title=values.title,
        ticker_text=values.story_text,
        channel_url=catalogue.channel_url,
        channel_id=catalogue.channel_id,
        channel_title=catalogue.channel_title,
        channel_thumbnail=catalogue.channel_thumbnail,
        id=existing.id if existing else str(uuid4()),
        project_type=project_type,
        additional_urls=list(values.additional_urls),
        business_config=values.business_config if project_type is ProjectType.BUSINESS else None,
        music_config=values.music_config if project_type is ProjectType.MUSIC else None,
        tourism_config=values.tourism_config if project_type is ProjectType.TOURISM else None,
        source_channel_url=values.channel_url,
        manual_video_urls=list(values.manual_video_urls),
        excluded_video_ids=sorted(excluded_ids),
        # Persist the reviewed catalogue, not only today's included subset.
        # Inclusion remains authoritative in excluded_video_ids so an operator
        # can later re-enable a known video without spending API quota again.
        videos=list(reviewed_videos),
        status="changes_pending" if changes_pending else "draft",
        created_at=existing.created_at if existing else utc_now(),
        published_at=existing.published_at if existing else None,
        published_url=existing.published_url if existing else None,
        delivery_status=existing.delivery_status if changes_pending and existing else "not_requested",
        publication_revision=existing.publication_revision if existing else None,
        delivery_record=existing.delivery_record if existing else None,
        publication_operation=existing.publication_operation if existing else None,
        extra_fields=extra_fields,
    )


def assemble_business_project(**kwargs) -> Project:
    """Compatibility entry point for the approved Business workflow."""
    return assemble_reviewed_project(project_type=ProjectType.BUSINESS, **kwargs)


def assemble_music_project(**kwargs) -> Project:
    """Music adapter over the same reviewed-project assembly service."""
    return assemble_reviewed_project(project_type=ProjectType.MUSIC, **kwargs)


def assemble_tourism_project(**kwargs) -> Project:
    """Tourism adapter over the same reviewed-project assembly service."""
    return assemble_reviewed_project(project_type=ProjectType.TOURISM, **kwargs)
