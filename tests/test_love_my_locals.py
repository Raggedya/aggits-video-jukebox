from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from aggits_video_factory.config import resource_path, ticker_limit_for_project_type, video_limit_for_project_type
from aggits_video_factory.desktop_forms import CTA_CHOICES_BY_PROJECT
from aggits_video_factory.delivery import request_delivery
from aggits_video_factory.love_my_locals import (
    LoveMyLocalsDiscoveryService,
    LoveMyLocalsError,
    LoveMyLocalsFormValues,
    assemble_project,
    default_ticker,
    discovery_queries_for_location,
    discovery_quality_report,
    council_meeting_suppression_reason,
    local_texture_analysis,
    qualify_metadata,
    real_estate_exclusion_reason,
    remove_candidate,
    replace_candidate,
    resolved_locations,
    tourism_suppression_flags,
    validate_form,
)
from aggits_video_factory.models import LoveMyLocalsConfig, PrimaryCtaType, Project, ProjectType
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.youtube_api import YouTubeError


ROOT = Path(__file__).parents[1]


def item(number: int, *, title: str = "Box Hill local story", description: str = "", tags=None,
         duration: str = "PT2M", privacy: str = "public", embeddable: bool = True,
         channel: str | None = None, channel_id: str | None = None,
         published: str = "2026-01-01T00:00:00Z") -> dict:
    video_id = f"local{number:06d}"[:11]
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": description,
            "tags": list(tags or []),
            "channelTitle": channel or f"Local Channel {number % 20}",
            "channelId": channel_id or f"channel-{number % 20}",
            "publishedAt": published,
            "liveBroadcastContent": "none",
            "thumbnails": {"high": {"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", "width": 480, "height": 360}},
        },
        "contentDetails": {"duration": duration},
        "status": {"privacyStatus": privacy, "embeddable": embeddable},
    }


class FakeClient:
    def __init__(self, results: list[dict] | None = None, error: Exception | None = None) -> None:
        self.results = list(results or [])
        self.error = error
        self.queries: list[tuple[str, int]] = []
        from aggits_video_factory.youtube_api import YouTubeClient
        self._record = YouTubeClient("test-key")._video_record

    def search_video_items(self, query: str, maximum: int = 75) -> list[dict]:
        self.queries.append((query, maximum))
        if self.error:
            raise self.error
        return list(self.results)

    def _video_record(self, value: dict):
        return self._record(value)


def discovered(count: int = 3, *, include_shorts: bool = False):
    results = [item(index, title=f"Box Hill discovery {index}") for index in range(count)]
    return LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(7)).discover(
        ["Box Hill"], "Victoria, Australia", include_shorts=include_shorts,
    )


