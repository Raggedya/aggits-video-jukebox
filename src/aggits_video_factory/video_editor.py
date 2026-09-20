from __future__ import annotations

from dataclasses import dataclass

from .config import MAX_VIDEOS
from .models import Project, Video
from .youtube_api import YouTubeClient, YouTubeError


class VideoEditError(ValueError):
    """A recoverable operator error in the saved-project video editor."""


@dataclass(frozen=True, slots=True)
class AddVideoResult:
    video: Video
    reinstated: bool = False


class VideoSelectionSession:
    """Isolated working copy for one saved project's video selection.

    The source project is never mutated.  This makes Cancel exact and keeps
    network resolution separate from the eventual atomic ProjectStore save.
    """

    def __init__(self, project: Project, maximum: int = MAX_VIDEOS) -> None:
        self._source = project
        self.maximum = max(1, min(MAX_VIDEOS, int(maximum)))
        self.videos = [Video.from_dict(video.to_dict()) for video in project.videos]
        known_ids = {video.video_id for video in self.videos}
        self.excluded_ids = {video_id for video_id in project.excluded_video_ids if video_id in known_ids}
        self.unknown_excluded_ids = {video_id for video_id in project.excluded_video_ids if video_id not in known_ids}
        self.manual_video_urls = list(project.manual_video_urls)

    @property
    def included_count(self) -> int:
        return sum(video.video_id not in self.excluded_ids for video in self.videos)

    def is_included(self, video_id: str) -> bool:
        return video_id not in self.excluded_ids

    def set_included(self, video_id: str, included: bool) -> None:
        if video_id not in {video.video_id for video in self.videos}:
            raise VideoEditError("That video is not part of this project.")
        if included:
            if video_id in self.excluded_ids and self.included_count >= self.maximum:
                raise VideoEditError(f"Maximum {self.maximum} videos can be included.")
            self.excluded_ids.discard(video_id)
        else:
            self.excluded_ids.add(video_id)

    def add_url(self, url: str, client: YouTubeClient) -> AddVideoResult:
        cleaned = str(url or "").strip()
        video_id = YouTubeClient.video_id_from_url(cleaned)
        if not video_id:
            raise VideoEditError("Enter a recognised individual YouTube video URL.")
        existing = next((video for video in self.videos if video.video_id == video_id), None)
        if existing:
            if video_id in self.excluded_ids:
                self.set_included(video_id, True)
                return AddVideoResult(video=existing, reinstated=True)
            raise VideoEditError("That video is already included in this project.")
        if self.included_count >= self.maximum:
            raise VideoEditError(f"Maximum {self.maximum} videos can be included.")
        try:
            catalogue = client.fetch_videos([cleaned])
        except YouTubeError:
            raise
        if not catalogue.videos:
            raise VideoEditError("The YouTube video could not be resolved.")
        video = catalogue.videos[0]
        if any(item.video_id == video.video_id for item in self.videos):
            raise VideoEditError("That video is already present in this project.")
        self.videos.append(Video.from_dict(video.to_dict()))
        self.excluded_ids.discard(video.video_id)
        if not any(YouTubeClient.video_id_from_url(item) == video.video_id for item in self.manual_video_urls):
            self.manual_video_urls.append(cleaned)
        return AddVideoResult(video=video)

    def revised_project(self) -> Project:
        if self.included_count < 1:
            raise VideoEditError("At least one video must be included.")
        if self.included_count > self.maximum:
            raise VideoEditError(f"Maximum {self.maximum} videos can be included.")
        revised = Project.from_dict(self._source.to_dict())
        revised.videos = [Video.from_dict(video.to_dict()) for video in self.videos]
        revised.excluded_video_ids = sorted(self.excluded_ids | self.unknown_excluded_ids)
        revised.manual_video_urls = list(self.manual_video_urls)
        if revised.published_url or revised.status == "published":
            revised.status = "changes_pending"
        return revised
