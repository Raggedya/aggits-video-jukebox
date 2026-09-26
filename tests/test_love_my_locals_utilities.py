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
from aggits_video_factory.config import LOVE_MY_LOCALS_EAT_ENDPOINT
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
        utility_data_mode="development-fixture",
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

    def test_live_is_the_safe_default_and_development_fixture_must_be_explicit(self):
        live = LoveMyLocalsConfig(locations=["Bairnsdale"], candidates=[_candidate()])
        self.assertEqual(live.utility_data_mode, "live")
        self.assertEqual(LoveMyLocalsConfig.from_dict(live.to_dict()).utility_data_mode, "live")
        development = LoveMyLocalsConfig(
            locations=["Bairnsdale"], candidates=[_candidate()], utility_data_mode="development-fixture",
        )
        self.assertEqual(LoveMyLocalsConfig.from_dict(development.to_dict()).utility_data_mode, "development-fixture")
        with self.assertRaises(ValueError):
            LoveMyLocalsConfig(locations=["Bairnsdale"], candidates=[_candidate()], utility_data_mode="fixture-if-live-fails")


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


class LoveMyLocalsLiveEatOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.destination = Path(self.temporary.name)
        config = LoveMyLocalsConfig(
            locations=["Bairnsdale"], resolved_geography="Victoria, Australia",
            candidates=[_candidate()],
        )
        project = assemble_project(
            LoveMyLocalsFormValues(locations=["Bairnsdale"], explore_url="https://www.visitgippsland.com.au/"),
            config, "bairnsdale",
        )
        build_project_site(project, self.destination)
        self.page = (self.destination / "index.html").read_text(encoding="utf-8")
        self.machine = json.loads((self.destination / "machine.json").read_text(encoding="utf-8"))
        self.service = (ROOT / "static" / "love-my-locals-utilities.js").read_text(encoding="utf-8")
        self.runtime = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_production_payload_uses_live_eat_and_only_other_utilities_retain_fixtures(self):
        panel = self.machine["loveMyLocalsConfig"]["utilityPanel"]
        self.assertEqual(panel["provider"], "google-places-new")
        self.assertTrue(panel["liveDataConnected"])
        self.assertEqual(panel["environment"], "production")
        self.assertEqual(panel["eat"], {
            "provider": "google-places-new",
            "mode": "live",
            "endpoint": LOVE_MY_LOCALS_EAT_ENDPOINT,
            "projectSlug": "bairnsdale",
            "attribution": "Google Maps",
            "photosEnabled": False,
            "cacheStrategy": "page-session-only",
        })
        self.assertNotIn("eat", panel["data"])
        self.assertEqual(set(panel["data"]), {"stay", "whats-on", "house-prices"})
        self.assertTrue(all(value["source"] == "development-fixture" for value in panel["data"].values()))

    def test_live_adapter_has_timeout_session_cache_and_no_fixture_fallback(self):
        self.assertIn("export class LiveEatProvider", self.service)
        self.assertIn("cache: 'no-store'", self.service)
        self.assertIn("AbortController", self.service)
        self.assertIn("this.cached && Date.now() < this.cacheUntil", self.service)
        service_start = self.service.index("export class LoveMyLocalsUtilityService")
        eat_start = self.service.index("getEatData() {", service_start)
        eat_method = self.service[eat_start:self.service.index("getStayData()", eat_start)]
        self.assertIn("this.liveEatProvider.getEatData()", eat_method)
        self.assertIn("this.eatMode === 'development-fixture'", eat_method)
        self.assertIn("Promise.reject", eat_method)
        self.assertNotIn("catch", eat_method)

    def test_unavailable_state_is_inside_chamber_and_back_to_video_remains_the_exit(self):
        self.assertIn("LOCAL EATING INFORMATION IS TEMPORARILY UNAVAILABLE.", self.runtime)
        self.assertIn("renderLocalUtilityUnavailable(type)", self.runtime)
        self.assertIn("data-local-utility-back", self.page)
        self.assertNotIn("VIEW DETAILS", self.page)
        self.assertNotIn("BOOK NOW", self.page)
        self.assertNotIn("MENU", self.page)
        chamber = self.page[self.page.index('class="local-utility-chamber"'):self.page.index("</section>", self.page.index('class="local-utility-chamber"'))]
        self.assertNotIn("<a ", chamber)

    def test_google_attribution_is_plain_visible_chamber_text_and_photos_are_deliberately_disabled(self):
        self.assertIn('data-local-utility-attribution translate="no" hidden', self.page)
        self.assertNotIn('data-local-utility-attribution href=', self.page)
        panel = self.machine["loveMyLocalsConfig"]["utilityPanel"]
        self.assertFalse(panel["eat"]["photosEnabled"])
        css = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
        self.assertIn(".local-utility-attribution", css)
        self.assertIn("font:400 12px", css)
        self.assertIn(".local-utility-pagination[hidden]{display:none!important}", css)

    def test_explore_youtube_discovery_and_mechanics_remain_separate(self):
        self.assertEqual(self.machine["customerConfig"]["primaryAction"]["destinationURL"], "https://www.visitgippsland.com.au/")
        discovery = (ROOT / "src" / "aggits_video_factory" / "love_my_locals.py").read_text(encoding="utf-8")
        self.assertIn("def real_estate_exclusion_reason", discovery)
        self.assertNotIn("google-places-new", discovery)
        for name in ("single-reel-engine.js", "machine-mechanics-core.js"):
            self.assertNotIn("google-places", (ROOT / "static" / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
