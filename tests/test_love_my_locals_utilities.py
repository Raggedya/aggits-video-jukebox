from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from aggits_video_factory.love_my_locals import LoveMyLocalsError, LoveMyLocalsFormValues, assemble_project, validate_form
from aggits_video_factory.love_my_locals_utilities import (
    UTILITY_FIXTURE_NOTICE,
    UTILITY_TYPES,
    build_development_utility_fixtures,
    fixture_provider_metadata,
)
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
            published_at="2020-01-01T00:00:00Z",
            duration_seconds=180,
            channel_title="Bairnsdale Community",
            channel_id="channel-one",
        ),
        description="A Bairnsdale community story.",
        tags=["Bairnsdale"],
        matched_location="Bairnsdale",
        match_basis=["title"],
        relevance_score=3,
        active=True,
    )


def _build_fixture_site(destination: Path):
    config = LoveMyLocalsConfig(
        locations=["Bairnsdale"],
        resolved_geography="Victoria, Australia",
        candidates=[_candidate()],
    )
    project = assemble_project(
        LoveMyLocalsFormValues(
            locations=["Bairnsdale"],
            explore_url="https://www.visitgippsland.com.au/",
        ),
        config,
        "bairnsdale",
    )
    build_project_site(project, destination)
    return project


class LoveMyLocalsUtilityFixtureTests(unittest.TestCase):
    def test_all_four_fixture_providers_are_normalised_and_unmistakably_non_production(self):
        data = build_development_utility_fixtures(["Bairnsdale"], "Victoria, Australia")
        self.assertEqual(tuple(data), UTILITY_TYPES)
        for utility_type, utility in data.items():
            with self.subTest(utility_type=utility_type):
                self.assertEqual(utility["utilityType"], utility_type)
                self.assertEqual(utility["source"], "development-fixture")
                self.assertEqual(utility["environment"], "development")
                self.assertEqual(utility["notice"], UTILITY_FIXTURE_NOTICE)
                self.assertIn("NOT LIVE DATA", utility["generatedAt"])
                self.assertEqual(len(utility["items"]), 9)
                self.assertTrue(all(item["fixture"] for item in utility["items"]))
                self.assertTrue(all("TEST" in item["name"] for item in utility["items"]))
                self.assertTrue(all("url" not in key.casefold() for item in utility["items"] for key in item))
        self.assertEqual(data["house-prices"]["market"], {
            "medianHousePrice": "TEST DATA",
            "medianUnitPrice": "TEST DATA",
            "twelveMonthMovement": "TEST DATA",
        })

    def test_provider_contract_caps_nine_cards_and_three_cards_per_page(self):
        metadata = fixture_provider_metadata()
        self.assertEqual(metadata["maxItemsPerUtility"], 9)
        self.assertEqual(metadata["itemsPerPage"], 3)
        self.assertFalse(metadata["liveDataConnected"])
        service = (ROOT / "static" / "love-my-locals-utilities.js").read_text(encoding="utf-8")
        for method in ("getEatData", "getStayData", "getWhatsOnData", "getHousePriceData"):
            self.assertIn(method, service)
        self.assertIn("sourceItems.slice(0, MAX_ITEMS)", service)
        self.assertNotIn("fetch(", service)

    def test_explore_url_and_default_enabled_utilities_round_trip(self):
        config = LoveMyLocalsConfig(
            locations=["Bairnsdale"], candidates=[_candidate()],
            explore_url="https://www.visitgippsland.com.au/",
        )
        restored = LoveMyLocalsConfig.from_dict(config.to_dict())
        self.assertEqual(restored.explore_url, "https://www.visitgippsland.com.au/")
        self.assertEqual(restored.utility_enabled, {utility_type: True for utility_type in UTILITY_TYPES})
        with self.assertRaises(LoveMyLocalsError):
            validate_form(LoveMyLocalsFormValues(["Bairnsdale"], explore_url="javascript:alert(1)"))


class LoveMyLocalsUtilityOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.destination = Path(self.temporary.name)
        self.project = _build_fixture_site(self.destination)
        self.page = (self.destination / "index.html").read_text(encoding="utf-8")
        self.machine = json.loads((self.destination / "machine.json").read_text(encoding="utf-8"))
        self.css = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
        self.runtime = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_secondary_row_has_exactly_four_even_accessible_buttons_and_no_around_here(self):
        self.assertEqual(self.page.count("data-local-utility=\""), 4)
        for utility_type in UTILITY_TYPES:
            self.assertIn(f'data-local-utility="{utility_type}"', self.page)
        self.assertNotIn("AROUND HERE", self.page)
        self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))", self.css)
        self.assertIn("aria-pressed=\"false\"", self.page)
        self.assertIn("button:focus-visible", self.css)

    def test_chamber_is_inside_existing_video_frame_and_all_cards_are_information_only(self):
        frame_start = self.page.index('<div class="video-stage-frame">')
        frame_end = self.page.index('</div>\n      </section>', frame_start)
        chamber = self.page[frame_start:frame_end]
        self.assertIn("data-youtube-player", chamber)
        self.assertIn("data-local-utility-chamber", chamber)
        self.assertIn("← BACK TO VIDEO", chamber)
        self.assertNotIn("<a ", chamber)
        utility_json = json.dumps(self.machine["loveMyLocalsConfig"]["utilityPanel"])
        for forbidden in (
            "VIEW DETAILS", "CHECK AVAILABILITY", "BOOK NOW", "BUY TICKETS",
            "VIEW PROPERTY", "CONTACT AGENT", "MORE PLACES",
        ):
            self.assertNotIn(forbidden, utility_json.upper())
        self.assertNotIn('"url"', utility_json.casefold())

    def test_explore_is_the_only_configured_external_local_information_action(self):
        action = self.machine["customerConfig"]["primaryAction"]
        self.assertEqual(action, {
            "type": "explore",
            "displayLabel": "EXPLORE",
            "destinationURL": "https://www.visitgippsland.com.au/",
            "enabled": True,
        })
        self.assertEqual(self.machine["loveMyLocalsConfig"]["exploreUrl"], action["destinationURL"])
        self.assertIn("EXPLORE TOURISM URL", (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8"))

    def test_all_utilities_use_teal_active_state_three_page_pagination_and_fixed_frame(self):
        panel = self.machine["loveMyLocalsConfig"]["utilityPanel"]
        self.assertEqual(panel["itemsPerPage"], 3)
        self.assertEqual(panel["maxItemsPerUtility"], 9)
        self.assertEqual(set(panel["data"]), set(UTILITY_TYPES))
        self.assertTrue(all(len(value["items"]) == 9 for value in panel["data"].values()))
        self.assertIn("button.is-active", self.css)
        self.assertIn("#00c7cc", self.css.casefold())
        self.assertIn(".video-stage-frame{position:relative;width:100%;aspect-ratio:16/9", self.css)
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr))", self.css)

    def test_back_to_video_preserves_selected_video_reel_and_description_state(self):
        open_start = self.runtime.index("async function openLocalUtility")
        close_start = self.runtime.index("function closeLocalUtility", open_start)
        close_end = self.runtime.index("function showBanjoChoiceAward", close_start)
        open_source = self.runtime[open_start:close_start]
        close_source = self.runtime[close_start:close_end]
        self.assertIn("localUtilityRestore", open_source)
        self.assertIn("winnerTitle.textContent = localUtilityRestore.title", close_source)
        self.assertIn("contentMeta.textContent = localUtilityRestore.meta", close_source)
        self.assertIn("contentDescription.textContent = localUtilityRestore.description", close_source)
        self.assertNotIn("spinSingleReel", open_source + close_source)
        self.assertNotIn("current =", open_source + close_source)
        self.assertNotIn("location.reload", open_source + close_source)
        self.assertIn("machine.dataset.videoOpen !== 'true'", open_source)

    def test_mobile_and_desktop_rules_remain_scoped_without_machine_level_overflow(self):
        self.assertIn('@media (max-width:560px)', self.css)
        self.assertIn('.music-machine[data-project-type="love_my_locals"] .local-utility-chamber', self.css)
        self.assertIn("overflow:hidden", self.css)
        self.assertIn("body{overflow-x:hidden", self.css)
        self.assertNotIn("width:100vw", self.css)

    def test_fixture_payload_has_no_live_provider_claim_and_video_real_estate_filter_is_untouched(self):
        panel = self.machine["loveMyLocalsConfig"]["utilityPanel"]
        self.assertEqual(panel["provider"], "development-fixture")
        self.assertFalse(panel["liveDataConnected"])
        discovery = (ROOT / "src" / "aggits_video_factory" / "love_my_locals.py").read_text(encoding="utf-8")
        self.assertIn("def real_estate_exclusion_reason", discovery)
        self.assertIn("DIRECT_PROPERTY_LISTING_PATTERN", discovery)

    def test_mechanical_modules_remain_free_of_utility_implementation(self):
        for name in ("single-reel-engine.js", "machine-mechanics-core.js"):
            source = (ROOT / "static" / name).read_text(encoding="utf-8")
            self.assertNotIn("local-utility", source)
            self.assertNotIn("house-prices", source)


if __name__ == "__main__":
    unittest.main()
