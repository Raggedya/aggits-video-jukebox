from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.models import ChannelMasterConfig, PrimaryCta, PrimaryCtaType, Project, ProjectType, Video
from aggits_video_factory.site_builder import build_project_site


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "templates" / "machine.html").read_text(encoding="utf-8")


def _project(destination: str = "https://tickets.example/show") -> Project:
    video = Video(
        video_id="initialcta1",
        title="Opening Act",
        display_title="Opening Act",
        channel_title="Channel",
        url="https://www.youtube.com/watch?v=initialcta1",
        embed_url="https://www.youtube.com/embed/initialcta1",
        thumbnail_url="",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=60,
    )
    return Project(
        slug="initial-controls",
        title="INITIAL CONTROLS",
        ticker_text="TEST",
        channel_url="https://www.youtube.com/channel/UCINITIAL",
        channel_id="UCINITIAL",
        channel_title="Initial Controls",
        channel_thumbnail="",
        project_type=ProjectType.CHANNEL_MASTER,
        videos=[video],
        channel_master_config=ChannelMasterConfig(
            primary_cta=PrimaryCta(PrimaryCtaType.TICKETS, destination),
        ),
    )


class ChannelMasterInitialControlTests(unittest.TestCase):
    def test_get_tickets_payload_is_valid_before_any_discovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build_project_site(_project(), output)
            payload = json.loads((output / "machine.json").read_text(encoding="utf-8"))
            action = payload["customerConfig"]["primaryAction"]
            self.assertTrue(action["enabled"])
            self.assertEqual(action["displayLabel"], "GET TICKETS")
            self.assertEqual(action["destinationURL"], "https://tickets.example/show")

    def test_channel_master_cta_depends_on_destination_not_discovery(self):
        start = SCRIPT.index("function updatePrimaryActionAvailability")
        end = SCRIPT.index("\n  function openPlaqueAction", start)
        availability = SCRIPT[start:end]
        self.assertIn("activeProjectType === 'channel_master'", availability)
        self.assertIn("primaryActionButton.disabled = !primaryActionDestination;", availability)
        self.assertIn("primaryActionButton.disabled = !hasDiscovery || !primaryActionDestination;", availability)
        self.assertIn("updatePrimaryActionAvailability(false);", SCRIPT)
        self.assertIn("updatePrimaryActionAvailability(true);", SCRIPT)

    def test_initial_respin_uses_canonical_spin_and_play_stays_disabled(self):
        self.assertIn("respinButton.addEventListener('click', spin);", SCRIPT)
        self.assertIn("setState('IDLE', 'Pull the lever or press Re-Spin to select a video.');", SCRIPT)
        self.assertIn("respinButton.disabled = false;", SCRIPT)
        self.assertIn('data-action="play" disabled', TEMPLATE)
        self.assertIn("playButton.disabled = false;", SCRIPT)

    def test_primary_cta_cancels_only_pending_intro_before_opening_destination(self):
        start = SCRIPT.index("primaryActionButton.addEventListener('click'")
        end = SCRIPT.index("\n    });", start)
        handler = SCRIPT[start:end]
        self.assertIn("channelMasterIntroState === 'pending'", handler)
        self.assertIn("cancelChannelMasterIntro();", handler)
        self.assertLess(handler.index("cancelChannelMasterIntro();"), handler.index("openPrimaryAction();"))

    def test_missing_destination_remains_safely_unavailable(self):
        self.assertIn("primaryActionButton.disabled = !primaryActionDestination;", SCRIPT)
        self.assertIn("if (!primaryActionDestination) return;", SCRIPT)


if __name__ == "__main__":
    unittest.main()
