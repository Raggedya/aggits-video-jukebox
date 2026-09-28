from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.business_workflow import assemble_reviewed_project
from aggits_video_factory.channel_master_intro import (
    ChannelMasterIntroError,
    inspect_intro_mp4,
    materialize_intro_mp4,
)
from aggits_video_factory.config import MAX_CHANNEL_MASTER_INTRO_MP4_BYTES
from aggits_video_factory.desktop_forms import ProjectFormValues, project_to_form_values, validate_project_form
from aggits_video_factory.models import ChannelMasterConfig, PrimaryCta, PrimaryCtaType, Project, ProjectType, Video
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.youtube_api import ChannelCatalogue


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
DESKTOP = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")


def _atom(kind: bytes, payload: bytes = b"") -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + kind + payload


def _make_mp4(path: Path, payload: bytes = b"video") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        _atom(b"ftyp", b"isom\x00\x00\x02\x00isommp42")
        + _atom(b"moov")
        + _atom(b"mdat", payload)
    )


def _video(index: int = 1) -> Video:
    video_id = f"intro{index:06d}"[:11]
    return Video(
        video_id=video_id,
        title=f"Video {index}",
        display_title=f"Video {index}",
        channel_title="Channel",
        url=f"https://www.youtube.com/watch?v={video_id}",
        embed_url=f"https://www.youtube.com/embed/{video_id}",
        thumbnail_url="",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=60,
    )


def _project(reference: str = "", *, count: int = 1) -> Project:
    return Project(
        slug="intro-fixture",
        title="INTRO FIXTURE",
        ticker_text="INTRO TEST",
        channel_url="https://www.youtube.com/channel/UCINTRO",
        channel_id="UCINTRO",
        channel_title="Intro Channel",
        channel_thumbnail="",
        project_type=ProjectType.CHANNEL_MASTER,
        videos=[_video(index) for index in range(1, count + 1)],
        channel_master_config=ChannelMasterConfig(
            primary_cta=PrimaryCta(PrimaryCtaType.VISIT_WEBSITE, "https://example.com"),
            intro_mp4=reference,
        ),
    )


class ChannelMasterIntroAssetTests(unittest.TestCase):
    def test_operator_requested_limit_is_twenty_four_megabytes(self):
        self.assertEqual(MAX_CHANNEL_MASTER_INTRO_MP4_BYTES, 24 * 1024 * 1024)

    def test_valid_mp4_is_inspected_hashed_and_project_controlled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "operator" / "opening.mp4"
            _make_mp4(source)
            info = inspect_intro_mp4(source)
            reference = materialize_intro_mp4(str(source), root / "project")
            controlled = root / "project" / reference
            self.assertEqual(info.file_size, controlled.stat().st_size)
            self.assertRegex(reference, r"^assets/channel-master-intro-[0-9a-f]{16}\.mp4$")
            source.unlink()
            self.assertEqual(inspect_intro_mp4(controlled).file_size, info.file_size)

    def test_invalid_extension_fake_mp4_and_oversize_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrong = root / "opening.mov"
            _make_mp4(wrong)
            with self.assertRaisesRegex(ChannelMasterIntroError, "MUST BE AN MP4"):
                inspect_intro_mp4(wrong)
            fake = root / "fake.mp4"
            fake.write_text("not a video", encoding="utf-8")
            with self.assertRaisesRegex(ChannelMasterIntroError, "COULD NOT BE READ"):
                inspect_intro_mp4(fake)
            oversized = root / "large.mp4"
            with oversized.open("wb") as target:
                target.seek(MAX_CHANNEL_MASTER_INTRO_MP4_BYTES)
                target.write(b"x")
            with self.assertRaisesRegex(ChannelMasterIntroError, "MAXIMUM FILE SIZE"):
                inspect_intro_mp4(oversized)

    def test_replace_changes_only_asset_reference_and_remove_clears_intro_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir = root / "project"
            first = root / "first.mp4"
            second = root / "second.mp4"
            _make_mp4(first, b"first")
            _make_mp4(second, b"second")
            first_reference = materialize_intro_mp4(str(first), project_dir)
            second_reference = materialize_intro_mp4(str(second), project_dir)
            self.assertNotEqual(first_reference, second_reference)
            self.assertFalse((project_dir / first_reference).exists())
            self.assertTrue((project_dir / second_reference).exists())
            self.assertEqual(materialize_intro_mp4("", project_dir), "")
            self.assertFalse(list((project_dir / "assets").glob("channel-master-intro-*.mp4")))


