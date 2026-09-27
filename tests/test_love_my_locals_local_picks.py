from __future__ import annotations

import json
import random
import tempfile
import time
import unittest
from pathlib import Path

import requests

from aggits_video_factory.local_picks import (
    LocalPicksError,
    OverpassLocalPicksService,
    replacement_for,
    select_local_picks,
)
from aggits_video_factory.love_my_locals import LoveMyLocalsFormValues, assemble_project
from aggits_video_factory.models import LocalPick, LoveMyLocalsCandidate, LoveMyLocalsConfig, Video
from aggits_video_factory.site_builder import build_project_site


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload, status: int = 200) -> None:
        self.payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, elements: list[dict]) -> None:
        self.elements = elements
        self.get_calls: list[dict] = []
        self.post_calls: list[dict] = []

    def get(self, _url, **kwargs):
        self.get_calls.append(kwargs)
        return FakeResponse([{
            "display_name": "Bairnsdale, East Gippsland, Victoria, Australia",
            "boundingbox": ["-37.86", "-37.80", "147.58", "147.66"],
            "lat": "-37.83", "lon": "147.62",
        }])

    def post(self, _url, **kwargs):
        self.post_calls.append(kwargs)
        return FakeResponse({"elements": self.elements})


def element(index: int, name: str, **tags) -> dict:
    return {"type": "node", "id": index, "tags": {"name": name, "addr:town": "Bairnsdale", **tags}}


def pick(index: int, category: str, website: str | None = None) -> LocalPick:
    return LocalPick(
        id=f"osm-node-{index}", osm_type="node", osm_id=str(index),
        business_name=f"Business {index}", category=category,
        short_description=f"Local business in Bairnsdale", location="Bairnsdale",
        website_url=website, source_url=f"https://www.openstreetmap.org/node/{index}",
        generated_at="2026-09-27T00:00:00Z",
    )


def project_with_picks(picks: list[LocalPick]):
    video = Video(
        video_id="abcdefghijk", title="Bairnsdale local story", display_title="Bairnsdale local story",
        url="https://www.youtube.com/watch?v=abcdefghijk",
        embed_url="https://www.youtube-nocookie.com/embed/abcdefghijk",
        thumbnail_url="https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z", duration_seconds=120,
        channel_title="Local Channel", channel_id="local-channel",
    )
    config = LoveMyLocalsConfig(
        locations=["Bairnsdale"], local_picks=picks,
        candidates=[LoveMyLocalsCandidate(
            video=video, matched_location="Bairnsdale", match_basis=["title"],
            relevance_score=3, active=True,
        )],
    )
    return assemble_project(LoveMyLocalsFormValues(["Bairnsdale"]), config, "bairnsdale")


