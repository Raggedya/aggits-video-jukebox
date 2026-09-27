from __future__ import annotations

import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import requests

from .models import LocalPick, utc_now


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
USER_AGENT = "CRISPY-BITS-Desktop/3.9 Local-Picks (operator-triggered OpenStreetMap discovery)"
MAX_LOCAL_PICKS = 9
CACHE_SECONDS = 15 * 60
TARGET_CATEGORIES = (
    "CAFE",
    "PUB / BAR",
    "RESTAURANT",
    "BAKERY",
    "SHOP",
    "LOCAL SERVICE",
    "TAKEAWAY / FOOD",
    "SPECIALTY / INTERESTING LOCAL BUSINESS",
    "WILDCARD",
)

_CHAIN_NAMES = {
    "7-eleven", "aldi", "amart furniture", "anaconda", "anytime fitness", "autobarn",
    "beacon lighting", "big w", "bunnings", "coles", "costco", "domino's", "dominos",
    "eb games", "fantastic furniture", "harvey norman", "hungry jack's", "hungry jacks",
    "bmw", "ford", "honda", "hyundai", "isuzu", "jaycar", "jb hi-fi", "kfc", "kia",
    "kmart", "mazda", "mcdonald's", "mcdonalds", "mercedes-benz", "mitsubishi", "nissan",
    "officeworks", "petbarn", "petstock", "red rooster", "rebel", "repco", "spotlight",
    "starbucks", "subaru", "subway", "suzuki", "supercheap auto", "target",
    "the reject shop", "tjm", "toyota", "volkswagen", "woolworths",
}
_EXCLUDED_SHOPS = {
    "alcohol", "cannabis", "chemist", "convenience", "e-cigarette", "funeral_directors",
    "gambling", "money_lender", "pawnbroker", "supermarket", "tobacco", "weapons",
}
_SERVICE_SHOPS = {
    "beauty", "bicycle", "car_repair", "dry_cleaning", "florist", "hairdresser",
    "laundry", "mobile_phone", "optician", "pet_grooming", "shoe_repair", "tailor",
}
_SPECIALTY_SHOPS = {
    "antiques", "art", "books", "camera", "charity", "collector", "craft", "fabric",
    "gift", "hobby", "musical_instrument", "music", "second_hand", "toys", "video_games",
}
_FRIENDLY_TOURISM = {"gallery", "museum", "attraction"}
_FRIENDLY_LEISURE = {"bowling_alley", "escape_game", "fitness_centre", "sports_centre"}
_SOCIAL_HOSTS = {"facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com"}
_cache_lock = threading.Lock()
_candidate_cache: dict[str, tuple[float, list[LocalPick], dict[str, object]]] = {}


class LocalPicksError(RuntimeError):
    pass


@dataclass(slots=True)
class LocalPicksDiscovery:
    candidates: list[LocalPick]
    selected: list[LocalPick]
    resolved_location: str
    raw_count: int
    rejected_count: int


def _clean(value: object, maximum: int = 300) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:maximum]


def _website(value: object) -> str | None:
    cleaned = _clean(value, 500)
    if not cleaned:
        return None
    if not re.match(r"^https?://", cleaned, re.I):
        if not re.fullmatch(r"(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?", cleaned):
            return None
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    if parsed.hostname.casefold() in _SOCIAL_HOSTS:
        return None
    return cleaned


def _category(tags: dict[str, object]) -> tuple[str, str] | None:
    amenity = _clean(tags.get("amenity"), 80).casefold()
    shop = _clean(tags.get("shop"), 80).casefold()
    craft = _clean(tags.get("craft"), 80).casefold()
    tourism = _clean(tags.get("tourism"), 80).casefold()
    leisure = _clean(tags.get("leisure"), 80).casefold()
    if amenity == "cafe":
        return "CAFE", "Cafe"
    if amenity in {"pub", "bar", "biergarten"}:
        return "PUB / BAR", "Pub" if amenity == "pub" else "Bar"
    if amenity == "restaurant":
        return "RESTAURANT", "Restaurant"
    if shop == "bakery":
        return "BAKERY", "Bakery"
    if amenity in {"fast_food", "food_court", "ice_cream"}:
        return "TAKEAWAY / FOOD", "Takeaway" if amenity == "fast_food" else amenity.replace("_", " ").title()
    if amenity in {"cinema", "theatre"}:
        return "SPECIALTY / INTERESTING LOCAL BUSINESS", amenity.title()
    if shop:
        if shop in _EXCLUDED_SHOPS:
            return None
        if shop in _SERVICE_SHOPS:
            return "LOCAL SERVICE", shop.replace("_", " ").title()
        if shop in _SPECIALTY_SHOPS:
            return "SPECIALTY / INTERESTING LOCAL BUSINESS", shop.replace("_", " ").title()
        return "SHOP", shop.replace("_", " ").title()
    if craft:
        return "LOCAL SERVICE", craft.replace("_", " ").title()
    if tourism in _FRIENDLY_TOURISM:
        return "SPECIALTY / INTERESTING LOCAL BUSINESS", tourism.title()
    if leisure in _FRIENDLY_LEISURE:
        return "SPECIALTY / INTERESTING LOCAL BUSINESS", leisure.replace("_", " ").title()
    return None


