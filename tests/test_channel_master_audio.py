from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.models import (
    ChannelMasterConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    Video,
)
from aggits_video_factory.site_builder import build_project_site


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")


def _project(project_type: ProjectType) -> Project:
    video = Video(
        video_id="audiofix001",
        title="Audio Fixture",
        display_title="Audio Fixture",
        channel_title="Fixture Channel",
        url="https://www.youtube.com/watch?v=audiofix001",
        embed_url="https://www.youtube.com/embed/audiofix001",
        thumbnail_url="",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=60,
    )
    return Project(
        slug=f"{project_type.value}-audio-fixture",
        title="AUDIO FIXTURE",
        ticker_text="AUDIO TEST",
        channel_url="https://www.youtube.com/channel/UCAUDIOFIXTURE",
        channel_id="UCAUDIOFIXTURE",
        channel_title="Audio Fixture",
        channel_thumbnail="",
        project_type=project_type,
        videos=[video],
        channel_master_config=(
            ChannelMasterConfig(
                primary_cta=PrimaryCta(PrimaryCtaType.VISIT_WEBSITE, "https://example.com"),
            )
            if project_type is ProjectType.CHANNEL_MASTER
            else None
        ),
    )


class ChannelMasterAudioTests(unittest.TestCase):
    def test_channel_master_has_one_explicit_sound_control_without_home_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build_project_site(_project(ProjectType.CHANNEL_MASTER), output)
            page = (output / "index.html").read_text(encoding="utf-8")
            self.assertEqual(page.count('data-action="sound"'), 1)
            self.assertIn('utility-controls--sound-only', page)
            self.assertIn('data-sound-label>SOUND ON', page)
            self.assertNotIn('data-action="home"', page)
            self.assertIn('.utility-controls--sound-only{justify-content:flex-end}', CSS)

    def test_audio_is_unlocked_during_initial_pointer_or_keyboard_interaction(self):
        self.assertIn("function unlockMachineAudio()", SCRIPT)
        self.assertIn("machine.addEventListener('pointerdown', () => { void unlockMachineAudio(); }, {capture: true});", SCRIPT)
        self.assertIn("if (event.key === 'Enter' || event.key === ' ') void unlockMachineAudio();", SCRIPT)
        self.assertIn("if (machineAudioUnlockPromise) await machineAudioUnlockPromise;", SCRIPT)
        self.assertIn("reelMotorAudio, reelRatchetAudio, reelStopAudio, shutterGearAudio", SCRIPT)

    def test_audio_failures_are_reported_instead_of_silently_discarded(self):
        self.assertIn("function reportAudioFailure(context, error)", SCRIPT)
        self.assertIn("console.warn(`[Crispy Bits audio]", SCRIPT)
        self.assertIn("new CustomEvent('crispy-bits:audio-error'", SCRIPT)
        self.assertIn("reelMotorAudio.play().catch(error => reportAudioFailure('reel motor', error))", SCRIPT)
        self.assertNotIn("audio.play().catch(() => {})", SCRIPT)

    def test_youtube_play_request_retries_when_iframe_loads(self):
        self.assertIn("pendingYouTubePlay = playRequested;", SCRIPT)
        self.assertIn("player.addEventListener('load'", SCRIPT)
        self.assertIn("window.setTimeout(() => {\n          requestPlayerPlay();\n          pendingYouTubePlay = false;", SCRIPT)
        self.assertIn("url.searchParams.set('origin', location.origin)", SCRIPT)

    def test_cancelled_auto_close_change_is_not_present(self):
        self.assertNotIn("closeCompletedYouTubeVideo", SCRIPT)
        self.assertNotIn("onYouTubePlayerMessage", SCRIPT)


if __name__ == "__main__":
    unittest.main()
