from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from aggits_video_factory.love_my_locals import LoveMyLocalsFormValues, assemble_project
from aggits_video_factory.models import LoveMyLocalsCandidate, LoveMyLocalsConfig, Video
from aggits_video_factory.site_builder import build_project_site


ROOT = Path(__file__).resolve().parents[1]


def _candidate() -> LoveMyLocalsCandidate:
    return LoveMyLocalsCandidate(
        video=Video(
            video_id="abcdefghijk",
            title="Bairnsdale local story",
            display_title="Bairnsdale local story",
            url="https://www.youtube.com/watch?v=abcdefghijk",
            embed_url="https://www.youtube-nocookie.com/embed/abcdefghijk",
            thumbnail_url="https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
            published_at="2009-01-01T00:00:00Z",
            duration_seconds=180,
            channel_title="Bairnsdale Community",
            channel_id="channel-one",
        ),
        description="An old Bairnsdale community story.",
        tags=["Bairnsdale", "community"],
        matched_location="Bairnsdale",
        match_basis=["title"],
        relevance_score=3,
        local_texture_score=4,
        content_type="PEOPLE / INTERVIEWS",
        active=True,
    )


def _config() -> LoveMyLocalsConfig:
    return LoveMyLocalsConfig(
        locations=["Bairnsdale"],
        resolved_geography="Victoria, Australia",
        candidates=[_candidate()],
        explore_url="https://www.visitgippsland.com.au/",
    )


def _build(destination: Path):
    config = _config()
    project = assemble_project(
        LoveMyLocalsFormValues(
            locations=["Bairnsdale"],
            ticker_text="BAIRNSDALE • LOCAL PEOPLE • MUSIC • STORIES",
            explore_url=config.explore_url or "",
        ),
        config,
        "bairnsdale",
    )
    build_project_site(project, destination)
    return project


class CoreProductCompatibilityTests(unittest.TestCase):
    def test_legacy_utility_fields_are_ignored_without_crashing(self):
        value = _config().to_dict()
        value.update(
            {
                "utility_data_mode": "live",
                "utility_enabled": {"eat": True, "stay": True},
                "eat_cards": [{"name": "Old fixture venue"}],
                "stay_cards": [{"name": "Old fixture accommodation"}],
                "house_price_snapshot": {"data_as_at": "September 2026"},
                "whats_on_url": "https://example.test/events",
            }
        )
        restored = LoveMyLocalsConfig.from_dict(value)
        self.assertEqual(restored.explore_url, "https://www.visitgippsland.com.au/")
        self.assertFalse(hasattr(restored, "eat_cards"))
        self.assertFalse(hasattr(restored, "utility_data_mode"))
        encoded = json.dumps(restored.to_dict()).casefold()
        for obsolete in ("eat_cards", "stay_cards", "house_price", "whats_on", "utility_data"):
            self.assertNotIn(obsolete, encoded)

    def test_explore_url_round_trips_as_the_only_utility_style_configuration(self):
        restored = LoveMyLocalsConfig.from_dict(_config().to_dict())
        self.assertEqual(restored.explore_url, "https://www.visitgippsland.com.au/")


class CoreProductPublicOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.destination = Path(self.temporary.name)
        _build(self.destination)
        self.page = (self.destination / "index.html").read_text(encoding="utf-8")
        self.machine = json.loads((self.destination / "machine.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.temporary.cleanup()

    def test_public_machine_has_exactly_the_four_primary_controls(self):
        start = self.page.index('<section class="machine-controls"')
        end = self.page.index("</section>", start)
        controls = self.page[start:end]
        self.assertEqual(controls.count("<button "), 4)
        self.assertEqual(controls.count('class="control-button'), 4)
        for label in ("SHARE", "PLAY VIDEO", "EXPLORE", "RE-SPIN"):
            self.assertEqual(controls.count(f">{label}</b>"), 1)

    def test_no_public_local_utility_layer_or_fixture_payload(self):
        combined = (self.page + json.dumps(self.machine)).casefold()
        for obsolete in (
            "data-local-utility",
            "local-utility-chamber",
            "local-utility-navigation",
            "utilitypanel",
            "development-fixture",
            "house prices",
            "what’s on",
        ):
            self.assertNotIn(obsolete, combined)
        self.assertNotIn("love-my-locals-utilities.js", self.page)

    def test_explore_is_the_single_optional_external_local_action(self):
        action = self.machine["customerConfig"]["primaryAction"]
        self.assertEqual(action["type"], "explore")
        self.assertEqual(action["displayLabel"], "EXPLORE")
        self.assertEqual(action["destinationURL"], "https://www.visitgippsland.com.au/")
        self.assertTrue(action["enabled"])
        config = self.machine["loveMyLocalsConfig"]
        self.assertEqual(config["exploreUrl"], action["destinationURL"])
        self.assertEqual(config["brandTeal"], "#00C7CC")

    def test_reel_landing_does_not_replace_explore_with_a_video_cta(self):
        runtime = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
        self.assertNotIn("primaryActionDestination = String(video.ctaURL", runtime)
        self.assertNotIn("primaryActionLabel = String(video.ctaLabel", runtime)

    def test_no_google_places_runtime_or_secret_is_required(self):
        paths = [ROOT / "src", ROOT / "static", ROOT / "worker" / "src", ROOT / "desktop"]
        combined = ""
        for path in paths:
            for file in path.rglob("*"):
                if file.is_file() and file.suffix.lower() in {".py", ".js", ".html", ".ps1"}:
                    combined += file.read_text(encoding="utf-8", errors="ignore")
        for forbidden in (
            "GOOGLE_PLACES_API_KEY",
            "places.googleapis.com",
            "/api/love-my-locals/eat",
            "google-places-new",
        ):
            self.assertNotIn(forbidden, combined)

    def test_desktop_workflow_has_no_utility_data_entry(self):
        source = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")
        self.assertIn("EXPLORE URL", source)
        for obsolete in (
            "EAT CARDS",
            "STAY CARDS",
            "WHAT’S ON URL",
            "HOUSE PRICE SNAPSHOT",
            "UTILITY AVAILABILITY",
        ):
            self.assertNotIn(obsolete, source)

    def test_mechanical_modules_contain_no_abandoned_utility_or_places_code(self):
        for name in ("single-reel-engine.js", "machine-mechanics-core.js"):
            source = (ROOT / "static" / name).read_text(encoding="utf-8").casefold()
            self.assertNotIn("local-utility", source)
            self.assertNotIn("google-places", source)


if __name__ == "__main__":
    unittest.main()
