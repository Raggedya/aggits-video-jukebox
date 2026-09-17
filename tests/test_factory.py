from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aggits_video_factory.models import Project, Video
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore, slugify
from aggits_video_factory.youtube_api import YouTubeClient, clean_display_title, parse_duration


def sample_video(index: int = 1) -> Video:
    return Video(
        video_id=f"video{index:06d}",
        title=f"A Long Song Title Number {index} (Official Video)",
        display_title=f"A Long Song Title Number {index}",
        url=f"https://www.youtube.com/watch?v=video{index:06d}",
        embed_url=f"https://www.youtube.com/embed/video{index:06d}?autoplay=0",
        thumbnail_url="https://i.ytimg.com/vi/example/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=213,
        channel_title="Example Channel",
    )


class FactoryTests(unittest.TestCase):
    def test_slug_and_title_cleaning(self):
        self.assertEqual(slugify("  Piano Black & Brass! "), "piano-black-brass")
        self.assertEqual(clean_display_title("Lost in the Static (Official Music Video)", "Band"), "Lost in the Static")
        self.assertEqual(clean_display_title("GOOD PEOPLE DOING NOTHING - THE BROWN CLOUD", "Good People Doing Nothing"), "THE BROWN CLOUD")
        self.assertEqual(clean_display_title("The Brown Cloud — Good People Doing Nothing", "Good People Doing Nothing"), "The Brown Cloud")
        self.assertEqual(parse_duration("PT3M33S"), 213)

    def test_project_roundtrip_and_site_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ProjectStore(root)
            project = Project(
                slug="example",
                title="Example",
                ticker_text="A short ticker",
                channel_url="https://www.youtube.com/channel/UCexample",
                channel_id="UCexample",
                channel_title="Example Channel",
                channel_thumbnail="",
                videos=[sample_video(1), sample_video(2), sample_video(3)],
            )
            store.save_project(project)
            self.assertEqual(store.load_project("example").videos[1].video_id, "video000002")
            destination = root / "site"
            build_project_site(project, destination)
            payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["videoCount"], 3)
            script = (destination / "assets" / "video-machine.js").read_text(encoding="utf-8")
            self.assertIn("player.src = playerUrl(current)", script)
            self.assertIn("reel-actual-slotmachine-freesound-261346.mp3", script)
            self.assertIn("machine.dataset.videoOpen = 'true'", script)
            self.assertTrue((destination / "assets" / "audio" / "machine" / "reel-stop-lock-mixkit-2857.mp3").is_file())
            self.assertTrue((destination / "qr-card.png").is_file())
            self.assertTrue((destination / "social-card.jpg").is_file())

    def test_catalogue_filters_and_limits(self):
        client = YouTubeClient("test-key")
        channel = {
            "id": "UCexample",
            "snippet": {"title": "Example", "thumbnails": {}},
            "contentDetails": {"relatedPlaylists": {"uploads": "UUexample"}},
        }
        playlist = {"items": [{"contentDetails": {"videoId": f"id{index:03d}"}} for index in range(35)]}
        details = {"items": [
            {
                "id": f"id{index:03d}",
                "status": {"privacyStatus": "public", "embeddable": True},
                "snippet": {"title": f"Video {index}", "channelTitle": "Example", "liveBroadcastContent": "none", "thumbnails": {"high": {"url": "https://example.test/x.jpg", "width": 480, "height": 360}}},
                "contentDetails": {"duration": "PT3M"},
            }
            for index in range(35)
        ]}
        with patch.object(client, "resolve_channel", return_value=channel), patch.object(client, "_get", side_effect=[playlist, details]):
            catalogue = client.fetch_catalogue("https://youtube.com/@example")
        self.assertEqual(len(catalogue.videos), 30)
        self.assertTrue(all("autoplay=0" in item.embed_url for item in catalogue.videos))


if __name__ == "__main__":
    unittest.main()