class LocalPicksTests(unittest.TestCase):
    def test_overpass_discovery_maps_categories_urls_sources_and_uses_no_key(self):
        session = FakeSession([
            element(1, "River Cafe", amenity="cafe", website="river.example"),
            element(2, "Railway Hotel", amenity="pub"),
            element(3, "Main Street Dining", amenity="restaurant"),
            element(4, "Town Bakery", shop="bakery"),
            element(5, "Local Books", shop="books", **{"contact:website": "https://books.example"}),
            element(6, "Bike Repairs", shop="bicycle"),
            element(7, "Quick Bite", amenity="fast_food"),
            element(8, "Regional Gallery", tourism="gallery"),
            element(9, "Corner Gifts", shop="gift"),
        ])
        result = OverpassLocalPicksService(session=session, rng=random.Random(3)).discover(
            "Bairnsdale, Victoria, Australia", force_refresh=True,
        )
        self.assertEqual(result.raw_count, 9)
        self.assertEqual(len(result.selected), 9)
        self.assertEqual({item.category for item in result.selected}, {
            "CAFE", "PUB / BAR", "RESTAURANT", "BAKERY", "LOCAL SERVICE",
            "TAKEAWAY / FOOD", "SPECIALTY / INTERESTING LOCAL BUSINESS", "WILDCARD",
        })
        river = next(item for item in result.candidates if item.business_name == "River Cafe")
        self.assertEqual(river.website_url, "https://river.example")
        self.assertEqual(river.source_url, "https://www.openstreetmap.org/node/1")
        request_text = json.dumps(session.get_calls + session.post_calls)
        self.assertNotIn("api_key", request_text.casefold())
        self.assertNotIn("google", request_text.casefold())
        self.assertIn("CRISPY-BITS-Desktop", request_text)

    def test_chain_inappropriate_unnamed_and_social_only_entries_are_filtered(self):
        session = FakeSession([
            element(1, "McDonald's", amenity="fast_food", website="https://mcdonalds.example"),
            element(2, "Local Supermarket", shop="supermarket"),
            element(3, "Friendly Cafe", amenity="cafe", website="https://facebook.com/friendly"),
            {"type": "node", "id": 4, "tags": {"amenity": "cafe"}},
            element(5, "Broken Caf�", amenity="cafe"),
        ])
        result = OverpassLocalPicksService(session=session, rng=random.Random(1)).discover("Bairnsdale", force_refresh=True)
        self.assertEqual([item.business_name for item in result.candidates], ["Friendly Cafe"])
        self.assertIsNone(result.candidates[0].website_url)
        self.assertEqual(result.rejected_count, 4)

    def test_selection_is_limited_varied_randomised_and_replace_avoids_current(self):
        categories = [
            "CAFE", "PUB / BAR", "RESTAURANT", "BAKERY", "SHOP", "LOCAL SERVICE",
            "TAKEAWAY / FOOD", "SPECIALTY / INTERESTING LOCAL BUSINESS",
        ]
        candidates = [pick(index + 1, category) for index, category in enumerate(categories)]
        candidates.extend(pick(index + 20, "CAFE") for index in range(4))
        first = select_local_picks(candidates, rng=random.Random(1))
        second = select_local_picks(candidates, rng=random.Random(9))
        self.assertLessEqual(len(first), 9)
        self.assertEqual(len({item.id for item in first}), len(first))
        self.assertNotEqual([item.id for item in first], [item.id for item in second])
        cafe = next(item for item in first if item.category == "CAFE")
        replacement = replacement_for(cafe, candidates, first, rng=random.Random(2))
        self.assertIsNotNone(replacement)
        self.assertNotEqual(replacement.id, cafe.id)
        self.assertEqual(replacement.category, "CAFE")

    def test_recent_results_are_cached_and_overpass_endpoint_failure_falls_back(self):
        elements = [element(index, f"Cafe {index}", amenity="cafe") for index in range(1, 5)]

        class FallbackSession(FakeSession):
            def post(self, url, **kwargs):
                self.post_calls.append({"url": url, **kwargs})
                if len(self.post_calls) == 1:
                    raise requests.Timeout("first endpoint unavailable")
                return FakeResponse({"elements": self.elements})

        session = FallbackSession(elements)
        service = OverpassLocalPicksService(session=session, rng=random.Random(4))
        first = service.discover("Cacheville, Victoria, Australia", force_refresh=True)
        second = service.discover("Cacheville, Victoria, Australia")
        self.assertEqual(len(session.get_calls), 1)
        self.assertEqual(len(session.post_calls), 2)
        self.assertEqual({item.id for item in first.candidates}, {item.id for item in second.candidates})

    def test_provider_has_a_firm_wall_clock_deadline(self):
        class SlowSession(FakeSession):
            def post(self, _url, **kwargs):
                self.post_calls.append(kwargs)
                time.sleep(0.2)
                return FakeResponse({"elements": self.elements})

        service = OverpassLocalPicksService(
            session=SlowSession([element(1, "Slow Cafe", amenity="cafe")]),
            request_deadline_seconds=0.02,
        )
        started = time.monotonic()
        with self.assertRaisesRegex(LocalPicksError, "temporarily unavailable"):
            service.discover("Slowville, Victoria, Australia", force_refresh=True)
        self.assertLess(time.monotonic() - started, 0.3)

    def test_unresolvable_location_fails_without_fabricating_businesses(self):
        session = FakeSession([])
        session.get = lambda *_args, **_kwargs: FakeResponse([])
        with self.assertRaisesRegex(LocalPicksError, "could not resolve"):
            OverpassLocalPicksService(session=session).discover("Not A Real Place", force_refresh=True)

    def test_project_persistence_is_backward_compatible(self):
        item = pick(1, "CAFE", "https://cafe.example")
        config = LoveMyLocalsConfig(locations=["Bairnsdale"], local_picks=[item])
        restored = LoveMyLocalsConfig.from_dict(config.to_dict())
        self.assertEqual(restored.local_picks[0].to_dict(), item.to_dict())
        legacy = config.to_dict()
        legacy.pop("localPicks")
        self.assertEqual(LoveMyLocalsConfig.from_dict(legacy).local_picks, [])

    def test_local_pick_validation_limits_count_and_rejects_bad_urls(self):
        with self.assertRaises(Exception):
            LoveMyLocalsConfig(locations=["Bairnsdale"], local_picks=[pick(index, "CAFE") for index in range(1, 11)])
        with self.assertRaises(Exception):
            pick(1, "CAFE", "javascript:alert(1)")

    def test_public_machine_renders_static_panel_only_when_picks_exist(self):
        picks = [
            pick(1, "CAFE", "https://cafe.example"),
            pick(2, "PUB / BAR"),
            pick(3, "RESTAURANT"),
            pick(4, "BAKERY"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(project_with_picks(picks), destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
            machine = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
        self.assertIn("★ LOCAL PICKS ★", page)
        self.assertIn("data-local-picks-next", page)
        self.assertIn('target="_blank"', page)
        self.assertIn("DATA © OPENSTREETMAP CONTRIBUTORS", page)
        self.assertEqual(len(machine["loveMyLocalsConfig"]["localPicks"]), 4)
        self.assertNotIn("overpass", json.dumps(machine).casefold())
        self.assertNotIn("nominatim", page.casefold())

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(project_with_picks([]), destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("★ LOCAL PICKS ★", page)
        self.assertNotIn("data-local-picks", page)

    def test_front_end_has_future_reporting_hook_without_backend(self):
        source = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
        self.assertIn("local_pick_click", source)
        self.assertIn("crispy-bits:local-pick", source)
        self.assertNotIn("/api/local-pick", source)

    def test_desktop_exposes_review_controls(self):
        source = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")
        for text in ("GENERATE LOCAL PICKS", "REGENERATE ALL", "KEEP ✓", "REPLACE", "REMOVE"):
            self.assertIn(text, source)
        self.assertIn("SEARCHING…", source)
        self.assertIn("up to about one minute", source)


if __name__ == "__main__":
    unittest.main()