class LoveMyLocalsTests(unittest.TestCase):
    def test_desktop_declares_love_my_locals_tab_and_no_csv_step(self):
        source = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")
        self.assertIn("ProjectType.LOVE_MY_LOCALS", source)
        self.assertIn('text="FIND LOCALS"', source)
        self.assertIn('text="DEFAULT CTA BUTTON"', source)
        self.assertIn('"DEFAULT DESTINATION URL"', source)
        self.assertIn('text="SAVE"', source)
        self.assertIn('"SAVE LOVE MY LOCALS"', source)
        self.assertIn("ADVANCED / DISCOVERY SETTINGS", source)
        self.assertIn('text="REAL ESTATE: EXCLUDED"', source)
        self.assertIn('text="INCLUDE FULL COUNCIL MEETINGS"', source)
        self.assertIn("LOCAL TEXTURE:", source)
        self.assertIn("LoveMyLocalsDiscoveryService", source)
        self.assertNotIn("Love My Locals CSV", source)

    def test_one_two_three_locations_and_context(self):
        for locations in (["Box Hill"], ["Box Hill", "Box Hill North"], ["A", "B", "C"]):
            validated = validate_form(LoveMyLocalsFormValues(list(locations)))
            self.assertEqual(validated.locations, list(locations))
            self.assertEqual(len(resolved_locations(locations, "Victoria, Australia")), len(locations))
        with self.assertRaises(LoveMyLocalsError):
            validate_form(LoveMyLocalsFormValues([]))
        with self.assertRaises(LoveMyLocalsError):
            validate_form(LoveMyLocalsFormValues(["A", "B", "C", "D"]))

    def test_default_cta_selector_and_destination_url_validation(self):
        values = validate_form(LoveMyLocalsFormValues(
            ["Box Hill"],
            default_cta_type=PrimaryCtaType.EXPLORE,
            default_cta_url="https://example.com/box-hill",
        ))
        self.assertEqual(values.default_cta_type, PrimaryCtaType.EXPLORE)
        self.assertEqual(values.default_cta_url, "https://example.com/box-hill")
        with self.assertRaises(LoveMyLocalsError):
            validate_form(LoveMyLocalsFormValues(
                ["Box Hill"], default_cta_url="javascript:alert(1)",
            ))

    def test_relevance_weights_title_description_and_tag(self):
        self.assertEqual(qualify_metadata("Box Hill cafe", "", [], ["Box Hill"])[2], 3)
        self.assertEqual(qualify_metadata("Cafe", "At Box Hill", [], ["Box Hill"])[2], 2)
        self.assertEqual(qualify_metadata("Cafe", "", ["Box Hill"], ["Box Hill"])[2], 1)
        self.assertIsNone(qualify_metadata("Cafe", "Elsewhere", [], ["Box Hill"]))

    def test_multi_query_basket_covers_local_texture_and_australian_vocabulary(self):
        queries = discovery_queries_for_location("Bairnsdale", "Victoria, Australia")
        joined = " ".join(queries).casefold()
        self.assertGreaterEqual(len(queries), 10)
        for term in (
            "band", "local news", "old footage", "community group", "footy", "cricket",
            "pub", "rsl", "cfa", "ses", "historical society", "neighbourhood house",
            "funny", "local legend",
        ):
            self.assertIn(term, joined)
        self.assertTrue(all("bairnsdale" in query.casefold() for query in queries))
        self.assertTrue(all(len(query) < 500 for query in queries))

        client = FakeClient([item(1)])
        LoveMyLocalsDiscoveryService(client, rng=random.Random(1)).discover(["Box Hill"])
        self.assertEqual([query for query, _maximum in client.queries], discovery_queries_for_location("Box Hill"))
        self.assertTrue(all(maximum == 20 for _query, maximum in client.queries))

    def test_channel_context_and_local_texture_are_independent_signals(self):
        qualification = qualify_metadata(
            "Live original song", "Recorded in the eastern suburbs", [], ["Box Hill"], "Box Hill Musicians",
        )
        self.assertEqual(qualification, ("Box Hill", ["channel"], 1))
        score, content_type, evidence = local_texture_analysis(
            "Local band live at the pub", "Interview with the singer after the gig", ["original song"], "Community Radio",
        )
        self.assertGreaterEqual(score, 12)
        self.assertEqual(content_type, "MUSIC / PERFORMANCE")
        self.assertIn("band", evidence)

    def test_tourism_and_council_suppression_preserve_historical_exceptions(self):
        self.assertIn("tourism:high", tourism_suppression_flags(
            "Top 10 things to do in Box Hill", "Travel guide and tourist attractions", [], "Visit Box Hill Tourism",
        ))
        self.assertEqual(tourism_suppression_flags(
            "Strange 1970s Box Hill tourism advertisement", "Historical archive footage", [], "Local History",
        ), ["tourism:historical_context"])
        self.assertEqual(council_meeting_suppression_reason(
            "Box Hill Council Meeting livestream", "Ordinary meeting agenda", "Council Stream",
        ), "council:administrative_meeting")
        self.assertIsNone(council_meeting_suppression_reason(
            "Box Hill local project opens", "A council-supported community story", "Local News",
        ))

    def test_old_local_content_is_welcome_and_council_meetings_default_off(self):
        old_story = item(20, title="Box Hill local band live performance", published="2008-04-01T00:00:00Z")
        meeting = item(21, title="Box Hill Council Meeting livestream", description="Ordinary council meeting agenda")
        config = LoveMyLocalsDiscoveryService(FakeClient([old_story, meeting]), rng=random.Random(2)).discover(["Box Hill"])
        self.assertEqual([candidate.video.video_id for candidate in config.candidates], [old_story["id"]])
        self.assertEqual(config.candidates[0].video.published_at, "2008-04-01T00:00:00Z")
        self.assertEqual(config.discovery_summary["council_meetings_excluded"], 1)

        included = LoveMyLocalsDiscoveryService(FakeClient([old_story, meeting]), rng=random.Random(2)).discover(
            ["Box Hill"], include_council_meetings=True,
        )
        council = next(candidate for candidate in included.candidates if candidate.video.video_id == meeting["id"])
        self.assertIn("council:administrative_meeting", council.suppression_flags)

    def test_channel_diversity_tourism_cap_and_search_again_randomness(self):
        results = [
            item(index, title=f"Box Hill local band performance {index}", channel="One Prolific Channel", channel_id="one-channel")
            for index in range(12)
        ]
        results.extend(
            item(100 + index, title=f"Box Hill community interview {index}", channel=f"Local Voice {index}", channel_id=f"voice-{index}")
            for index in range(12)
        )
        results.extend(
            item(200 + index, title=f"Box Hill top attractions travel guide {index}", description="Things to do and where to stay", channel=f"Visit Box Hill {index}", channel_id=f"tour-{index}")
            for index in range(6)
        )
        first = LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(3)).discover(["Box Hill"], target=15)
        second = LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(9)).discover(["Box Hill"], target=15)
        active = [candidate for candidate in first.candidates if candidate.active]
        self.assertLessEqual(sum(candidate.video.channel_id == "one-channel" for candidate in active), 3)
        self.assertLessEqual(sum("tourism:high" in candidate.suppression_flags for candidate in active), 1)
        self.assertGreater(first.discovery_summary["channel_diversity_removals"], 0)
        self.assertNotEqual(
            [candidate.video.video_id for candidate in first.candidates if candidate.active],
            [candidate.video.video_id for candidate in second.candidates if candidate.active],
        )

    def test_three_locations_receive_representation_when_qualified_content_exists(self):
        results = []
        for base, place in enumerate(("Box Hill", "Box Hill North", "Box Hill South"), start=1):
            results.extend(
                item(base * 100 + index, title=f"{place} community story {index}", channel_id=f"{base}-{index}")
                for index in range(8)
            )
        config = LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(4)).discover(
            ["Box Hill", "Box Hill North", "Box Hill South"], target=18,
        )
        represented = {candidate.matched_location for candidate in config.candidates if candidate.active}
        self.assertEqual(represented, {"Box Hill", "Box Hill North", "Box Hill South"})

    def test_duplicate_private_unavailable_spam_and_incidental_results_are_excluded(self):
        valid = item(1)
        duplicate = dict(valid)
        results = [
            valid,
            duplicate,
            item(2, privacy="private"),
            item(3, embeddable=False),
            item(4, title="Box Hill crypto giveaway"),
            item(5, title="Unrelated video", description="Somewhere else"),
        ]
        config = LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(1)).discover(["Box Hill"])
        self.assertEqual([candidate.video.video_id for candidate in config.candidates], [valid["id"]])

    def test_real_estate_listings_are_hard_excluded_without_blocking_local_history(self):
        listing = item(10, title="Box Hill house for sale — 3 bedroom family home")
        auction = item(11, title="Box Hill auction result — 18 Station Street")
        walkthrough = item(
            12,
            title="12 Whitehorse Road Box Hill | 3 Bed 2 Bath agent walkthrough",
            channel="Box Hill Property Group",
        )
        rental = item(13, title="Box Hill apartment for rent — $650 per week")
        ambiguous = item(14, title="History of the Box Hill real estate market")
        legitimate = item(15, title="Box Hill Historical Society walking tour")
        config = LoveMyLocalsDiscoveryService(
            FakeClient([listing, auction, walkthrough, rental, ambiguous, legitimate]),
            rng=random.Random(1),
        ).discover(["Box Hill"])

        included_ids = {candidate.video.video_id for candidate in config.candidates}
        self.assertEqual(included_ids, {ambiguous["id"], legitimate["id"]})
        excluded_ids = {item["video_id"] for item in config.exclusion_diagnostics}
        self.assertEqual(excluded_ids, {listing["id"], auction["id"], walkthrough["id"], rental["id"]})
        self.assertTrue(all(item["reason"].startswith("real_estate:") for item in config.exclusion_diagnostics))

        restored = LoveMyLocalsConfig.from_dict(config.to_dict())
        self.assertEqual(restored.exclusion_diagnostics, config.exclusion_diagnostics)
        project = assemble_project(LoveMyLocalsFormValues(["Box Hill"]), restored, "box-hill-property-filter")
        with tempfile.TemporaryDirectory() as temporary:
            build_project_site(project, Path(temporary))
            public_payload = json.loads((Path(temporary) / "machine.json").read_text(encoding="utf-8"))
        self.assertNotIn("exclusionDiagnostics", public_payload["loveMyLocalsConfig"])
        self.assertNotIn("real_estate:", json.dumps(public_payload))

    def test_real_estate_classifier_requires_listing_context_not_one_ambiguous_keyword(self):
        self.assertIsNone(real_estate_exclusion_reason(
            "History of the Box Hill real estate market", "A local history documentary.", [], "Local History TV",
        ))
        self.assertIsNone(real_estate_exclusion_reason(
            "Box Hill community property discussion", "Council discusses public property policy.", [], "Council Stream",
        ))
        self.assertIsNone(real_estate_exclusion_reason(
            "Box Hill real estate market analysis", "Median prices reached $1,000,000.", [], "Local News",
        ))
        self.assertIsNone(real_estate_exclusion_reason(
            "Box Hill school open house", "Meet the teachers and tour the classrooms.", [], "Box Hill School",
        ))
        self.assertEqual(
            real_estate_exclusion_reason(
                "Box Hill apartment tour", "Now selling from $650,000. Book an inspection.", ["property"], "Local Realty",
            ),
            "real_estate:agency_listing_context",
        )

    def test_shorts_off_and_on(self):
        results = [item(1, duration="PT30S"), item(2, duration="PT2M")]
        off = LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(1)).discover(["Box Hill"], include_shorts=False)
        on = LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(1)).discover(["Box Hill"], include_shorts=True)
        self.assertEqual(len(off.candidates), 1)
        self.assertEqual(len(on.candidates), 2)
        self.assertTrue(any(candidate.is_short for candidate in on.candidates))

    def test_fewer_than_50_more_than_50_and_randomised_final_order(self):
        few = discovered(7)
        self.assertEqual(len(few.selected_videos), 7)
        results = [item(index, title=f"Box Hill discovery {index}") for index in range(80)]
        many = LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(9)).discover(["Box Hill"])
        self.assertEqual(len(many.selected_videos), 50)
        original = [value["id"] for value in results[:50]]
        self.assertNotEqual([video.video_id for video in many.selected_videos], original)

    def test_remove_and_replace_uses_remaining_candidate_pool(self):
        config = discovered(55)
        removed = config.selected_videos[0].video_id
        self.assertTrue(remove_candidate(config, removed))
        replacement = replace_candidate(config, removed, rng=random.Random(2))
        self.assertIsNotNone(replacement)
        self.assertNotEqual(replacement.video.video_id, removed)
        self.assertEqual(len(config.selected_videos), 50)

    def test_project_save_reload_cta_ticker_and_optional_destination(self):
        config = LoveMyLocalsDiscoveryService(
            FakeClient([item(index, title=f"Box Hill discovery {index}") for index in range(3)]),
            rng=random.Random(7),
        ).discover(
            ["Box Hill"],
            tourism_mode="include",
            include_council_meetings=True,
            default_cta_type=PrimaryCtaType.EXPLORE,
            default_cta_url="https://example.com/local",
        )
        values = LoveMyLocalsFormValues(
            ["Box Hill"],
            ticker_text=default_ticker(["Box Hill"]),
            default_cta_type=PrimaryCtaType.EXPLORE,
            default_cta_url="https://example.com/local",
            tourism_mode="include",
            include_council_meetings=True,
        )
        project = assemble_project(values, config, "box-hill")
        self.assertEqual(project.project_type, ProjectType.LOVE_MY_LOCALS)
        self.assertEqual(video_limit_for_project_type(project.project_type), 50)
        self.assertEqual(ticker_limit_for_project_type(project.project_type), 1500)
        self.assertGreater(len(CTA_CHOICES_BY_PROJECT[project.project_type]), 1)
        self.assertEqual(config.candidates[1].cta_url, "https://example.com/local")
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            store.save_project(project)
            loaded = store.load_project(project.slug)
            self.assertEqual(loaded.love_my_locals_config.locations, ["Box Hill"])
            self.assertEqual(loaded.ticker_text, project.ticker_text)
            self.assertEqual(loaded.love_my_locals_config.candidates[0].cta_url, "https://example.com/local")
            self.assertEqual(loaded.love_my_locals_config.default_cta_type, PrimaryCtaType.EXPLORE)
            self.assertEqual(loaded.love_my_locals_config.default_cta_url, "https://example.com/local")
            self.assertEqual(loaded.love_my_locals_config.tourism_mode, "include")
            self.assertTrue(loaded.love_my_locals_config.include_council_meetings)

    def test_quality_report_counts_selected_types_and_private_discovery_totals(self):
        results = [
            item(301, title="Box Hill local band live performance", channel_id="music-one"),
            item(302, title="Box Hill historical archive footage", channel_id="history-one"),
            item(303, title="Box Hill community football club story", channel_id="sport-one"),
        ]
        config = LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(5)).discover(["Box Hill"])
        report = discovery_quality_report(config)
        self.assertEqual(sum(report.get(name, 0) for name in (
            "MUSIC / PERFORMANCE", "PEOPLE / INTERVIEWS", "NEWS", "HISTORY / ARCHIVE",
            "COMMUNITY / CLUBS / SPORT", "BUSINESS / PUB / FOOD / MAKERS", "TOURISM",
            "OTHER / RANDOM LOCAL",
        )), 3)
        self.assertEqual(report["REAL ESTATE"], 0)
        self.assertEqual(report["final_videos"], 3)

    def test_saving_new_defaults_preserves_per_video_cta_overrides(self):
        config = discovered(3)
        overridden = config.candidates[0]
        overridden.cta_type = PrimaryCtaType.BOOK_NOW
        overridden.cta_url = "https://example.com/special"
        values = LoveMyLocalsFormValues(
            ["Box Hill"],
            default_cta_type=PrimaryCtaType.EXPLORE,
            default_cta_url="https://example.com/default",
        )
        project = assemble_project(values, config, "box-hill")
        candidates = project.love_my_locals_config.candidates
        self.assertEqual(candidates[0].cta_type, PrimaryCtaType.BOOK_NOW)
        self.assertEqual(candidates[0].cta_url, "https://example.com/special")
        self.assertTrue(all(item.cta_type is PrimaryCtaType.EXPLORE for item in candidates[1:]))
        self.assertTrue(all(item.cta_url == "https://example.com/default" for item in candidates[1:]))

    def test_preview_payload_logo_plaque_teal_ctas_and_qr(self):
        results = [item(index, title=f"Box Hill discovery {index}") for index in range(2)]
        config = LoveMyLocalsDiscoveryService(FakeClient(results), rng=random.Random(7)).discover(
            ["Box Hill", "Box Hill North"], "Victoria, Australia",
        )
        config.candidates[0].cta_url = "https://example.com/one"
        project = assemble_project(LoveMyLocalsFormValues(["Box Hill", "Box Hill North"]), config, "box-hill")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(project, destination)
            machine = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
            page = (destination / "index.html").read_text(encoding="utf-8")
            self.assertEqual(machine["projectType"], "love_my_locals")
            self.assertEqual(machine["loveMyLocalsConfig"]["brandTeal"], "#00C7CC")
            self.assertEqual(machine["channelMasterConfig"]["palette"], {
                "name": "MIDNIGHT",
                "customPrimary": None,
                "customAccent": None,
                "resolvedPrimary": "#172033",
                "resolvedSecondary": "#080B12",
                "resolvedAccent": "#6D80AF",
            })
            self.assertEqual(machine["videos"][0]["ctaURL"], "https://example.com/one")
            self.assertEqual(machine["videos"][1]["ctaURL"], "")
            public_json = json.dumps(machine)
            for private_key in (
                "matchBasis", "relevanceScore", "localTextureScore", "suppressionFlags",
                "qualificationReason", "discoverySummary", "candidateCount",
            ):
                self.assertNotIn(private_key, public_json)
            self.assertIn("BOX HILL + BOX HILL NORTH", page)
            self.assertIn("assets/love-my-locals/love-my-locals-logo.png", page)
            self.assertTrue((destination / "assets" / "love-my-locals" / "love-my-locals-logo.png").is_file())
            self.assertTrue((destination / "qr-card.png").is_file())

    def test_logo_has_real_transparency_and_public_asset_contains_no_secret(self):
        logo = resource_path("static/love-my-locals/love-my-locals-logo.png")
        with Image.open(logo) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
        self.assertNotIn("AIza", logo.read_bytes().decode("latin1", errors="ignore"))

    def test_authenticated_existing_email_path_is_type_aware_and_intercepted(self):
        project = assemble_project(LoveMyLocalsFormValues(["Box Hill"]), discovered(2), "box-hill")
        project.status = "published"
        project.published_url = "https://raggedya.github.io/aggits-video-jukebox/crispy-bits/box-hill/"
        project.publication_revision = "a" * 40
        response = Mock(ok=True, status_code=201)
        response.json.return_value = {"ok": True, "id": "intercepted"}
        with patch("aggits_video_factory.delivery.requests.post", return_value=response) as post:
            request_delivery(project, "operator@example.com", secret="test-secret", timestamp=1_700_000_000, nonce="f" * 32)
        payload = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(payload["projectType"], "love_my_locals")
        self.assertEqual(payload["productName"], "LOVE MY LOCALS")
        self.assertEqual(payload["qrUrl"], f"{project.published_url}qr-card.png")

    def test_api_and_quota_errors_are_reported_without_fabricating_results(self):
        for error in (YouTubeError("quota exceeded"), YouTubeError("invalid credentials"), YouTubeError("network failure")):
            with self.subTest(error=str(error)), self.assertRaises(YouTubeError):
                LoveMyLocalsDiscoveryService(FakeClient(error=error)).discover(["Box Hill"])

    def test_machine_mechanics_modules_are_not_modified_for_love_my_locals(self):
        for name in ("single-reel-engine.js", "machine-mechanics-core.js"):
            source = (ROOT / "static" / name).read_text(encoding="utf-8")
            self.assertNotIn("love_my_locals", source)

    def test_project_rejects_unsynchronised_selection(self):
        config = discovered(2)
        project = assemble_project(LoveMyLocalsFormValues(["Box Hill"]), config, "box-hill")
        data = project.to_dict()
        data["excluded_video_ids"] = []
        config.candidates[0].active = False
        data["love_my_locals_config"] = config.to_dict()
        with self.assertRaises(Exception):
            Project.from_dict(data)


if __name__ == "__main__":
    unittest.main()
