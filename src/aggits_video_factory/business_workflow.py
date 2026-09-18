from __future__ import annotations

from uuid import uuid4

from .desktop_forms import ValidatedProjectForm
from .models import Project, ProjectType, Video, utc_now
from .supplementary_sources import SupplementarySourceResult
from .youtube_api import ChannelCatalogue


def assemble_business_project(
    *,
    values: ValidatedProjectForm,
    catalogue: ChannelCatalogue,
    selected_videos: list[Video],
    reviewed_videos: list[Video],
    source_results: list[SupplementarySourceResult],
    slug: str,
    existing: Project | None = None,
) -> Project:
    """Create the persisted Business record after the authoritative video review."""
    if values.business_config is None or values.music_config is not None:
        raise ValueError("Validated Business configuration is required.")
    if existing and existing.project_type is not ProjectType.BUSINESS:
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
        project_type=ProjectType.BUSINESS,
        additional_urls=list(values.additional_urls),
        business_config=values.business_config,
        music_config=None,
        source_channel_url=values.channel_url,
        manual_video_urls=list(values.manual_video_urls),
        excluded_video_ids=sorted(excluded_ids),
        videos=list(selected_videos),
        status="changes_pending" if changes_pending else "draft",
        created_at=existing.created_at if existing else utc_now(),
        published_at=existing.published_at if existing else None,
        published_url=existing.published_url if existing else None,
        delivery_status=existing.delivery_status if changes_pending and existing else "not_requested",
        publication_revision=existing.publication_revision if existing else None,
        extra_fields=extra_fields,
    )
