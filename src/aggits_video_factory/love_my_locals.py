from __future__ import annotations

import html
import random
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable
from urllib.parse import urlparse
from uuid import uuid4

from .config import MAX_LOVE_MY_LOCALS_CANDIDATES, MAX_LOVE_MY_LOCALS_VIDEOS
from .models import (
    CHANNEL_MASTER_CTA_TYPES,
    ChannelMasterConfig,
    LoveMyLocalsCandidate,
    LoveMyLocalsConfig,
    PrimaryCtaType,
    Project,
    ProjectType,
    Video,
    utc_now,
)
from .youtube_api import ChannelCatalogue, YouTubeClient, YouTubeError, best_thumbnail, parse_duration


DEFAULT_GEOGRAPHY = "Victoria, Australia"
MATCH_WEIGHTS = {"title": 3, "description": 2, "tag": 1, "channel": 1}
TOURISM_MODES = frozenset({"limited", "include"})
CONTENT_TYPES = (
    "MUSIC / PERFORMANCE",
    "PEOPLE / INTERVIEWS",
    "NEWS",
    "HISTORY / ARCHIVE",
    "COMMUNITY / CLUBS / SPORT",
    "BUSINESS / PUB / FOOD / MAKERS",
    "TOURISM",
    "OTHER / RANDOM LOCAL",
)
DISCOVERY_QUERY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bands", ("band",)),
    ("musicians", ("musician",)),
    ("live-music", ("singer", "live music", "gig", "concert", "local music", "original song")),
    ("news", ("local news", "news")),
    ("people", ("interview", "people", "locals", "local story", "resident", "profile")),
    ("history", ("history", "historical", "old footage", "archive", "memories", "heritage", "historical society")),
    ("community", ("community", "club", "community group", "charity", "volunteer", "neighbourhood house", "community centre")),
    ("sport", ("sporting club", "football", "footy", "cricket", "basketball", "netball", "sport", "bowls club")),
    ("social-life", ("pub", "venue", "restaurant", "cafe", "brewery", "record store", "bookshop", "RSL")),
    ("culture-business", ("business", "shop", "maker", "artist", "gallery", "theatre", "performance")),
    ("events-schools", ("school", "festival", "market", "event", "live performance")),
    ("local-services", ("community radio", "radio", "CFA", "SES", "council")),
    ("quirks", ("funny", "unusual", "weird", "story", "character", "local legend", "collection", "hobby")),
)
LOCAL_TEXTURE_TERMS: dict[str, tuple[str, ...]] = {
    "MUSIC / PERFORMANCE": ("band", "cover band", "musician", "singer", "music", "country music", "gig", "live music", "concert", "orchestra", "performance", "original song", "music video"),
    "PEOPLE / INTERVIEWS": ("interview", "resident", "people", "profile", "volunteer", "character", "local legend", "collector", "inventor", "hobby"),
    "NEWS": ("local news", "regional news", "news report", "news", "ABC", "community radio", "radio"),
    "HISTORY / ARCHIVE": ("history", "historical", "archive", "old footage", "memories", "heritage", "documentary"),
    "COMMUNITY / CLUBS / SPORT": ("club", "association", "community", "charity", "school", "football", "footy", "cricket", "basketball", "netball", "RSL", "CFA", "SES", "bowls club", "community centre", "neighbourhood house"),
    "BUSINESS / PUB / FOOD / MAKERS": ("pub", "cafe", "restaurant", "shop", "venue", "business", "brewery", "record store", "bookshop", "maker", "artist", "gallery", "theatre", "market"),
    "OTHER / RANDOM LOCAL": ("unusual", "weird", "funny", "story", "event", "collection"),
}
TOURISM_PATTERN = re.compile(
    r"\b(?:tourism|travel\s+guide|travel\s+vlog|things\s+to\s+do|top\s+\d+\s+(?:things|attractions)|"
    r"tourist\s+attractions?|where\s+to\s+stay|accommodation|holiday|vacation|destination\s+guide|"
    r"travel\s+itinerary|weekend\s+getaway|tourism\s+campaign|destination\s+marketing|"
    r"aerial\s+view|drone\s+tour|walking\s+tour)\b",
    re.I,
)
TOURISM_CHANNEL_PATTERN = re.compile(r"(?:tourism|visitor\s+centre|destination|\bvisit\s+[A-Za-z]|travel)", re.I)
HISTORICAL_CONTEXT_PATTERN = re.compile(r"\b(?:history|historical|archive|old\s+footage|heritage|memories|vintage)\b", re.I)
COUNCIL_MEETING_PATTERN = re.compile(
    r"\b(?:ordinary|special|monthly|statutory)?\s*(?:council|committee)\s+(?:meeting|livestream)|"
    r"\b(?:council\s+agenda|minutes\s+of\s+(?:the\s+)?meeting|planning\s+committee\s+meeting|"
    r"public\s+question\s+time|council\s+chamber\s+livestream)\b",
    re.I,
)
GENERIC_PROMO_PATTERN = re.compile(
    r"\b(?:limited\s+time|buy\s+now|call\s+today|special\s+offer|our\s+services|sales\s+presentation|corporate\s+video)\b",
    re.I,
)
SPAM_PATTERN = re.compile(r"\b(?:sub\s*4\s*sub|free\s+bitcoin|crypto\s+giveaway|click\s+here\s+to\s+earn)\b", re.I)
PROPERTY_CONTEXT_PATTERN = re.compile(
    r"\b(?:real\s+estate|realty|realtor|estate\s+agents?|property|properties|house|home|apartment|unit|townhouse|land|property\s+development)\b",
    re.I,
)
DIRECT_PROPERTY_LISTING_PATTERN = re.compile(
    r"\b(?:(?:property|house|home|apartment|unit|townhouse|land)\s+(?:is\s+|now\s+)?(?:for\s+sale|for\s+rent)|"
    r"(?:for\s+sale|for\s+rent)\s+(?:property|house|home|apartment|unit|townhouse|land)|"
    r"property\s+listing|real[ -]?estate\s+listing|rental\s+listing|"
    r"property\s+inspection|land\s+for\s+sale)\b",
    re.I,
)
PROPERTY_AGENCY_PATTERN = re.compile(
    r"\b(?:real\s+estate|realty|realtor|estate\s+agents?|property\s+(?:group|sales)|properties)\b",
    re.I,
)
PROPERTY_SALES_PATTERN = re.compile(
    r"\b(?:for\s+sale|for\s+rent|auction|open\s+(?:home|house)|inspection|listing|sold|rental|"
    r"rent|now\s+selling|private\s+sale|display\s+suite|enquire\s+now|off[ -]the[ -]plan)\b",
    re.I,
)
PROPERTY_TOUR_PATTERN = re.compile(
    r"\b(?:agent\s+walkthrough|property\s+walkthrough|walk[ -]?through|house\s+tour|home\s+tour|"
    r"property\s+tour|apartment\s+tour|unit\s+tour)\b",
    re.I,
)
STREET_ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}[A-Za-z]?\s+[A-Za-z][A-Za-z' -]{1,45}\s"
    r"(?:street|st|road|rd|avenue|ave|drive|dr|court|ct|lane|ln|crescent|cres|boulevard|blvd|parade|place|pl|way)\b",
    re.I,
)
PROPERTY_SPEC_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:bed(?:room)?s?|bath(?:room)?s?|car\s*spaces?|garage|sqm|m2|m²|square\s+metres?)\b",
    re.I,
)
PROPERTY_PRICE_PATTERN = re.compile(
    r"(?:\$\s?\d[\d,.]*(?:\s*(?:k|m|million))?|\b\d[\d,.]*\s*(?:per\s+week|p/?w)\b)",
    re.I,
)