def _locality(tags: dict[str, object], fallback: str) -> str:
    for key in ("addr:suburb", "addr:city", "addr:town", "addr:village", "addr:locality"):
        value = _clean(tags.get(key), 100)
        if value:
            return value
    return _clean(fallback, 100)


def _description(kind: str, locality: str, tags: dict[str, object]) -> str:
    cuisine = _clean(tags.get("cuisine"), 80).replace("_", " ")
    if cuisine:
        description = f"{kind} serving {cuisine} in {locality}"
    else:
        description = f"{kind} in {locality}"
    return description[:100].rstrip()


def _normalise_element(element: dict[str, object], location: str, generated_at: str) -> LocalPick | None:
    osm_type = _clean(element.get("type"), 20).casefold()
    osm_id = str(element.get("id") or "").strip()
    tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
    name = _clean(tags.get("name"), 140)
    if osm_type not in {"node", "way", "relation"} or not osm_id.isdigit() or not name or "\ufffd" in name:
        return None
    name_key = name.casefold()
    brand_key = _clean(tags.get("brand"), 120).casefold()
    if any(
        value == chain or value.startswith(f"{chain} ")
        for value in (name_key, brand_key)
        for chain in _CHAIN_NAMES
        if value
    ):
        return None
    categorised = _category(tags)
    if not categorised:
        return None
    category, kind = categorised
    locality = _locality(tags, location)
    website = _website(tags.get("website") or tags.get("contact:website"))
    return LocalPick(
        id=f"osm-{osm_type}-{osm_id}",
        osm_type=osm_type,
        osm_id=osm_id,
        business_name=name,
        category=category,
        short_description=_description(kind, locality, tags),
        location=locality,
        website_url=website,
        source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        generated_at=generated_at,
    )


def select_local_picks(candidates: Iterable[LocalPick], *, rng: random.Random | None = None) -> list[LocalPick]:
    randomiser = rng or random.SystemRandom()
    pool = list(candidates)
    randomiser.shuffle(pool)
    selected: list[LocalPick] = []
    used: set[str] = set()
    for target in TARGET_CATEGORIES[:-1]:
        options = [item for item in pool if item.category == target and item.id not in used]
        if options:
            website_options = [item for item in options if item.website_url]
            choice = randomiser.choice(options + website_options + website_options)
            selected.append(choice)
            used.add(choice.id)
    remaining = [item for item in pool if item.id not in used]
    if remaining and len(selected) < MAX_LOCAL_PICKS:
        website_options = [item for item in remaining if item.website_url]
        choice = randomiser.choice(remaining + website_options + website_options)
        selected.append(LocalPick.from_dict(choice.to_dict() | {"category": "WILDCARD"}))
        used.add(choice.id)
    while remaining and len(selected) < MAX_LOCAL_PICKS:
        represented = {item.category for item in selected}
        diverse = [item for item in remaining if item.id not in used and item.category not in represented]
        options = diverse or [item for item in remaining if item.id not in used]
        if not options:
            break
        website_options = [item for item in options if item.website_url]
        choice = randomiser.choice(options + website_options + website_options)
        selected.append(choice)
        used.add(choice.id)
    randomiser.shuffle(selected)
    return selected[:MAX_LOCAL_PICKS]


def replacement_for(
    current: LocalPick,
    candidates: Iterable[LocalPick],
    selected: Iterable[LocalPick],
    *,
    rng: random.Random | None = None,
) -> LocalPick | None:
    used = {item.id for item in selected if item.id != current.id}
    options = [item for item in candidates if item.id not in used and item.id != current.id and item.category == current.category]
    if not options and current.category == "WILDCARD":
        options = [item for item in candidates if item.id not in used and item.id != current.id]
    if not options:
        return None
    website_options = [item for item in options if item.website_url]
    choice = (rng or random.SystemRandom()).choice(options + website_options + website_options)
    if current.category == "WILDCARD":
        return LocalPick.from_dict(choice.to_dict() | {"category": "WILDCARD"})
    return choice