class ChannelMasterIntroPersistenceTests(unittest.TestCase):
    def test_old_config_defaults_to_no_intro_and_round_trip_preserves_reference(self):
        self.assertEqual(ChannelMasterConfig.from_dict({"palette": "MIDNIGHT"}).intro_mp4, "")
        config = ChannelMasterConfig.from_dict({"intro_mp4": "assets/channel-master-intro-a.mp4"})
        self.assertEqual(config.to_dict()["intro_mp4"], "assets/channel-master-intro-a.mp4")

    def test_store_save_close_reopen_and_form_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            project = _project("assets/channel-master-intro-a.mp4")
            store.save_project(project)
            restored = ProjectStore(Path(temporary)).load_project(project.slug)
            self.assertEqual(restored.channel_master_config.intro_mp4, project.channel_master_config.intro_mp4)
            self.assertEqual(project_to_form_values(restored).intro_mp4, project.channel_master_config.intro_mp4)

    def test_fifty_youtube_videos_plus_intro_is_valid(self):
        project = _project("assets/channel-master-intro-a.mp4", count=50)
        self.assertEqual(len(project.videos), 50)
        self.assertTrue(project.channel_master_config.intro_mp4)

    def test_published_intro_edit_is_changes_pending_without_identity_change(self):
        existing = _project()
        existing.status = "published"
        existing.published_url = "https://example.com/crispy-bits/intro-fixture/"
        identity = (existing.id, existing.slug, existing.published_url)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "intro.mp4"
            _make_mp4(source)
            values = validate_project_form(ProjectFormValues(
                title=existing.title,
                manual_video_urls=[existing.videos[0].url],
                story_text=existing.ticker_text,
                cta_label="Visit Website",
                destination_url="https://example.com",
                intro_mp4=str(source),
            ), ProjectType.CHANNEL_MASTER)
            revised = assemble_reviewed_project(
                project_type=ProjectType.CHANNEL_MASTER,
                values=values,
                catalogue=ChannelCatalogue("", "", "", "", [existing.videos[0]]),
                selected_videos=[existing.videos[0]],
                reviewed_videos=[existing.videos[0]],
                source_results=[], slug=existing.slug, existing=existing,
            )
        self.assertEqual(revised.status, "changes_pending")
        self.assertEqual((revised.id, revised.slug, revised.published_url), identity)


class ChannelMasterIntroPublishingTests(unittest.TestCase):
    def test_build_packages_public_mp4_payload_and_same_chamber_markup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "private" / "opening.mp4"
            _make_mp4(source)
            project_dir = root / "project"
            reference = materialize_intro_mp4(str(source), project_dir)
            project = _project(reference)
            build_project_site(project, project_dir / "site")
            payload = json.loads((project_dir / "site" / "machine.json").read_text(encoding="utf-8"))
            intro = payload["channelMasterConfig"]["introMP4"]
            self.assertTrue(intro["enabled"])
            self.assertEqual(intro["promptDelayMilliseconds"], 1250)
            self.assertTrue((project_dir / "site" / intro["assetURL"]).is_file())
            page = (project_dir / "site" / "index.html").read_text(encoding="utf-8")
            self.assertIn("data-channel-master-intro-player", page)
            self.assertNotIn("data-channel-master-intro-player autoplay", page)
            self.assertNotIn(str(source.parent), page + json.dumps(payload))

    def test_no_intro_has_no_timer_asset_markup_or_layout_difference(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build_project_site(_project(), output)
            payload = json.loads((output / "machine.json").read_text(encoding="utf-8"))
            page = (output / "index.html").read_text(encoding="utf-8")
            self.assertFalse(payload["channelMasterConfig"]["introMP4"]["enabled"])
            self.assertNotIn("data-channel-master-intro-player", page)

    def test_runtime_is_channel_master_only_user_first_and_non_autoplay(self):
        for required in (
            "activeProjectType !== 'channel_master'", "promptDelayMilliseconds", "Math.max(1000, Math.min(1500",
            "cancelChannelMasterIntro();", "channelMasterIntroPlayer.play()", "channelMasterIntroPlayer?.addEventListener('ended'",
            "channelMasterIntroDismiss?.addEventListener('click'", "machine.dataset.introOpen = 'true'",
            "playSample(shutterGearAudio, {volume: .62, rate: .9})",
        ):
            self.assertIn(required, SCRIPT)
        self.assertIn("preload=\"metadata\" controls playsinline hidden", (ROOT / "src" / "aggits_video_factory" / "site_builder.py").read_text(encoding="utf-8"))
        self.assertNotIn("channelMasterIntroPlayer.autoplay", SCRIPT)
        self.assertIn("[data-intro-open=\"true\"]", CSS)

    def test_desktop_has_channel_master_only_select_remove_and_helper(self):
        self.assertIn('text="Intro MP4"', DESKTOP)
        self.assertIn('text="SELECT MP4"', DESKTOP)
        self.assertIn('text="REMOVE"', DESKTOP)
        self.assertIn("OPTIONAL OPENING VIDEO — VIEWER IS PROMPTED TO PLAY", DESKTOP)
        self.assertIn('self.field_widgets["intro_mp4"]', DESKTOP)


if __name__ == "__main__":
    unittest.main()
