from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from aggits_video_factory.models import (
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    ProjectValidationError,
    TourismConfig,
    TourismDiscovery,
    Video,
)
from aggits_video_factory.site_builder import build_project_site


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
DESKTOP = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")


def video(index: int) -> Video:
    return Video(
        video_id=f"tourismdeck{index:02d}",
        title=f"Lorne video {index}",
        display_title=f"Lorne video {index}",
        url=f"https://www.youtube.com/watch?v=tourismdeck{index:02d}",
        embed_url=f"https://www.youtube-nocookie.com/embed/tourismdeck{index:02d}",
        thumbnail_url="https://i.ytimg.com/vi/tourismdeck01/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=90,
        channel_title="Lorne Tourism",
        channel_id="UCtourismdeck",
    )


def discovery(identifier: str = "nature-1", image: str = "") -> TourismDiscovery:
    return TourismDiscovery(
        id=identifier,
        location="Lorne, Victoria, Australia",
        category="NATURE",
        hook="DEVELOPMENT SAMPLE",
        headline="SAMPLE NATURE DISCOVERY",
        body="Test content only — replace with operator-verified destination copy before publishing.",
        image=image,
        cta_label="EXPLORE",
        cta_url="https://example.com/official-tourism/nature",
        source_url="https://example.com/source",
    )


def project(discoveries: list[TourismDiscovery]) -> Project:
    return Project(
        slug="love-lorne-tourism-preview",
        title="LOVE LORNE",
        ticker_text="Development preview only.",
        channel_url="https://www.youtube.com/@example",
        channel_id="UCtourismdeck",
        channel_title="Lorne Tourism",
        channel_thumbnail="",
        project_type=ProjectType.TOURISM,
        tourism_config=TourismConfig(
            more_info_url="https://example.com/official-tourism",
            primary_cta=PrimaryCta(PrimaryCtaType.MORE_INFO, "https://example.com/official-tourism"),
            destination_title="LOVE LORNE",
            location="Lorne, Victoria, Australia",
            official_tourism_url="https://example.com/official-tourism",
            discoveries=discoveries,
        ),
        videos=[video(1), video(2), video(3)],
    )


class TourismDiscoveryDeckTests(unittest.TestCase):
    def test_discovery_schema_round_trip_and_validation(self):
        item = discovery()
        self.assertEqual(TourismDiscovery.from_dict(item.to_dict()).to_dict(), item.to_dict())
        with self.assertRaises(ProjectValidationError):
            TourismDiscovery.from_dict({**item.to_dict(), "ctaUrl": "javascript:alert(1)"})
        with self.assertRaises(ProjectValidationError):
            TourismConfig(discoveries=[discovery("duplicate"), discovery("duplicate")])

    def test_tourism_project_round_trip_preserves_discoveries(self):
        restored = Project.from_dict(project([discovery()]).to_dict())
        self.assertEqual(restored.tourism_config.destination_title, "LOVE LORNE")
        self.assertEqual(restored.tourism_config.location, "Lorne, Victoria, Australia")
        self.assertEqual(len(restored.tourism_config.discoveries), 1)
        self.assertEqual(restored.tourism_config.discoveries[0].headline, "SAMPLE NATURE DISCOVERY")

    def test_site_build_emits_one_typed_mixed_deck_and_packages_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "destination.jpg"
            Image.new("RGB", (900, 600), "#173149").save(image)
            output = root / "site"
            build_project_site(project([discovery(image=str(image))]), output)
            payload = json.loads((output / "machine.json").read_text(encoding="utf-8"))
            deck = payload["contentDeck"]
            self.assertEqual([item["contentType"] for item in deck], ["video", "video", "video", "discovery"])
            card = payload["tourismConfig"]["discoveries"][0]
            self.assertEqual(card["type"], "discovery")
            self.assertEqual(card["ctaLabel"], "EXPLORE")
            self.assertTrue((output / card["image"]).is_file())

    def test_disabled_cards_are_persisted_but_not_published(self):
        item = discovery()
        item.enabled = False
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build_project_site(project([item]), output)
            payload = json.loads((output / "machine.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["tourismConfig"]["discoveries"], [])
            self.assertEqual(len(payload["contentDeck"]), 3)

    def test_legacy_tourism_output_remains_video_only(self):
        legacy = project([])
        legacy.tourism_config = TourismConfig(
            more_info_url="https://example.com/info",
            stay_url="https://example.com/stay",
            destination_title="Legacy title restored by the editor",
            location="Legacy location restored by the editor",
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build_project_site(legacy, output)
            payload = json.loads((output / "machine.json").read_text(encoding="utf-8"))
            self.assertNotIn("contentDeck", payload)
            self.assertNotIn("mixedDiscoveryEnabled", payload["tourismConfig"])

    def test_public_runtime_has_tourism_only_selection_and_poster_behaviour(self):
        self.assertIn("Math.random() < .25", SCRIPT)
        self.assertIn("current?.contentType !== 'discovery'", SCRIPT)
        self.assertIn("tourismDiscoveryBag", SCRIPT)
        self.assertIn("tourism_discovery_selected", SCRIPT)
        self.assertIn("tourism_discovery_cta_click", SCRIPT)
        self.assertIn("tourism_official_site_click", SCRIPT)
        self.assertIn("tourism-discovery-poster", STYLE)
        self.assertIn("activeProjectType === 'tourism' && tourismMixedMode", SCRIPT)
        self.assertIn("isSponsor || isTourismDiscovery ? null : video", SCRIPT)

    def test_desktop_exposes_manual_editor_without_research_or_places_api(self):
        for copy in (
            "LOCAL DISCOVERY DECK", "MANAGE DISCOVERIES", "SAVE CARD", "DELETE",
            "MOVE UP", "MOVE DOWN", "PREVIEW", "IMPORT JSON", "SELECT",
        ):
            self.assertIn(copy, DESKTOP)
        self.assertNotIn("GENERATE LOCAL DISCOVERIES", DESKTOP)
        self.assertNotIn("Google Places", DESKTOP)


if __name__ == "__main__":
    unittest.main()