class LoveMyLocalsError(RuntimeError):
    pass


@dataclass(slots=True)
class LoveMyLocalsFormValues:
    locations: list[str] = field(default_factory=list)
    geography: str = DEFAULT_GEOGRAPHY
    include_shorts: bool = False
    ticker_text: str = ""
    default_cta_type: PrimaryCtaType | str = PrimaryCtaType.VISIT_WEBSITE
    default_cta_url: str = ""
    tourism_mode: str = "limited"
    include_council_meetings: bool = False
    explore_url: str = ""

    def comparable(self) -> tuple[object, ...]:
        return (
            tuple(self.locations),
            self.geography,
            bool(self.include_shorts),
            self.ticker_text,
            self.default_cta_type.value if isinstance(self.default_cta_type, PrimaryCtaType) else str(self.default_cta_type),
            self.default_cta_url,
            self.tourism_mode,
            bool(self.include_council_meetings),
            self.explore_url,
        )


def normalize_locations(values: Iterable[str]) -> list[str]:
    locations = [re.sub(r"\s+", " ", str(value)).strip() for value in values if str(value).strip()]
    if not 1 <= len(locations) <= 3:
        raise LoveMyLocalsError("Enter between one and three locations.")
    if len({item.casefold() for item in locations}) != len(locations):
        raise LoveMyLocalsError("Each location must be different.")
    if any(len(item) > 80 for item in locations):
        raise LoveMyLocalsError("Each location must be 80 characters or fewer.")
    return locations


