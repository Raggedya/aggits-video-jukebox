from __future__ import annotations

import html
import random
import re
from dataclasses import dataclass, field
from typing import Iterable
from uuid import uuid4

from .config import MAX_LOVE_MY_LOCALS_CANDIDATES, MAX_LOVE_MY_LOCALS_VIDEOS
from .models import (
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
MATCH_WEIGHTS = {"title": 3, "description": 2, "tag": 1}
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

    def comparable(self) -> tuple[object, ...]:
        return (
            tuple(self.locations),
            self.geography,
            bool(self.include_shorts),
            self.ticker_text,
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
    return LoveMyLocalsFormValues(locations, geography, bool(values.include_shorts), ticker)


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


def qualify_metadata(title: str, description: str, tags: Iterable[str], locations: Iterable[str]) -> tuple[str, list[str], int] | None:
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
        if not bases:
            continue
        score = max(MATCH_WEIGHTS[item] for item in bases)
        if best is None or score > best[2]:
            best = (location, bases, score)
    return best


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


def _prioritise(candidates: list[LoveMyLocalsCandidate], target: int, rng: random.Random) -> list[LoveMyLocalsCandidate]:
    selected: list[LoveMyLocalsCandidate] = []
    deferred: list[LoveMyLocalsCandidate] = []
    channel_counts: dict[str, int] = {}
    for score in (3, 2, 1):
        group = [item for item in candidates if item.relevance_score == score]
        rng.shuffle(group)
        for item in group:
            channel_key = item.video.channel_id or item.video.channel_title.casefold()
            if channel_counts.get(channel_key, 0) >= 3:
                deferred.append(item)
                continue
            selected.append(item)
            channel_counts[channel_key] = channel_counts.get(channel_key, 0) + 1
            if len(selected) >= target:
                rng.shuffle(selected)
                return selected
    rng.shuffle(deferred)
    selected.extend(deferred[: max(0, target - len(selected))])
    rng.shuffle(selected)
    return selected[:target]


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
        target: int = MAX_LOVE_MY_LOCALS_VIDEOS,
    ) -> LoveMyLocalsConfig:
        names = normalize_locations(locations)
        resolved = resolved_locations(names, geography)
        raw_items: list[dict] = []
        for query in resolved:
            try:
                raw_items.extend(self.client.search_video_items(f'"{query}"', maximum=75))
            except YouTubeError:
                raise
            except Exception as error:
                raise LoveMyLocalsError("Love My Locals could not complete the YouTube search.") from error

        qualified: list[LoveMyLocalsCandidate] = []
        exclusion_diagnostics: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        seen_signatures: set[tuple[str, str, int]] = set()
        for item in raw_items:
            record = self.client._video_record(item)
            if not record or record.video_id in seen_ids:
                continue
            seen_ids.add(record.video_id)
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            description = html.unescape(str(snippet.get("description") or "")).strip()
            tags = [html.unescape(str(tag)).strip() for tag in (snippet.get("tags") or []) if str(tag).strip()]
            qualification = qualify_metadata(record.title, description, tags, names)
            if qualification is None or SPAM_PATTERN.search(f"{record.title} {description}"):
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
            short = _is_short(item)
            if short and not include_shorts:
                continue
            signature = _duplicate_signature(record)
            if signature in seen_signatures:
                continue
            matched_location, match_basis, score = qualification
            seen_signatures.add(signature)
            qualified.append(LoveMyLocalsCandidate(
                video=record,
                description=description,
                tags=tags,
                matched_location=matched_location,
                match_basis=match_basis,
                relevance_score=score,
                is_short=short,
                cta_type=PrimaryCtaType.VISIT_WEBSITE,
                cta_url=None,
                active=False,
            ))
            if len(qualified) >= MAX_LOVE_MY_LOCALS_CANDIDATES:
                break
        selected = _prioritise(qualified, min(MAX_LOVE_MY_LOCALS_VIDEOS, max(1, target)), self.rng)
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
            candidates=qualified,
            exclusion_diagnostics=exclusion_diagnostics,
            last_search_at=utc_now(),
        )


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
    best_score = max(item.relevance_score for item in available)
    best = [item for item in available if item.relevance_score == best_score]
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