class OverpassLocalPicksService:
    def __init__(self, *, session: requests.Session | None = None, rng: random.Random | None = None) -> None:
        self.session = session or requests.Session()
        self.rng = rng or random.SystemRandom()

    def _resolve(self, location: str) -> tuple[tuple[float, float, float, float], str]:
        response = self.session.get(
            NOMINATIM_URL,
            params={"q": location, "format": "jsonv2", "limit": 1, "addressdetails": 1},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=(8, 20),
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        payload = response.json()
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise LocalPicksError(f'OpenStreetMap could not resolve "{location}" in Australia.')
        result = payload[0]
        bounds = result.get("boundingbox")
        if not isinstance(bounds, list) or len(bounds) != 4:
            raise LocalPicksError("OpenStreetMap returned an unusable location boundary.")
        try:
            south, north, west, east = (float(value) for value in bounds)
            latitude = float(result.get("lat"))
            longitude = float(result.get("lon"))
        except (TypeError, ValueError) as error:
            raise LocalPicksError("OpenStreetMap returned an invalid location boundary.") from error
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
            raise LocalPicksError("OpenStreetMap returned an invalid location boundary.")
        # A city or region boundary can be enormous. Keep this operator-triggered
        # public Overpass query local and bounded to roughly a 10 km search area.
        south = max(south, latitude - 0.09)
        north = min(north, latitude + 0.09)
        west = max(west, longitude - 0.11)
        east = min(east, longitude + 0.11)
        return (south, west, north, east), _clean(result.get("display_name"), 300) or location

    @staticmethod
    def _query(bounds: tuple[float, float, float, float]) -> str:
        bbox = ",".join(f"{value:.7f}" for value in bounds)
        selectors = (
            '["amenity"~"^(cafe|pub|bar|biergarten|restaurant|fast_food|food_court|ice_cream|cinema|theatre)$"]',
            '["shop"]',
            '["craft"]',
            '["tourism"~"^(gallery|museum|attraction)$"]',
            '["leisure"~"^(bowling_alley|escape_game|fitness_centre|sports_centre)$"]',
        )
        statements = "".join(f"nwr{selector}({bbox});" for selector in selectors)
        return f"[out:json][timeout:25];({statements});out center tags;"

    def _overpass(self, query: str) -> dict[str, object]:
        errors: list[str] = []
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                response = self.session.post(
                    endpoint,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                    timeout=(10, 50),
                )
                response.raise_for_status()
                response.encoding = "utf-8"
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
                    raise LocalPicksError("Overpass returned malformed business data.")
                return payload
            except (requests.RequestException, ValueError, LocalPicksError) as error:
                errors.append(f"{urlparse(endpoint).hostname}: {type(error).__name__}")
        raise LocalPicksError("OpenStreetMap business discovery is temporarily unavailable. " + "; ".join(errors))

    def discover(self, location: str, *, force_refresh: bool = False) -> LocalPicksDiscovery:
        cleaned = _clean(location, 200)
        if not cleaned:
            raise LocalPicksError("Enter Location 1 before generating Local Picks.")
        cache_key = cleaned.casefold()
        now = time.monotonic()
        with _cache_lock:
            cached = _candidate_cache.get(cache_key)
        if cached and not force_refresh and now - cached[0] < CACHE_SECONDS:
            candidates = [LocalPick.from_dict(item.to_dict()) for item in cached[1]]
            metadata = cached[2]
            return LocalPicksDiscovery(
                candidates=candidates,
                selected=select_local_picks(candidates, rng=self.rng),
                resolved_location=str(metadata["resolved_location"]),
                raw_count=int(metadata["raw_count"]),
                rejected_count=int(metadata["rejected_count"]),
            )
        bounds, resolved = self._resolve(cleaned)
        payload = self._overpass(self._query(bounds))
        generated_at = utc_now()
        elements = payload.get("elements") or []
        candidates: list[LocalPick] = []
        seen: set[str] = set()
        rejected = 0
        for element in elements:
            if not isinstance(element, dict):
                rejected += 1
                continue
            item = _normalise_element(element, cleaned.split(",", 1)[0], generated_at)
            signature = item.business_name.casefold() if item else ""
            if not item or item.id in seen or signature in seen:
                rejected += 1
                continue
            seen.update({item.id, signature})
            candidates.append(item)
        if not candidates:
            raise LocalPicksError("No reliable OpenStreetMap businesses were found for this location.")
        metadata = {"resolved_location": resolved, "raw_count": len(elements), "rejected_count": rejected}
        with _cache_lock:
            _candidate_cache[cache_key] = (now, [LocalPick.from_dict(item.to_dict()) for item in candidates], metadata)
        return LocalPicksDiscovery(
            candidates=candidates,
            selected=select_local_picks(candidates, rng=self.rng),
            resolved_location=resolved,
            raw_count=len(elements),
            rejected_count=rejected,
        )