def validate_form(values: LoveMyLocalsFormValues) -> LoveMyLocalsFormValues:
    locations = normalize_locations(values.locations)
    geography = re.sub(r"\s+", " ", str(values.geography or DEFAULT_GEOGRAPHY)).strip()
    if not geography or len(geography) > 100:
        raise LoveMyLocalsError("Enter a valid geographic context, such as Victoria, Australia.")
    ticker = str(values.ticker_text or "").strip() or default_ticker(locations)
    if len(ticker) > 1500:
        raise LoveMyLocalsError("Ticker Text cannot exceed 1500 characters.")
    try:
        cta_type = PrimaryCtaType(values.default_cta_type)
    except (TypeError, ValueError) as error:
        raise LoveMyLocalsError("Select a valid Love My Locals CTA button.") from error
    if cta_type not in CHANNEL_MASTER_CTA_TYPES:
        raise LoveMyLocalsError("Select a valid Love My Locals CTA button.")
    cta_url = str(values.default_cta_url or "").strip()
    if cta_url:
        parsed = urlparse(cta_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise LoveMyLocalsError("CTA Destination URL must be a complete http or https URL.")
    tourism_mode = str(values.tourism_mode or "limited").strip().lower()
    if tourism_mode not in TOURISM_MODES:
        raise LoveMyLocalsError("Tourism discovery must be LIMITED or INCLUDE.")
    explore_url = str(values.explore_url or "").strip()
    if explore_url:
        parsed = urlparse(explore_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise LoveMyLocalsError("Explore Tourism URL must be a complete http or https URL.")
    return LoveMyLocalsFormValues(
        locations, geography, bool(values.include_shorts), ticker, cta_type, cta_url,
        tourism_mode, bool(values.include_council_meetings), explore_url,
    )


def location_title(locations: Iterable[str], *, plaque: bool = False) -> str:
    separator = " + " if plaque else " • "
    return separator.join(str(item).strip().upper() for item in locations if str(item).strip())


def default_ticker(locations: Iterable[str]) -> str:
    names = " • ".join(str(item).strip().upper() for item in locations if str(item).strip())
    return f"LOVE MY LOCALS • {names} • PULL THE LEVER AND DISCOVER SOMETHING LOCAL •"


def resolved_locations(locations: Iterable[str], geography: str) -> list[str]:
    context = re.sub(r"\s+", " ", str(geography)).strip()
    return [f"{location}, {context}" for location in normalize_locations(locations)]


def _contains_location(text: str, location: str) -> bool:
    words = [re.escape(part) for part in re.findall(r"[\w'-]+", location, flags=re.UNICODE)]
    if not words:
        return False
    return bool(re.search(r"(?<!\w)" + r"[\s\W_]+".join(words) + r"(?!\w)", text, flags=re.I))


def qualify_metadata(
    title: str,
    description: str,
    tags: Iterable[str],
    locations: Iterable[str],
    channel_title: str = "",
) -> tuple[str, list[str], int] | None:
    tag_text = " ".join(str(tag) for tag in tags)
    best: tuple[str, list[str], int] | None = None
    for location in locations:
        bases: list[str] = []
        if _contains_location(title, location):
            bases.append("title")
        if _contains_location(description, location):
            bases.append("description")
        if _contains_location(tag_text, location):
            bases.append("tag")
        if _contains_location(channel_title, location):
            bases.append("channel")
        if not bases:
            continue
        score = max(MATCH_WEIGHTS[item] for item in bases)
        if best is None or score > best[2] or (score == best[2] and len(location) > len(best[0])):
            best = (location, bases, score)
    return best


@lru_cache(maxsize=256)
def _term_pattern(term: str) -> re.Pattern[str]:
    words = [re.escape(part) for part in re.findall(r"[\w'-]+", term, flags=re.UNICODE)]
    return re.compile(r"(?<!\w)" + r"[\s\W_]+".join(words) + r"(?!\w)", re.I)


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    return [term for term in terms if _term_pattern(term).search(text)]


def local_texture_analysis(
    title: str,
    description: str,
    tags: Iterable[str],
    channel_title: str = "",
) -> tuple[int, str, list[str]]:
    """Return a human/local-interest score independently of geography."""
    tag_text = " ".join(str(tag) for tag in tags)
    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}
    for content_type, terms in LOCAL_TEXTURE_TERMS.items():
        title_hits = _matched_terms(title, terms)
        description_hits = _matched_terms(description, terms)
        tag_hits = _matched_terms(tag_text, terms)
        channel_hits = _matched_terms(channel_title, terms)
        all_hits = list(dict.fromkeys((*title_hits, *description_hits, *tag_hits, *channel_hits)))
        score = min(24, len(title_hits) * 4 + len(description_hits) * 2 + len(tag_hits) + len(channel_hits))
        scores[content_type] = score
        evidence[content_type] = all_hits
    content_type = max(scores, key=lambda item: scores[item]) if scores else "OTHER / RANDOM LOCAL"
    if scores.get(content_type, 0) <= 0:
        content_type = "OTHER / RANDOM LOCAL"
    total = min(60, sum(sorted((value for value in scores.values() if value > 0), reverse=True)[:3]))
    return total, content_type, evidence.get(content_type, [])[:5]


def tourism_suppression_flags(title: str, description: str, tags: Iterable[str], channel_title: str = "") -> list[str]:
    metadata = " ".join((str(title), str(description), " ".join(str(tag) for tag in tags)))
    hits = TOURISM_PATTERN.findall(metadata)
    channel_is_tourism = bool(TOURISM_CHANNEL_PATTERN.search(str(channel_title or "")))
    historical = bool(HISTORICAL_CONTEXT_PATTERN.search(metadata))
    if historical and (hits or channel_is_tourism):
        return ["tourism:historical_context"]
    if channel_is_tourism or len(hits) >= 2:
        return ["tourism:high"]
    if hits:
        return ["tourism:medium"]
    return []


def council_meeting_suppression_reason(title: str, description: str, channel_title: str = "") -> str | None:
    combined = f"{title} {description} {channel_title}"
    return "council:administrative_meeting" if COUNCIL_MEETING_PATTERN.search(combined) else None


def discovery_queries_for_location(location: str, geography: str = DEFAULT_GEOGRAPHY) -> list[str]:
    """Build broad intent queries while keeping each API search quota-bounded."""
    place = re.sub(r"\s+", " ", str(location)).strip()
    context = re.sub(r"\s+", " ", str(geography)).strip()
    prefix = f'"{place}" {context}'.strip()
    queries = [prefix]
    for _intent, terms in DISCOVERY_QUERY_GROUPS:
        expression = "|".join(f'"{term}"' if " " in term else term for term in terms)
        queries.append(f"{prefix} {expression}")
    return queries


def real_estate_exclusion_reason(
    title: str,
    description: str,
    tags: Iterable[str],
    channel_title: str = "",
) -> str | None:
    """Identify sales/rental listings without blocking general property discussion."""
    metadata = " ".join((str(title), str(description), " ".join(str(tag) for tag in tags)))
    channel = str(channel_title or "")
    combined = f"{metadata} {channel}"
    if DIRECT_PROPERTY_LISTING_PATTERN.search(metadata):
        return "real_estate:direct_listing_language"

    property_context = bool(PROPERTY_CONTEXT_PATTERN.search(combined))
    agency_context = bool(PROPERTY_AGENCY_PATTERN.search(channel)) or bool(
        re.search(r"\breal[ -]?estate\s+agent\b", metadata, flags=re.I)
    )
    sales_context = bool(PROPERTY_SALES_PATTERN.search(metadata))
    tour_context = bool(PROPERTY_TOUR_PATTERN.search(metadata))
    address_context = bool(STREET_ADDRESS_PATTERN.search(metadata))
    specification_count = len(PROPERTY_SPEC_PATTERN.findall(metadata))
    price_context = bool(PROPERTY_PRICE_PATTERN.search(metadata))

    if address_context and specification_count >= 2:
        return "real_estate:address_and_property_specifications"
    if address_context and sales_context:
        return "real_estate:address_and_sales_context"
    if agency_context and (sales_context or tour_context) and (address_context or specification_count or price_context):
        return "real_estate:agency_listing_context"
    if property_context and tour_context and (sales_context or address_context or specification_count or agency_context):
        return "real_estate:sales_walkthrough"
    listing_signals = sum((sales_context, tour_context, address_context, specification_count >= 1, price_context, agency_context))
    if property_context and listing_signals >= 2:
        return "real_estate:property_sales_context"
    return None


def _is_short(item: dict) -> bool:
    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
    duration = parse_duration(str(item.get("contentDetails", {}).get("duration") or ""))
    _, ratio = best_thumbnail(snippet)
    title = str(snippet.get("title") or "")
    return bool((duration and duration <= 60) or "#shorts" in title.casefold() or (ratio and ratio < 0.9))


def _duplicate_signature(video: Video) -> tuple[str, str, int]:
    title = re.sub(r"\W+", " ", video.title.casefold()).strip()
    return title, video.channel_title.casefold(), round(video.duration_seconds / 5) if video.duration_seconds else 0


def _candidate_quality(item: LoveMyLocalsCandidate) -> int:
    penalty = 0
    if "tourism:high" in item.suppression_flags:
        penalty += 24
    elif "tourism:medium" in item.suppression_flags:
        penalty += 12
    if "promotion:generic" in item.suppression_flags:
        penalty += 8
    if "council:administrative_meeting" in item.suppression_flags:
        penalty += 20
    return item.relevance_score * 20 + item.local_texture_score - penalty


def _prioritise(
    candidates: list[LoveMyLocalsCandidate],
    target: int,
    rng: random.Random,
    *,
    locations: Iterable[str],
    tourism_mode: str = "limited",
) -> tuple[list[LoveMyLocalsCandidate], dict[str, int]]:
    """Greedily balance quality, topic, place and publisher before shuffling."""
    selected: list[LoveMyLocalsCandidate] = []
    remaining = list(candidates)
    channel_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    location_counts: dict[str, int] = {}
    channel_skips: set[str] = set()
    tourism_skips: set[str] = set()
    location_list = list(locations)
    category_targets = {
        "PEOPLE / INTERVIEWS": 10,
        "NEWS": 6,
        "MUSIC / PERFORMANCE": 8,
        "COMMUNITY / CLUBS / SPORT": 6,
        "HISTORY / ARCHIVE": 5,
        "BUSINESS / PUB / FOOD / MAKERS": 5,
    }
    location_target = max(1, target // max(2, len(location_list) * 2))

    def choose(channel_limit: int, tourism_limit: int | None) -> LoveMyLocalsCandidate | None:
        eligible: list[tuple[float, LoveMyLocalsCandidate]] = []
        tourism_count = sum(
            bool({"tourism:high", "tourism:medium"} & set(item.suppression_flags)) for item in selected
        )
        for item in remaining:
            channel_key = item.video.channel_id or item.video.channel_title.casefold()
            if channel_counts.get(channel_key, 0) >= channel_limit:
                channel_skips.add(item.video.video_id)
                continue
            is_tourism = bool({"tourism:high", "tourism:medium"} & set(item.suppression_flags))
            if tourism_limit is not None and is_tourism and tourism_count >= tourism_limit:
                tourism_skips.add(item.video.video_id)
                continue
            category_gap = max(0, category_targets.get(item.content_type, 0) - category_counts.get(item.content_type, 0))
            place_gap = max(0, location_target - location_counts.get(item.matched_location, 0))
            score = _candidate_quality(item) + min(28, category_gap * 4) + min(18, place_gap * 3)
            eligible.append((score + rng.random() * 2.5, item))
        return max(eligible, key=lambda value: value[0])[1] if eligible else None

    tourism_limit = 1 if tourism_mode == "limited" else 3
    while remaining and len(selected) < target:
        item = choose(3, tourism_limit)
        if item is None:
            # Only relax publisher/tourism caps when alternatives cannot fill the machine.
            item = choose(5, tourism_limit)
        if item is None:
            item = choose(8, None)
        if item is None:
            break
        remaining.remove(item)
        selected.append(item)
        channel_key = item.video.channel_id or item.video.channel_title.casefold()
        channel_counts[channel_key] = channel_counts.get(channel_key, 0) + 1
        category_counts[item.content_type] = category_counts.get(item.content_type, 0) + 1
        location_counts[item.matched_location] = location_counts.get(item.matched_location, 0) + 1
    rng.shuffle(selected)
    selected_ids = {item.video.video_id for item in selected}
    tourism_suppressed = sum(
        item.video.video_id not in selected_ids
        and (item.content_type == "TOURISM" or bool({"tourism:high", "tourism:medium"} & set(item.suppression_flags)))
        for item in candidates
    )
    return selected[:target], {
        "channel_diversity_removals": len(channel_skips - selected_ids),
        "tourism_suppressed": max(tourism_suppressed, len(tourism_skips - selected_ids)),
    }


class LoveMyLocalsDiscoveryService:
    def __init__(self, client: YouTubeClient, *, rng: random.Random | None = None) -> None:
        self.client = client
        self.rng = rng or random.SystemRandom()

    def discover(
        self,
        locations: Iterable[str],
        geography: str = DEFAULT_GEOGRAPHY,
        *,
        include_shorts: bool = False,
        tourism_mode: str = "limited",
        include_council_meetings: bool = False,
        default_cta_type: PrimaryCtaType | str = PrimaryCtaType.VISIT_WEBSITE,
        default_cta_url: str | None = None,
        target: int = MAX_LOVE_MY_LOCALS_VIDEOS,
    ) -> LoveMyLocalsConfig:
        names = normalize_locations(locations)
        tourism_mode = str(tourism_mode or "limited").strip().lower()
        if tourism_mode not in TOURISM_MODES:
            raise LoveMyLocalsError("Tourism discovery must be LIMITED or INCLUDE.")
        resolved = resolved_locations(names, geography)
        raw_items: list[dict] = []
        queries: list[str] = []
        for name in names:
            queries.extend(discovery_queries_for_location(name, geography))
        for query in queries:
            try:
                raw_items.extend(self.client.search_video_items(query, maximum=20))
            except YouTubeError:
                raise
            except Exception as error:
                raise LoveMyLocalsError("Love My Locals could not complete the YouTube search.") from error

        qualified: list[LoveMyLocalsCandidate] = []
        exclusion_diagnostics: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        seen_signatures: set[tuple[str, str, int]] = set()
        duplicate_count = 0
        unavailable_count = 0
        unqualified_count = 0
        spam_count = 0
        shorts_excluded_count = 0
        for item in raw_items:
            record = self.client._video_record(item)
            if not record:
                unavailable_count += 1
                continue
            if record.video_id in seen_ids:
                duplicate_count += 1
                continue
            seen_ids.add(record.video_id)
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            description = html.unescape(str(snippet.get("description") or "")).strip()
            tags = [html.unescape(str(tag)).strip() for tag in (snippet.get("tags") or []) if str(tag).strip()]
            qualification = qualify_metadata(record.title, description, tags, names, record.channel_title)
            if qualification is None:
                unqualified_count += 1
                continue
            if SPAM_PATTERN.search(f"{record.title} {description}"):
                spam_count += 1
                continue
            exclusion_reason = real_estate_exclusion_reason(
                record.title,
                description,
                tags,
                record.channel_title,
            )
            if exclusion_reason:
                exclusion_diagnostics.append({
                    "video_id": record.video_id,
                    "title": record.title,
                    "reason": exclusion_reason,
                })
                continue
            council_reason = council_meeting_suppression_reason(record.title, description, record.channel_title)
            if council_reason and not include_council_meetings:
                exclusion_diagnostics.append({
                    "video_id": record.video_id,
                    "title": record.title,
                    "reason": council_reason,
                })
                continue
            short = _is_short(item)
            if short and not include_shorts:
                shorts_excluded_count += 1
                continue
            signature = _duplicate_signature(record)
            if signature in seen_signatures:
                duplicate_count += 1
                continue
            matched_location, match_basis, score = qualification
            texture_score, content_type, texture_evidence = local_texture_analysis(
                record.title, description, tags, record.channel_title,
            )
            suppression_flags = tourism_suppression_flags(record.title, description, tags, record.channel_title)
            if council_reason:
                suppression_flags.append(council_reason)
            if GENERIC_PROMO_PATTERN.search(f"{record.title} {description}") and texture_score < 10:
                suppression_flags.append("promotion:generic")
            if {"tourism:high", "tourism:medium"} & set(suppression_flags) and not texture_evidence:
                content_type = "TOURISM"
            reason = f"{' + '.join(match_basis).upper()} MATCH: {matched_location}"
            if texture_evidence:
                reason += f"; {content_type}: {', '.join(texture_evidence)}"
            seen_signatures.add(signature)
            qualified.append(LoveMyLocalsCandidate(
                video=record,
                description=description,
                tags=tags,
                matched_location=matched_location,
                match_basis=match_basis,
                relevance_score=score,
                content_type=content_type,
                local_texture_score=texture_score,
                suppression_flags=suppression_flags,
                qualification_reason=reason,
                is_short=short,
                cta_type=default_cta_type,
                cta_url=default_cta_url,
                active=False,
            ))
            if len(qualified) >= MAX_LOVE_MY_LOCALS_CANDIDATES:
                break
        selected, selection_summary = _prioritise(
            qualified,
            min(MAX_LOVE_MY_LOCALS_VIDEOS, max(1, target)),
            self.rng,
            locations=names,
            tourism_mode=tourism_mode,
        )
        selected_ids = {item.video.video_id for item in selected}
        for item in qualified:
            item.active = item.video.video_id in selected_ids
        selected_order = {item.video.video_id: index for index, item in enumerate(selected)}
        qualified.sort(key=lambda item: (0 if item.active else 1, selected_order.get(item.video.video_id, 9999)))
        return LoveMyLocalsConfig(
            locations=names,
            resolved_geography=geography,
            resolved_locations=resolved,
            include_shorts=include_shorts,
            tourism_mode=tourism_mode,
            include_council_meetings=include_council_meetings,
            candidates=qualified,
            default_cta_type=default_cta_type,
            default_cta_url=default_cta_url,
            exclusion_diagnostics=exclusion_diagnostics,
            discovery_summary={
                "queries_run": len(queries),
                "raw_results": len(raw_items),
                "unique_results": len(seen_ids),
                "qualified_candidates": len(qualified),
                "excluded": (
                    len(exclusion_diagnostics) + unavailable_count + unqualified_count
                    + spam_count + shorts_excluded_count
                ),
                "unavailable_excluded": unavailable_count,
                "location_unqualified": unqualified_count,
                "spam_excluded": spam_count,
                "shorts_excluded": shorts_excluded_count,
                "real_estate_excluded": sum(item["reason"].startswith("real_estate:") for item in exclusion_diagnostics),
                "council_meetings_excluded": sum(item["reason"].startswith("council:") for item in exclusion_diagnostics),
                "duplicates_removed": duplicate_count,
                "tourism_suppressed": selection_summary["tourism_suppressed"],
                "channel_diversity_removals": selection_summary["channel_diversity_removals"],
                "final_videos": len(selected),
            },
            last_search_at=utc_now(),
        )


def discovery_quality_report(config: LoveMyLocalsConfig) -> dict[str, int]:
    report = {content_type: 0 for content_type in CONTENT_TYPES}
    for item in config.candidates:
        if item.active:
            report[item.content_type] = report.get(item.content_type, 0) + 1
    report["REAL ESTATE"] = 0
    report.update(config.discovery_summary)
    return report


def remove_candidate(config: LoveMyLocalsConfig, video_id: str) -> bool:
    for item in config.candidates:
        if item.video.video_id == video_id and item.active:
            item.active = False
            return True
    return False


def replace_candidate(config: LoveMyLocalsConfig, video_id: str, *, rng: random.Random | None = None) -> LoveMyLocalsCandidate | None:
    remove_candidate(config, video_id)
    available = [item for item in config.candidates if not item.active and item.video.video_id != video_id]
    if not available:
        return None
    active_channel_counts: dict[str, int] = {}
    for item in config.candidates:
        if item.active:
            key = item.video.channel_id or item.video.channel_title.casefold()
            active_channel_counts[key] = active_channel_counts.get(key, 0) + 1
    diverse = [
        item for item in available
        if active_channel_counts.get(item.video.channel_id or item.video.channel_title.casefold(), 0) < 3
    ] or available
    best_score = max(_candidate_quality(item) for item in diverse)
    best = [item for item in diverse if _candidate_quality(item) == best_score]
    replacement = (rng or random.SystemRandom()).choice(best)
    replacement.active = True
    return replacement


def assemble_project(
    values: LoveMyLocalsFormValues,
    config: LoveMyLocalsConfig,
    slug: str,
    *,
    existing: Project | None = None,
) -> Project:
    validated = validate_form(values)
    if [item.casefold() for item in validated.locations] != [item.casefold() for item in config.locations]:
        raise LoveMyLocalsError("The reviewed discovery results do not match the current location fields. Search again before building.")
    if validated.geography.casefold() != config.resolved_geography.casefold():
        raise LoveMyLocalsError("The reviewed discovery results do not match the current geographic context. Search again before building.")
    if validated.include_shorts != config.include_shorts:
        raise LoveMyLocalsError("The YouTube Shorts setting changed after discovery. Search again before building.")
    if validated.tourism_mode != config.tourism_mode:
        raise LoveMyLocalsError("The tourism discovery setting changed after discovery. Search again before building.")
    if validated.include_council_meetings != config.include_council_meetings:
        raise LoveMyLocalsError("The council-meeting setting changed after discovery. Search again before building.")
    previous_type = config.default_cta_type
    previous_url = config.default_cta_url
    for item in config.candidates:
        uses_previous_default = item.cta_type == previous_type and item.cta_url == previous_url
        if not item.cta_url or uses_previous_default:
            item.cta_type = validated.default_cta_type
            item.cta_url = validated.default_cta_url or None
            item.__post_init__()
    config.default_cta_type = validated.default_cta_type
    config.default_cta_url = validated.default_cta_url or None
    config.explore_url = validated.explore_url or None
    config.__post_init__()
    if not config.selected_videos:
        raise LoveMyLocalsError("No active local videos are available to build this machine.")
    if existing and existing.project_type is not ProjectType.LOVE_MY_LOCALS:
        raise LoveMyLocalsError("An existing project cannot change project type.")
    changes_pending = bool(existing and existing.published_url)
    excluded = [item.video.video_id for item in config.candidates if not item.active]
    active = config.selected_videos
    return Project(
        slug=existing.slug if existing else slug,
        title=location_title(validated.locations),
        ticker_text=validated.ticker_text,
        channel_url="",
        channel_id="",
        channel_title="Love My Locals",
        channel_thumbnail=active[0].thumbnail_url if active else "",
        id=existing.id if existing else str(uuid4()),
        project_type=ProjectType.LOVE_MY_LOCALS,
        channel_master_config=ChannelMasterConfig(palette="MIDNIGHT"),
        love_my_locals_config=config,
        excluded_video_ids=excluded,
        videos=[item.video for item in config.candidates],
        status="changes_pending" if changes_pending else "draft",
        created_at=existing.created_at if existing else utc_now(),
        published_at=existing.published_at if existing else None,
        published_url=existing.published_url if existing else None,
        delivery_status=existing.delivery_status if changes_pending and existing else "not_requested",
        publication_revision=existing.publication_revision if existing else None,
        delivery_record=existing.delivery_record if existing else None,
        publication_operation=existing.publication_operation if existing else None,
    )


def catalogue_for(config: LoveMyLocalsConfig) -> ChannelCatalogue:
    videos = config.selected_videos
    return ChannelCatalogue(
        channel_id="",
        channel_title="Love My Locals",
        channel_url="",
        channel_thumbnail=videos[0].thumbnail_url if videos else "",
        videos=videos,
    )
