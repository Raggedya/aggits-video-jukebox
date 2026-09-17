from pathlib import Path

from aggits_video_factory.models import Project, Video
from aggits_video_factory.site_builder import build_project_site


def video(video_id: str, title: str) -> Video:
    return Video(
        video_id=video_id,
        title=title,
        display_title=title,
        url=f"https://www.youtube.com/watch?v={video_id}",
        embed_url=f"https://www.youtube.com/embed/{video_id}?enablejsapi=1&autoplay=0&playsinline=1&rel=0",
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        published_at="2026-09-01T00:00:00Z",
        duration_seconds=220,
        channel_title="The Midnight Assembly",
    )


project = Project(
    slug="midnight-assembly",
    title="THE MIDNIGHT ASSEMBLY",
    ticker_text="STRANGE TRANSMISSIONS FROM THE EDGE OF THE CITY · PULL THE LEVER AND LET THE MACHINE CHOOSE",
    channel_url="https://www.youtube.com/@YouTubeCreators",
    channel_id="UCsample",
    channel_title="The Midnight Assembly",
    channel_thumbnail="",
    videos=[
        video("M7lc1UVf-VE", "LOST IN THE STATIC"),
        video("dQw4w9WgXcQ", "NIGHT DRIVE SIGNAL"),
        video("aqz-KE-bpKQ", "THE LAST TRANSMISSION"),
        video("ysz5S6PUM-U", "BLACK GLASS CITY"),
        video("jNQXAC9IVRw", "AFTER THE LIGHTS GO OUT"),
    ],
)

destination = Path(__file__).resolve().parents[1] / "_qa" / "midnight-assembly"
build_project_site(project, destination)
print(destination)
