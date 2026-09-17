from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aggits_video_factory.models import Project, Video
from aggits_video_factory.publisher import _library_path, _valid_public_machine_path
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore, slugify
from aggits_video_factory.youtube_api import YouTubeClient, clean_display_title, merge_video_selections, parse_duration


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
        channel_id="UCexample",
    )


class FactoryTests(unittest.TestCase):
    def test_crispy_bits_publish_namespace_is_isolated(self):
        workspace = Path("C:/temporary/workspace")
        public_root = workspace / "public" / "crispy-bits"
        self.assertEqual(_library_path(workspace), public_root / "library.json")
        self.assertEqual(_valid_public_machine_path(public_root, "Example Machine"), public_root / "example-machine")

    def test_slug_and_title_cleaning(self):
        self.assertEqual(slugify("  Piano Black & Brass! "), "piano-black-brass")
        self.assertEqual(clean_display_title("Lost in the Static (Official Music Video)", "Band"), "Lost in the Static")
        self.assertEqual(clean_display_title("GOOD PEOPLE DOING NOTHING - THE BROWN CLOUD", "Good People Doing Nothing"), "THE BROWN CLOUD")
        self.assertEqual(clean_display_title("The Brown Cloud — Good People Doing Nothing", "Good People Doing Nothing"), "The Brown Cloud")
        self.assertEqual(parse_duration("PT3M33S"), 213)
        self.assertEqual(YouTubeClient.video_id_from_url("https://youtu.be/dQw4w9WgXcQ?t=5"), "dQw4w9WgXcQ")
        self.assertEqual(YouTubeClient.video_id_from_url("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(YouTubeClient.video_id_from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(YouTubeClient.video_id_from_url("https://example.com/watch?v=dQw4w9WgXcQ"), "")

    def test_manual_videos_take_priority_and_duplicates_are_removed(self):
        manual = [sample_video(2), sample_video(1)]
        channel = [sample_video(1), sample_video(3), sample_video(4)]
        selected = merge_video_selections(manual, channel, 3)
        self.assertEqual([video.video_id for video in selected], ["video000002", "video000001", "video000003"])

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
                source_channel_url="https://youtube.com/@example",
                manual_video_urls=["https://youtu.be/video000001"],
                excluded_video_ids=["video000099"],
                videos=[sample_video(1), sample_video(2), sample_video(3)],
            )
            store.save_project(project)
            restored = store.load_project("example")
            self.assertEqual(restored.videos[1].video_id, "video000002")
            self.assertEqual(restored.source_channel_url, "https://youtube.com/@example")
            self.assertEqual(restored.manual_video_urls, ["https://youtu.be/video000001"])
            self.assertEqual(restored.excluded_video_ids, ["video000099"])
            destination = root / "site"
            build_project_site(project, destination)
            payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["videoCount"], 3)
            self.assertEqual(payload["schemaVersion"], 2)
            self.assertEqual(payload["customerConfig"]["customerName"], "Example")
            self.assertEqual(payload["customerConfig"]["customerStory"], "A short ticker")
            self.assertEqual(payload["customerConfig"]["customerTagline"], "MORE STORIES • MORE TO DISCOVER")
            self.assertEqual(payload["videos"][0]["shortTitle"], "A Long Song Title Number 1")
            self.assertIn("Press Play Video", payload["videos"][0]["storyText"])
            script = (destination / "assets" / "video-machine.js").read_text(encoding="utf-8")
            self.assertIn("player.src = playerUrl(current)", script)
            self.assertIn("reel-actual-slotmachine-freesound-261346.mp3", script)
            self.assertIn("machine.dataset.videoOpen = 'true'", script)
            self.assertIn("await closeVideo()", script)
            self.assertIn("sub_confirmation=1", script)
            self.assertIn("function startStoryTicker()", script)
            self.assertIn("storyTrack.style.setProperty('--story-start', `${start}px`)", script)
            self.assertIn("storyTrack.style.setProperty('--story-end', `${end}px`)", script)
            self.assertIn("function updateStory(video = null)", script)
            self.assertIn("sessionStorage.setItem('crispyBitsSound'", script)
            self.assertIn("function fiveAround(winner)", script)
            self.assertIn("scheduleVideoReveal(winner)", script)
            self.assertIn("machine.dataset.revealedVideoId = openingVideoId", script)
            video_css = (destination / "assets" / "video-machine.css").read_text(encoding="utf-8")
            self.assertIn("grid-template-columns:repeat(5,minmax(0,1fr))", video_css)
            self.assertIn('@keyframes storyCrawl', video_css)
            self.assertIn('.story-window{', video_css)
            self.assertIn('[data-machine-state="READY_TO_PLAY"] .reel-card:nth-child(3)', video_css)
            self.assertIn('animation:crispyReelFocus .38s cubic-bezier(.2,.72,.22,1) .7s both', video_css)
            self.assertIn('@keyframes crispyReelFocus', video_css)
            self.assertIn('.music-machine[data-video-open="true"] .video-stage', video_css)
            page = (destination / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("VIDEO MUSIC MACHINE", page)
            self.assertIn("SUBSCRIBE", page)
            self.assertNotIn("OPEN<br>YOUTUBE", page)
            self.assertIn("crispy-bits-logo-cutout-v2.png", page)
            self.assertIn("data-content-description", page)
            self.assertIn("data-view-youtube", page)
            self.assertIn("data-story-window", page)
            self.assertIn("THE STORY SO FAR", page)
            self.assertEqual(page.count('class="reel-card"'), 5)
            self.assertIn("CRISPY BITS", page)
            self.assertTrue((destination / "assets" / "music-machine" / "aggits-cabinet-emerald-v1.png").is_file())
            self.assertTrue((destination / "assets" / "music-machine" / "crispy-bits-logo-cutout-v2.png").is_file())
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

    def test_individual_video_catalogue(self):
        client = YouTubeClient("test-key")
        details = {"items": [{
            "id": "dQw4w9WgXcQ",
            "status": {"privacyStatus": "public", "embeddable": True},
            "snippet": {"title": "Example Clip", "channelTitle": "Example Channel", "channelId": "UCexample", "liveBroadcastContent": "none", "thumbnails": {}},
            "contentDetails": {"duration": "PT4M"},
        }]}
        with patch.object(client, "_get", return_value=details):
            catalogue = client.fetch_videos(["https://youtu.be/dQw4w9WgXcQ"])
        self.assertEqual(catalogue.channel_title, "Example Channel")
        self.assertEqual(catalogue.channel_url, "https://www.youtube.com/channel/UCexample")
        self.assertEqual(catalogue.videos[0].video_id, "dQw4w9WgXcQ")


if __name__ == "__main__":
    unittest.main()
