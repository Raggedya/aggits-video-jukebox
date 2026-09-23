from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlparse, urlunparse
from uuid import UUID, uuid4

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_H

from .config import MAX_CHANNEL_MASTER_REVIEW_VIDEOS, resource_path
from .models import (
    CHANNEL_MASTER_PALETTES,
    PRIMARY_CTA_LABELS,
    ChannelMasterConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    utc_now,
)
from .site_builder import build_project_site
from .store import ProjectStore, slugify
from .youtube_api import ChannelCatalogue


MAX_CAMPAIGN_CANDIDATES = 20
CAMPAIGN_SCHEMA_VERSION = 1
CAMPAIGN_EMAIL_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_PALETTE = "MIDNIGHT"
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")

CAMPAIGN_STATES = frozenset({
    "DRAFT", "RESEARCHED", "CANDIDATES_APPROVED", "BUILDING", "BUILT",
    "UNDER_REVIEW", "APPROVED_TO_PUBLISH", "PUBLISHING", "PUBLISHED",
    "PACKAGE_CREATED", "EMAILED", "PARTIAL_FAILURE", "ARCHIVED",
})
BUILD_STATES = frozenset({"PENDING", "BUILDING", "BUILT", "WARNING", "FAILED"})
REVIEW_STATES = frozenset({"PENDING", "BUILT", "REVIEWED", "APPROVED TO PUBLISH", "REJECTED-HOLD"})
PUBLISH_STATES = frozenset({"PENDING", "APPROVED TO PUBLISH", "PUBLISHING", "PUBLISHED", "FAILED", "HOLD"})
PROSPECT_STATES = frozenset({
    "RESEARCHED", "APPROVED", "BUILT", "REVIEWED", "PUBLISHED",
    "CONTACTED", "REPLIED", "INTERESTED", "DECLINED", "HOLD",
})
OWNERSHIP_STATES = frozenset({"VERIFIED", "LIKELY", "REVIEW REQUIRED"})
VIDEO_COUNT_STATES = frozenset({"VERIFIED", "APPROXIMATE", "UNKNOWN"})
CONFIDENCE_STATES = frozenset({"HIGH", "MEDIUM", "REVIEW REQUIRED"})


class CampaignError(ValueError):
    pass


class ResearchUnavailableError(CampaignError):
    pass


def _clean_text(value: object, *, limit: int = 1500) -> str:
    text = str(value or "").replace("\x00", "").strip()
    if any(ord(character) < 32 and character not in "\t\n\r" for character in text):
        raise CampaignError("Control characters are not allowed.")
    if len(text) > limit:
        raise CampaignError(f"Text cannot exceed {limit} characters.")
    return text


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    cleaned = str(value or "").strip().lower()
    if cleaned in {"1", "true", "yes", "y", "approved"}:
        return True
    if cleaned in {"", "0", "false", "no", "n", "pending"}:
        return False
    raise CampaignError(f"Expected YES or NO, not {value!r}.")


def _public_http_url(value: object, label: str, *, required: bool = False) -> str:
    cleaned = _clean_text(value, limit=2048)
    if not cleaned and not required:
        return ""
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise CampaignError(f"{label} must be a complete public http or https URL.")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise CampaignError(f"{label} cannot point to a local address.")
    if re.fullmatch(r"(?:127|10)\..+|192\.168\..+|172\.(?:1[6-9]|2\d|3[01])\..+|0\.0\.0\.0", host):
        raise CampaignError(f"{label} cannot point to a private address.")
    return cleaned


def canonical_youtube_channel_url(value: object) -> str:
    cleaned = _public_http_url(value, "YouTube channel URL", required=True)
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host not in {"youtube.com", "m.youtube.com"}:
        raise CampaignError("YouTube channel URL must use youtube.com.")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments or not (segments[0].startswith("@") or (segments[0] in {"channel", "c", "user"} and len(segments) >= 2)):
        raise CampaignError("Use a recognizable YouTube channel or @handle URL.")
    path = "/" + "/".join(segments[:2] if segments[0] in {"channel", "c", "user"} else segments[:1])
    return urlunparse(("https", "www.youtube.com", path.rstrip("/"), "", "", ""))


def _cta_type(value: object) -> PrimaryCtaType:
    cleaned = _clean_text(value, limit=60)
    if not cleaned:
        raise CampaignError("Primary CTA type is required before build.")
    normalized = cleaned.lower().replace("'", "").replace(" ", "_").replace("-", "_")
    label_map = {label.upper(): cta for cta, label in PRIMARY_CTA_LABELS.items()}
    if cleaned.upper() in label_map:
        return label_map[cleaned.upper()]
    aliases = {"buy_on_bandcamp": PrimaryCtaType.BANDCAMP, "listen_on_spotify": PrimaryCtaType.SPOTIFY, "get_tickets": PrimaryCtaType.TICKETS}
    try:
        return aliases.get(normalized) or PrimaryCtaType(normalized)
    except ValueError as error:
        raise CampaignError(f"Unsupported Channel Master CTA: {cleaned}.") from error


def _csv_safe(value: object) -> str:
    cleaned = str(value or "")
    if cleaned.lstrip().startswith(CSV_FORMULA_PREFIXES):
        return "'" + cleaned
    return cleaned


@dataclass(slots=True)
class CampaignCandidate:
    candidate_number: int
    organisation_name: str = ""
    location: str = ""
    website_url: str = ""
    youtube_channel_url: str = ""
    youtube_video_count: int | None = None
    video_count_status: str = "UNKNOWN"
    youtube_ownership_status: str = "REVIEW REQUIRED"
    qualification_status: str = "REVIEW REQUIRED"
    qualification_notes: str = ""
    research_sources: list[str] = field(default_factory=list)
    research_date: str = ""
    research_confidence: str = "REVIEW REQUIRED"
    primary_cta_type: str = ""
    primary_cta_label: str = ""
    primary_cta_url: str = ""
    primary_cta_url_status: str = "REVIEW REQUIRED"
    cta_reason: str = ""
    contact_url: str = ""
    ticker_mode: str = "TITLE ONLY"
    ticker_text: str = ""
    palette_mode: str = "CHANNEL MASTER DEFAULT"
    palette_primary: str = ""
    palette_accent: str = ""
    approved_for_build: bool = False
    build_status: str = "PENDING"
    review_status: str = "PENDING"
    publish_status: str = "PENDING"
    prospect_status: str = "RESEARCHED"
    project_uuid: str = ""
    project_slug: str = ""
    public_url: str = ""
    qr_path: str = ""
    prospect_card_status: str = "NOT_READY"
    prospect_card_path: str = ""
    prospect_card_template_version: str = ""
    error_message: str = ""
    operator_notes: str = ""
    approved_at: str = ""
    built_at: str = ""
    published_at: str = ""
    contacted_at: str = ""

    def __post_init__(self) -> None:
        self.candidate_number = int(self.candidate_number)
        if not 1 <= self.candidate_number <= 999:
            raise CampaignError("Candidate number must be between 1 and 999.")
        self.organisation_name = _clean_text(self.organisation_name, limit=120)
        self.location = _clean_text(self.location, limit=120)
        self.ticker_text = _clean_text(self.ticker_text, limit=1500)
        self.qualification_notes = _clean_text(self.qualification_notes, limit=2000)
        self.cta_reason = _clean_text(self.cta_reason, limit=800)
        self.operator_notes = _clean_text(self.operator_notes, limit=2000)
        self.research_sources = [_public_http_url(item, "Research source") for item in self.research_sources if str(item).strip()]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CampaignCandidate":
        known = {item.name for item in fields(cls)}
        data = {key: item for key, item in value.items() if key in known}
        data["approved_for_build"] = _bool(data.get("approved_for_build"))
        count = data.get("youtube_video_count")
        data["youtube_video_count"] = int(count) if str(count or "").strip() else None
        sources = data.get("research_sources", [])
        if isinstance(sources, str):
            data["research_sources"] = [part.strip() for part in sources.split("|") if part.strip()]
        return cls(**data)


@dataclass(slots=True)
class Campaign:
    campaign_name: str
    theme: str
    location: str
    target_count: int = MAX_CAMPAIGN_CANDIDATES
    campaign_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "DRAFT"
    candidates: list[CampaignCandidate] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    researched_at: str = ""
    package_created_at: str = ""
    package_path: str = ""
    email_status: str = "NOT READY"
    emailed_at: str = ""
    email_idempotency_key: str = ""
    archived: bool = False
    schema_version: int = CAMPAIGN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            self.campaign_id = str(UUID(str(self.campaign_id)))
        except (ValueError, TypeError, AttributeError) as error:
            raise CampaignError("Campaign ID must be a valid UUID.") from error
        self.campaign_name = _clean_text(self.campaign_name, limit=120)
        self.theme = _clean_text(self.theme, limit=120)
        self.location = _clean_text(self.location, limit=120)
        self.target_count = int(self.target_count)
        if not 1 <= self.target_count <= MAX_CAMPAIGN_CANDIDATES:
            raise CampaignError("A campaign target must be between 1 and 20.")
        if self.status not in CAMPAIGN_STATES:
            raise CampaignError(f"Unsupported campaign status: {self.status}.")
        numbers = [item.candidate_number for item in self.candidates]
        if len(numbers) != len(set(numbers)):
            raise CampaignError("Candidate numbers must be unique within a campaign.")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["schema_version"] = CAMPAIGN_SCHEMA_VERSION
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Campaign":
        data = dict(value)
        data["candidates"] = [CampaignCandidate.from_dict(item) for item in value.get("candidates", []) if isinstance(item, dict)]
        data.pop("schemaVersion", None)
        return cls(**{key: item for key, item in data.items() if key in {field_.name for field_ in fields(cls)}})

    def counts(self) -> dict[str, int]:
        return {
            "candidates": len(self.candidates),
            "approved": sum(item.approved_for_build for item in self.candidates),
            "built": sum(item.build_status == "BUILT" for item in self.candidates),
            "published": sum(item.publish_status == "PUBLISHED" for item in self.candidates),
            "failed": sum(item.build_status == "FAILED" or item.publish_status == "FAILED" for item in self.candidates),
        }


class CampaignStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.campaigns_dir = self.root / "campaigns"
        self.campaigns_dir.mkdir(parents=True, exist_ok=True)

    def campaign_dir(self, campaign_id: str) -> Path:
        try:
            safe = str(UUID(str(campaign_id)))
        except (ValueError, TypeError, AttributeError) as error:
            raise CampaignError("Unsafe campaign identifier.") from error
        candidate = (self.campaigns_dir / safe).resolve()
        if candidate.parent != self.campaigns_dir.resolve():
            raise CampaignError("Unsafe campaign path.")
        return candidate

    def output_dir(self, campaign: Campaign) -> Path:
        return self.campaign_dir(campaign.campaign_id) / "output"

    def save(self, campaign: Campaign) -> None:
        campaign.updated_at = utc_now()
        directory = self.campaign_dir(campaign.campaign_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "campaign.json"
        temporary = directory / ".campaign.json.tmp"
        temporary.write_text(json.dumps(campaign.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)

    def load(self, campaign_id: str) -> Campaign:
        source = self.campaign_dir(campaign_id) / "campaign.json"
        return Campaign.from_dict(json.loads(source.read_text(encoding="utf-8")))

    def list(self, *, include_archived: bool = False) -> list[Campaign]:
        campaigns: list[Campaign] = []
        for source in self.campaigns_dir.glob("*/campaign.json"):
            try:
                campaign = Campaign.from_dict(json.loads(source.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                continue
            if include_archived or not campaign.archived:
                campaigns.append(campaign)
        return sorted(campaigns, key=lambda item: item.updated_at, reverse=True)

    def archive(self, campaign: Campaign) -> None:
        campaign.archived = True
        campaign.status = "ARCHIVED"
        self.save(campaign)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    candidate_number: int
    severity: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class CampaignValidation:
    valid: int
    warnings: int
    blocked: int
    issues: tuple[ValidationIssue, ...]


class CampaignCsvService:
    FIELDS = (
        "campaign_id", "campaign_name", "theme", "location", "candidate_number", "organisation_name",
        "website_url", "youtube_channel_url", "youtube_video_count", "video_count_status",
        "youtube_ownership_status", "qualification_status", "qualification_notes", "research_sources",
        "research_date", "research_confidence", "primary_cta_type", "primary_cta_label", "primary_cta_url",
        "primary_cta_url_status", "cta_reason", "contact_url", "ticker_mode", "ticker_text", "palette_mode",
        "palette_primary", "palette_accent", "approved_for_build", "build_status", "review_status",
        "publish_status", "prospect_status", "project_uuid", "project_slug", "public_url", "qr_path",
        "prospect_card_status", "prospect_card_path", "prospect_card_template_version",
        "error_message", "operator_notes", "approved_at", "built_at", "published_at", "contacted_at",
    )

    @classmethod
    def export(cls, campaign: Campaign, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=cls.FIELDS, extrasaction="ignore")
            writer.writeheader()
            for candidate in campaign.candidates:
                row = candidate.to_dict()
                row.update({
                    "campaign_id": campaign.campaign_id,
                    "campaign_name": campaign.campaign_name,
                    "theme": campaign.theme,
                    "location": campaign.location,
                    "approved_for_build": "YES" if candidate.approved_for_build else "NO",
                    "research_sources": "|".join(candidate.research_sources),
                })
                writer.writerow({key: _csv_safe(row.get(key, "")) for key in cls.FIELDS})
        return destination

    @classmethod
    def template(cls, destination: Path) -> Path:
        example = Campaign(
            campaign_name="Fictional Museums - Example City", theme="Museums", location="Example City", target_count=1,
            candidates=[CampaignCandidate(
                candidate_number=1, organisation_name="Example Heritage Museum", location="Example City",
                website_url="https://example.com/museum", youtube_channel_url="https://www.youtube.com/@ExampleMuseum",
                youtube_video_count=42, video_count_status="APPROXIMATE", youtube_ownership_status="LIKELY",
                qualification_status="REVIEW REQUIRED", qualification_notes="Fictional template row — replace before use.",
                research_confidence="REVIEW REQUIRED", primary_cta_type="VISIT WEBSITE",
                primary_cta_url="https://example.com/museum", primary_cta_url_status="REVIEW REQUIRED",
                contact_url="https://example.com/museum/contact", approved_for_build=False,
            )],
        )
        return cls.export(example, destination)

    @classmethod
    def import_file(cls, source: Path) -> Campaign:
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            missing = [field for field in ("campaign_id", "campaign_name", "theme", "location", "candidate_number", "organisation_name", "youtube_channel_url", "approved_for_build") if field not in (reader.fieldnames or [])]
            if missing:
                raise CampaignError("Campaign CSV is missing required columns: " + ", ".join(missing))
            rows = list(reader)
        if not rows:
            raise CampaignError("Campaign CSV contains no candidate rows.")
        if len(rows) > 200:
            raise CampaignError("Campaign CSV cannot contain more than 200 candidate records.")
        identity = {(row.get("campaign_id", "").strip(), row.get("campaign_name", "").strip(), row.get("theme", "").strip(), row.get("location", "").strip()) for row in rows}
        if len(identity) != 1:
            raise CampaignError("Every CSV row must use the same campaign identity and settings.")
        campaign_id, name, theme, location = identity.pop()
        candidates: list[CampaignCandidate] = []
        candidate_fields = {item.name for item in fields(CampaignCandidate)}
        for row in rows:
            if any(str(value or "").lstrip().startswith(CSV_FORMULA_PREFIXES) for value in row.values()):
                raise CampaignError(f"Candidate {row.get('candidate_number') or '?'} contains an unsafe spreadsheet formula prefix.")
            candidate = CampaignCandidate.from_dict({key: value for key, value in row.items() if key in candidate_fields})
            candidates.append(candidate)
        return Campaign(
            campaign_id=campaign_id or str(uuid4()), campaign_name=name, theme=theme, location=location,
            target_count=min(MAX_CAMPAIGN_CANDIDATES, max(1, sum(item.approved_for_build for item in candidates) or min(len(candidates), MAX_CAMPAIGN_CANDIDATES))),
            candidates=candidates,
        )

    @classmethod
    def validate(cls, campaign: Campaign, existing_projects: list[Project] | None = None) -> CampaignValidation:
        issues: list[ValidationIssue] = []
        seen_channels: dict[str, int] = {}
        existing = {}
        for project in existing_projects or []:
            if project.project_type is ProjectType.CHANNEL_MASTER:
                try:
                    existing[canonical_youtube_channel_url(project.source_channel_url or project.channel_url)] = project.slug
                except CampaignError:
                    pass
        approved = [item for item in campaign.candidates if item.approved_for_build]
        if len(approved) > MAX_CAMPAIGN_CANDIDATES:
            for item in approved[MAX_CAMPAIGN_CANDIDATES:]:
                issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "approved_for_build", "No more than 20 candidates may be approved for build."))
        for item in campaign.candidates:
            before = len(issues)
            if not item.organisation_name:
                issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "organisation_name", "Organisation name is required."))
            try:
                channel = canonical_youtube_channel_url(item.youtube_channel_url)
            except CampaignError as error:
                issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "youtube_channel_url", str(error)))
                channel = ""
            if channel:
                if channel in seen_channels:
                    issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "youtube_channel_url", f"Duplicates candidate {seen_channels[channel]:02d}."))
                else:
                    seen_channels[channel] = item.candidate_number
                if channel in existing and not item.project_uuid:
                    issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "youtube_channel_url", f"Existing Channel Master project detected: {existing[channel]}. Review and use the existing project."))
            for field_name, label in (("website_url", "Website URL"), ("contact_url", "Contact URL")):
                try:
                    _public_http_url(getattr(item, field_name), label)
                except CampaignError as error:
                    issues.append(ValidationIssue(item.candidate_number, "BLOCKED", field_name, str(error)))
            if item.approved_for_build:
                try:
                    cta = _cta_type(item.primary_cta_type)
                    if cta is PrimaryCtaType.CUSTOM and not item.primary_cta_label.strip():
                        raise CampaignError("Custom CTA requires an approved label.")
                    _public_http_url(item.primary_cta_url, "Primary CTA URL", required=True)
                except CampaignError as error:
                    issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "primary_cta_url", str(error)))
                if item.primary_cta_url_status.upper() == "REVIEW REQUIRED":
                    issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "primary_cta_url_status", "CTA destination must be verified before build."))
            if item.youtube_video_count is not None and item.youtube_video_count < 30:
                issues.append(ValidationIssue(item.candidate_number, "WARNING", "youtube_video_count", "Fewer than the preferred 30 videos; operator review recommended."))
            if item.youtube_ownership_status not in OWNERSHIP_STATES:
                issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "youtube_ownership_status", "Use VERIFIED, LIKELY, or REVIEW REQUIRED."))
            if item.youtube_ownership_status == "REVIEW REQUIRED":
                issues.append(ValidationIssue(item.candidate_number, "WARNING", "youtube_ownership_status", "Channel ownership still requires operator review."))
            if item.video_count_status not in VIDEO_COUNT_STATES:
                issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "video_count_status", "Use VERIFIED, APPROXIMATE, or UNKNOWN."))
            if item.research_confidence not in CONFIDENCE_STATES:
                issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "research_confidence", "Use HIGH, MEDIUM, or REVIEW REQUIRED."))
            palette = item.palette_mode.strip().upper()
            if palette not in {"", "CHANNEL MASTER DEFAULT", "ONE PALETTE FOR ALL", "USE CSV VALUES", *CHANNEL_MASTER_PALETTES, "CUSTOM"}:
                issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "palette_mode", "Select a canonical Channel Master palette mode."))
            if palette in {"CUSTOM", "USE CSV VALUES"}:
                for field_name in ("palette_primary", "palette_accent"):
                    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", getattr(item, field_name)):
                        issues.append(ValidationIssue(item.candidate_number, "BLOCKED", field_name, "Custom palette colours must use #RRGGBB."))
            ticker_mode = item.ticker_mode.strip().upper() or "TITLE ONLY"
            if ticker_mode not in {"TITLE ONLY", "VERIFIED AUTO COPY", "USE CSV TEXT"}:
                issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "ticker_mode", "Use TITLE ONLY, VERIFIED AUTO COPY, or USE CSV TEXT."))
            elif ticker_mode != "TITLE ONLY" and not item.ticker_text:
                issues.append(ValidationIssue(item.candidate_number, "BLOCKED", "ticker_text", "This ticker mode requires verified text."))
            if len(issues) == before and item.approved_for_build:
                item.approved_at = item.approved_at or utc_now()
        blocked_numbers = {issue.candidate_number for issue in issues if issue.severity == "BLOCKED"}
        warning_numbers = {issue.candidate_number for issue in issues if issue.severity == "WARNING" and issue.candidate_number not in blocked_numbers}
        return CampaignValidation(
            valid=len(campaign.candidates) - len(blocked_numbers) - len(warning_numbers),
            warnings=len(warning_numbers), blocked=len(blocked_numbers), issues=tuple(issues),
        )


class CandidateResearchService:
    """Authorised research boundary. The desktop ships without a prospect-data provider."""

    available = False
    provider_name = "NOT CONFIGURED"

    def find_candidates(self, *, theme: str, location: str, limit: int) -> list[CampaignCandidate]:
        raise ResearchUnavailableError(
            "No authorised candidate-research provider is configured. Use IMPORT CSV with verified prospect data."
        )


class CampaignQualificationService:
    CTA_GUIDANCE = (
        (("dance", "performance", "theatre", "festival"), PrimaryCtaType.TICKETS),
        (("music", "band", "artist"), PrimaryCtaType.SPOTIFY),
        (("tourism", "museum", "destination"), PrimaryCtaType.PLAN_YOUR_VISIT),
        (("accommodation", "hotel", "stay"), PrimaryCtaType.STAY),
        (("retail", "shop", "store"), PrimaryCtaType.SHOP_NOW),
        (("service", "trade"), PrimaryCtaType.GET_A_QUOTE),
    )

    @classmethod
    def recommend_cta(cls, theme: str, verified_destination_url: str = "") -> tuple[PrimaryCtaType, str, str]:
        cleaned = _clean_text(theme, limit=120).lower()
        cta = PrimaryCtaType.VISIT_WEBSITE
        for keywords, proposed in cls.CTA_GUIDANCE:
            if any(keyword in cleaned for keyword in keywords):
                cta = proposed
                break
        if verified_destination_url:
            destination = _public_http_url(verified_destination_url, "CTA destination")
            return cta, destination, "VERIFIED"
        return cta, "", "REVIEW REQUIRED"

    @staticmethod
    def assess(candidate: CampaignCandidate) -> tuple[str, list[str]]:
        notes: list[str] = []
        if candidate.youtube_video_count is None:
            notes.append("Video count unknown.")
        elif candidate.youtube_video_count < 30:
            notes.append("Below the preferred 30-video archive depth.")
        else:
            notes.append(f"Archive depth qualifies ({candidate.youtube_video_count} videos; no upper ceiling).")
        notes.append(f"Channel ownership: {candidate.youtube_ownership_status}.")
        if not candidate.primary_cta_url or candidate.primary_cta_url_status == "REVIEW REQUIRED":
            notes.append("CTA destination requires verification.")
        status = "QUALIFIED" if candidate.youtube_video_count is not None and candidate.youtube_video_count >= 30 and candidate.youtube_ownership_status in {"VERIFIED", "LIKELY"} and candidate.primary_cta_url else "REVIEW REQUIRED"
        return status, notes


class YouTubeCatalogueProvider(Protocol):
    def fetch_catalogue(self, channel_url: str, maximum: int = MAX_CHANNEL_MASTER_REVIEW_VIDEOS) -> ChannelCatalogue: ...


class BulkChannelMasterBuilder:
    def __init__(self, project_store: ProjectStore, campaign_store: CampaignStore, youtube: YouTubeCatalogueProvider) -> None:
        self.project_store = project_store
        self.campaign_store = campaign_store
        self.youtube = youtube

    def _palette(self, candidate: CampaignCandidate) -> ChannelMasterConfig:
        mode = candidate.palette_mode.strip().upper()
        cta_type = _cta_type(candidate.primary_cta_type)
        custom_label = candidate.primary_cta_label.strip() if cta_type is PrimaryCtaType.CUSTOM else None
        cta = PrimaryCta(cta_type, _public_http_url(candidate.primary_cta_url, "Primary CTA URL", required=True), custom_label=custom_label)
        contact = _public_http_url(candidate.contact_url, "Contact URL") or None
        if mode in {"CUSTOM", "USE CSV VALUES"}:
            return ChannelMasterConfig(palette="CUSTOM", custom_primary=candidate.palette_primary, custom_accent=candidate.palette_accent, primary_cta=cta, contact_url=contact)
        palette = mode if mode in CHANNEL_MASTER_PALETTES else DEFAULT_PALETTE
        return ChannelMasterConfig(palette=palette, primary_cta=cta, contact_url=contact)

    def build_candidate(self, campaign: Campaign, candidate: CampaignCandidate) -> Project:
        if not candidate.approved_for_build:
            raise CampaignError("Candidate is not approved for build.")
        if candidate.build_status == "BUILT" and candidate.project_uuid and candidate.project_slug:
            existing = self.project_store.load_project(candidate.project_slug)
            if existing.id != candidate.project_uuid:
                raise CampaignError("Saved campaign mapping does not match the existing project identity.")
            return existing
        validation = CampaignCsvService.validate(campaign, self.project_store.list_projects())
        blockers = [issue for issue in validation.issues if issue.candidate_number == candidate.candidate_number and issue.severity == "BLOCKED"]
        if blockers:
            raise CampaignError("; ".join(issue.message for issue in blockers))
        candidate.build_status = "BUILDING"
        campaign.status = "BUILDING"
        self.campaign_store.save(campaign)
        catalogue = self.youtube.fetch_catalogue(candidate.youtube_channel_url, MAX_CHANNEL_MASTER_REVIEW_VIDEOS)
        if not catalogue.videos:
            raise CampaignError("No eligible public YouTube videos were found for this candidate.")
        slug = self.project_store.allocate_slug(candidate.organisation_name)
        project = Project(
            slug=slug,
            title=candidate.organisation_name,
            ticker_text=candidate.organisation_name if candidate.ticker_mode.strip().upper() in {"", "TITLE ONLY"} else candidate.ticker_text,
            channel_url=catalogue.channel_url,
            channel_id=catalogue.channel_id,
            channel_title=catalogue.channel_title,
            channel_thumbnail=catalogue.channel_thumbnail,
            project_type=ProjectType.CHANNEL_MASTER,
            channel_master_config=self._palette(candidate),
            source_channel_url=canonical_youtube_channel_url(candidate.youtube_channel_url),
            videos=list(catalogue.videos[:MAX_CHANNEL_MASTER_REVIEW_VIDEOS]),
            extra_fields={
                "creation_source": "bulk_upload",
                "campaign_id": campaign.campaign_id,
                "candidate_number": candidate.candidate_number,
            },
        )
        project_directory = self.project_store.project_dir(project.slug)
        temporary_site = project_directory / ".site-build"
        final_site = project_directory / "site"
        if temporary_site.exists():
            shutil.rmtree(temporary_site)
        try:
            build_project_site(project, temporary_site)
            self.project_store.save_project(project)
            if final_site.exists():
                raise CampaignError("A generated site already exists for the newly allocated project slug.")
            temporary_site.replace(final_site)
        except Exception:
            if temporary_site.exists():
                shutil.rmtree(temporary_site)
            raise
        candidate.project_uuid = project.id
        candidate.project_slug = project.slug
        candidate.build_status = "BUILT"
        candidate.review_status = "BUILT"
        candidate.prospect_status = "BUILT"
        candidate.built_at = utc_now()
        candidate.error_message = ""
        campaign.status = "BUILT" if all(not item.approved_for_build or item.build_status == "BUILT" for item in campaign.candidates) else "PARTIAL_FAILURE"
        self.campaign_store.save(campaign)
        return project

    def build_approved(self, campaign: Campaign) -> list[Project]:
        approved = [item for item in campaign.candidates if item.approved_for_build]
        if len(approved) > MAX_CAMPAIGN_CANDIDATES:
            raise CampaignError("No more than 20 candidates may be built in one campaign.")
        projects: list[Project] = []
        for candidate in approved:
            try:
                projects.append(self.build_candidate(campaign, candidate))
            except Exception as error:
                candidate.build_status = "FAILED"
                candidate.error_message = str(error)
                campaign.status = "PARTIAL_FAILURE"
                self.campaign_store.save(campaign)
        return projects


class ProjectPublisher(Protocol):
    def publish(self, project: Project) -> tuple[str, str]: ...


class BulkPublishCoordinator:
    def __init__(self, project_store: ProjectStore, campaign_store: CampaignStore, publisher: ProjectPublisher) -> None:
        self.project_store = project_store
        self.campaign_store = campaign_store
        self.publisher = publisher

    def publish_approved(self, campaign: Campaign) -> list[Project]:
        selected = [item for item in campaign.candidates if item.review_status == "APPROVED TO PUBLISH" or item.publish_status == "APPROVED TO PUBLISH"]
        if not selected:
            raise CampaignError("No reviewed machines are approved to publish.")
        campaign.status = "PUBLISHING"
        self.campaign_store.save(campaign)
        published: list[Project] = []
        for candidate in selected:
            if candidate.publish_status == "PUBLISHED" and candidate.public_url:
                published.append(self.project_store.load_project(candidate.project_slug))
                continue
            try:
                project = self.project_store.load_project(candidate.project_slug)
                candidate.publish_status = "PUBLISHING"
                self.campaign_store.save(campaign)
                public_url, revision = self.publisher.publish(project)
                project = self.project_store.load_project(candidate.project_slug)
                project.status = "published"
                project.published_url = public_url
                project.published_at = utc_now()
                project.publication_revision = revision
                project.delivery_status = "not_requested"
                self.project_store.save_project(project)
                candidate.public_url = public_url
                candidate.publish_status = "PUBLISHED"
                candidate.prospect_status = "PUBLISHED"
                candidate.published_at = utc_now()
                candidate.error_message = ""
                published.append(project)
            except Exception as error:
                candidate.publish_status = "FAILED"
                candidate.error_message = str(error)
            self.campaign_store.save(campaign)
        campaign.status = "PUBLISHED" if all(item.publish_status == "PUBLISHED" for item in selected) else "PARTIAL_FAILURE"
        self.campaign_store.save(campaign)
        return published


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf")]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


class CampaignQrService:
    @staticmethod
    def generate(campaign: Campaign, output_dir: Path) -> list[Path]:
        qr_dir = output_dir / "qr"
        qr_dir.mkdir(parents=True, exist_ok=True)
        created: list[Path] = []
        for candidate in campaign.candidates:
            if candidate.publish_status != "PUBLISHED" or not candidate.public_url:
                continue
            public_url = _public_http_url(candidate.public_url, "Published URL", required=True)
            filename = f"qr-{candidate.candidate_number:02d}-{slugify(candidate.organisation_name)[:48]}.png"
            destination = qr_dir / filename
            code = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H, box_size=10, border=4)
            code.add_data(public_url)
            code.make(fit=True)
            code.make_image(fill_color="#102a22", back_color="#ffffff").convert("RGB").save(destination, "PNG", optimize=True)
            candidate.qr_path = f"qr/{filename}"
            created.append(destination)
        return created


class CampaignPdfService:
    PAGE_SIZE = (2480, 3508)

    @staticmethod
    def _fit_tile_name(draw: ImageDraw.ImageDraw, name: str, max_width: int) -> tuple[ImageFont.ImageFont, list[str]]:
        words = name.split()
        for size in range(29, 17, -1):
            font = _font(size, True)
            if draw.textbbox((0, 0), name, font=font)[2] <= max_width:
                return font, [name]
            best: tuple[int, list[str]] | None = None
            for split in range(1, len(words)):
                lines = [" ".join(words[:split]), " ".join(words[split:])]
                if max(draw.textbbox((0, 0), line, font=font)[2] for line in lines) <= max_width:
                    balance = abs(len(lines[0]) - len(lines[1]))
                    if best is None or balance < best[0]:
                        best = (balance, lines)
            if best:
                return font, best[1]
        clipped = name[:66].rstrip()
        return _font(17, True), [clipped[:33].rstrip(), clipped[33:].strip()]

    @classmethod
    def generate(cls, campaign: Campaign, output_dir: Path) -> Path:
        candidates = [item for item in campaign.candidates if item.publish_status == "PUBLISHED" and item.qr_path]
        if not candidates:
            raise CampaignError("At least one successful publication is required for the QR sheet.")
        if len(candidates) > MAX_CAMPAIGN_CANDIDATES:
            raise CampaignError("A one-page campaign QR sheet supports no more than 20 machines.")
        canvas = Image.new("RGB", cls.PAGE_SIZE, "#fbf7eb")
        draw = ImageDraw.Draw(canvas)
        logo_path = resource_path("static/channel-master/crispy-bits-maker-mark-approved.png")
        if logo_path.is_file():
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((420, 190), Image.Resampling.LANCZOS)
            canvas.paste(logo, ((canvas.width - logo.width) // 2, 70), logo)
        title = f"{campaign.theme} - {campaign.location}".upper() if campaign.theme and campaign.location else campaign.campaign_name.upper()
        title_font = _font(72, True)
        while draw.textbbox((0, 0), title, font=title_font)[2] > 2200 and getattr(title_font, "size", 40) > 40:
            title_font = _font(getattr(title_font, "size", 72) - 4, True)
        box = draw.textbbox((0, 0), title, font=title_font)
        draw.text(((canvas.width - (box[2] - box[0])) / 2, 270), title, font=title_font, fill="#14342d")
        margin_x, grid_top, gap_x, gap_y = 100, 430, 28, 32
        tile_w = (canvas.width - 2 * margin_x - 3 * gap_x) // 4
        tile_h = (canvas.height - grid_top - 130 - 4 * gap_y) // 5
        for index, candidate in enumerate(candidates):
            row, column = divmod(index, 4)
            x = margin_x + column * (tile_w + gap_x)
            y = grid_top + row * (tile_h + gap_y)
            draw.rounded_rectangle((x, y, x + tile_w, y + tile_h), radius=22, fill="#ffffff", outline="#a9772d", width=4)
            qr = Image.open(output_dir / candidate.qr_path).convert("RGB")
            qr_size = min(tile_w - 92, tile_h - 170)
            qr = qr.resize((qr_size, qr_size), Image.Resampling.NEAREST)
            canvas.paste(qr, (x + (tile_w - qr_size) // 2, y + 52))
            number = f"{candidate.candidate_number:02d}"
            draw.text((x + 22, y + 17), number, font=_font(36, True), fill="#a06e2d")
            font, lines = cls._fit_tile_name(draw, candidate.organisation_name, tile_w - 38)
            line_height = getattr(font, "size", 20) + 5
            text_y = y + tile_h - 26 - line_height * len(lines)
            for line in lines:
                text_box = draw.textbbox((0, 0), line, font=font)
                draw.text((x + (tile_w - (text_box[2] - text_box[0])) / 2, text_y), line, font=font, fill="#14342d")
                text_y += line_height
        destination = output_dir / "qr-sheet.pdf"
        canvas.save(destination, "PDF", resolution=300.0)
        return destination


class ProspectCardService:
    """Deterministic private outreach-card renderer; it has no publish or send capability."""

    WIDTH = 1080
    HEIGHT = 1350
    TEMPLATE_VERSION = "prospect-card-v1"
    MESSAGE = "I MADE THIS FOR YOU."
    INSTRUCTION = "SCAN IT. PULL THE LEVER."

    @staticmethod
    def _fit_name(draw: ImageDraw.ImageDraw, name: str, max_width: int) -> tuple[ImageFont.ImageFont, list[str]]:
        words = name.split()
        for size in range(58, 31, -2):
            font = _font(size, True)
            if draw.textbbox((0, 0), name, font=font)[2] <= max_width:
                return font, [name]
            best: tuple[int, list[str]] | None = None
            for split in range(1, len(words)):
                lines = [" ".join(words[:split]), " ".join(words[split:])]
                width = max(draw.textbbox((0, 0), line, font=font)[2] for line in lines)
                if width <= max_width:
                    balance = abs(len(lines[0]) - len(lines[1]))
                    if best is None or balance < best[0]:
                        best = (balance, lines)
            if best:
                return font, best[1]
        clipped = name[:70].rstrip()
        return _font(30, True), [clipped[:35].rstrip(), clipped[35:].strip()]

    @classmethod
    def generate_candidate(cls, candidate: CampaignCandidate, destination: Path) -> Path:
        if candidate.publish_status != "PUBLISHED" or not candidate.public_url:
            raise CampaignError("A verified published URL is required before a prospect card can be generated.")
        public_url = _public_http_url(candidate.public_url, "Published URL", required=True)
        name = _clean_text(candidate.organisation_name, limit=120)
        if not name:
            raise CampaignError("Organisation name is required for a prospect card.")
        canvas = Image.new("RGB", (cls.WIDTH, cls.HEIGHT), "#07120f")
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle((34, 34, cls.WIDTH - 34, cls.HEIGHT - 34), radius=36, outline="#b88947", width=4)
        draw.rounded_rectangle((52, 52, cls.WIDTH - 52, cls.HEIGHT - 52), radius=30, outline="#5c4226", width=2)
        logo_path = resource_path("static/channel-master/crispy-bits-maker-mark-approved.png")
        if not logo_path.is_file():
            raise CampaignError("The approved Crispy Bits logo asset is missing.")
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((420, 142), Image.Resampling.LANCZOS)
        canvas.paste(logo, ((cls.WIDTH - logo.width) // 2, 82), logo)

        name_font, lines = cls._fit_name(draw, name, 900)
        y = 250
        for line in lines:
            box = draw.textbbox((0, 0), line, font=name_font)
            draw.text(((cls.WIDTH - (box[2] - box[0])) / 2, y), line, font=name_font, fill="#f2e4bf")
            y += 62
        y += 18 if len(lines) == 1 else 2
        message_font = _font(42, True)
        box = draw.textbbox((0, 0), cls.MESSAGE, font=message_font)
        draw.text(((cls.WIDTH - (box[2] - box[0])) / 2, y), cls.MESSAGE, font=message_font, fill="#c99a57")

        code = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H, box_size=14, border=4)
        code.add_data(public_url)
        code.make(fit=True)
        qr = code.make_image(fill_color="#07120f", back_color="#ffffff").convert("RGB")
        qr_size = 620
        qr = qr.resize((qr_size, qr_size), Image.Resampling.NEAREST)
        qr_left = (cls.WIDTH - qr_size) // 2
        qr_top = 500
        draw.rounded_rectangle((qr_left - 22, qr_top - 22, qr_left + qr_size + 22, qr_top + qr_size + 22), radius=22, fill="#ffffff", outline="#b88947", width=4)
        canvas.paste(qr, (qr_left, qr_top))
        instruction_font = _font(38, True)
        box = draw.textbbox((0, 0), cls.INSTRUCTION, font=instruction_font)
        draw.text(((cls.WIDTH - (box[2] - box[0])) / 2, 1206), cls.INSTRUCTION, font=instruction_font, fill="#f2e4bf")
        destination.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(destination, "PNG", optimize=True)
        with Image.open(destination) as check:
            if check.size != (cls.WIDTH, cls.HEIGHT) or check.format != "PNG":
                raise CampaignError("Prospect card output verification failed.")
        candidate.prospect_card_status = "READY"
        candidate.prospect_card_path = f"prospect-cards/{destination.name}"
        candidate.prospect_card_template_version = cls.TEMPLATE_VERSION
        return destination

    @classmethod
    def generate_campaign(cls, campaign: Campaign, output_dir: Path) -> tuple[list[Path], list[tuple[int, str]]]:
        card_dir = output_dir / "prospect-cards"
        card_dir.mkdir(parents=True, exist_ok=True)
        cards: list[Path] = []
        failures: list[tuple[int, str]] = []
        for candidate in campaign.candidates:
            if candidate.publish_status != "PUBLISHED" or not candidate.public_url:
                candidate.prospect_card_status = "NOT_READY"
                candidate.prospect_card_path = ""
                continue
            filename = f"{candidate.candidate_number:02d}-{slugify(candidate.organisation_name)[:48]}-crispy-bits.png"
            try:
                cards.append(cls.generate_candidate(candidate, card_dir / filename))
            except Exception as error:
                candidate.prospect_card_status = "FAILED"
                candidate.prospect_card_path = ""
                failures.append((candidate.candidate_number, str(error)))
        return cards, failures

    @classmethod
    def regenerate_candidate(cls, candidate: CampaignCandidate, output_dir: Path) -> Path:
        filename = f"{candidate.candidate_number:02d}-{slugify(candidate.organisation_name)[:48]}-crispy-bits.png"
        return cls.generate_candidate(candidate, output_dir / "prospect-cards" / filename)


class CampaignPackageService:
    def __init__(self, store: CampaignStore, project_store: ProjectStore | None = None, *, verify_publications: bool = True) -> None:
        self.store = store
        self.project_store = project_store or ProjectStore(store.root)
        self.verify_publications = verify_publications

    def _verify_publications(self, campaign: Campaign) -> None:
        if not self.verify_publications:
            return
        for candidate in campaign.candidates:
            if candidate.publish_status != "PUBLISHED":
                continue
            if not candidate.project_uuid or not candidate.project_slug or not candidate.public_url:
                raise CampaignError(f"Candidate {candidate.candidate_number:02d} is missing its verified project mapping.")
            try:
                project = self.project_store.load_project(candidate.project_slug)
            except (OSError, ValueError) as error:
                raise CampaignError(f"Candidate {candidate.candidate_number:02d} published project could not be loaded.") from error
            if project.id != candidate.project_uuid or project.status != "published" or project.published_url != candidate.public_url:
                raise CampaignError(f"Candidate {candidate.candidate_number:02d} publication mapping is not verified.")

    def generate(self, campaign: Campaign) -> Path:
        self._verify_publications(campaign)
        output = self.store.output_dir(campaign)
        temporary = output.with_name(".output-build")
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        qr_files = CampaignQrService.generate(campaign, temporary)
        pdf = CampaignPdfService.generate(campaign, temporary)
        prospect_cards, card_failures = ProspectCardService.generate_campaign(campaign, temporary)
        CampaignCsvService.export(campaign, temporary / "campaign.csv")
        successful = [item for item in campaign.candidates if item.publish_status == "PUBLISHED" and item.public_url]
        report = {
            "schema_version": 1,
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "generated_at": utc_now(),
            "counts": campaign.counts(),
            "machines": [
                {"candidate_number": item.candidate_number, "organisation_name": item.organisation_name, "project_uuid": item.project_uuid, "project_slug": item.project_slug, "public_url": item.public_url, "qr_path": item.qr_path, "prospect_card_status": item.prospect_card_status, "prospect_card_path": item.prospect_card_path, "prospect_card_template_version": item.prospect_card_template_version}
                for item in successful
            ],
            "prospect_card_failures": [
                {"candidate_number": number, "error": error} for number, error in card_failures
            ],
        }
        (temporary / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with (temporary / "campaign-report.txt").open("w", encoding="utf-8") as stream:
            stream.write(f"{campaign.campaign_name}\n\n")
            stream.write(json.dumps(campaign.counts(), indent=2) + "\n\n")
            for item in successful:
                stream.write(f"{item.candidate_number:02d}. {item.organisation_name} — {item.public_url}\n")
        with zipfile.ZipFile(temporary / "qr-codes.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in qr_files:
                archive.write(path, arcname=path.name)
        with zipfile.ZipFile(temporary / "prospect-cards.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in prospect_cards:
                archive.write(path, arcname=path.name)
        if len(qr_files) != len(successful) or not pdf.is_file():
            raise CampaignError("Campaign package count verification failed.")
        if output.exists():
            shutil.rmtree(output)
        temporary.replace(output)
        campaign.package_path = str(output)
        campaign.package_created_at = utc_now()
        campaign.status = "PACKAGE_CREATED"
        campaign.email_status = "READY"
        self.store.save(campaign)
        return output


@dataclass(frozen=True, slots=True)
class CampaignEmail:
    campaign_id: str
    campaign_name: str
    machines: tuple[tuple[int, str, str], ...]
    counts: dict[str, int]
    subject: str
    text: str
    attachments: tuple[Path, ...]
    idempotency_key: str

    def to_worker_payload(self) -> dict[str, Any]:
        return {
            "campaignId": self.campaign_id,
            "campaignName": self.campaign_name,
            "machines": [
                {"candidateNumber": number, "organisationName": name, "publicUrl": public_url}
                for number, name, public_url in self.machines
            ],
            "counts": dict(self.counts),
            "idempotencyKey": self.idempotency_key,
            "attachments": [
                {"filename": path.name, "content": base64.b64encode(path.read_bytes()).decode("ascii")}
                for path in self.attachments
            ],
        }


class CampaignEmailPackager:
    @staticmethod
    def prepare(campaign: Campaign, package_dir: Path) -> CampaignEmail:
        successful = [item for item in campaign.candidates if item.publish_status == "PUBLISHED" and item.public_url]
        attachments = tuple(package_dir / name for name in ("campaign.csv", "qr-sheet.pdf", "prospect-cards.zip", "qr-codes.zip"))
        missing = [path.name for path in attachments if not path.is_file()]
        if missing:
            raise CampaignError("Campaign email attachments are missing: " + ", ".join(missing))
        size = sum(path.stat().st_size for path in attachments)
        if size > CAMPAIGN_EMAIL_MAX_BYTES:
            raise CampaignError("Campaign email attachments exceed the 8 MB delivery limit.")
        counts = campaign.counts()
        subject = f"CRISPY BITS — {campaign.campaign_name} — {len(successful)} MACHINES"
        lines = [subject, "", f"Approved: {counts['approved']}", f"Built: {counts['built']}", f"Published: {counts['published']}", f"Failures: {counts['failed']}", ""]
        lines.extend(f"{item.candidate_number:02d}. {item.organisation_name} — {item.public_url}" for item in successful)
        digest = hashlib.sha256((campaign.campaign_id + "\n" + "\n".join(item.public_url for item in successful)).encode("utf-8")).hexdigest()
        machines = tuple((item.candidate_number, item.organisation_name, item.public_url) for item in successful)
        return CampaignEmail(campaign.campaign_id, campaign.campaign_name, machines, counts, subject, "\n".join(lines), attachments, digest)


class CampaignEmailTransport(Protocol):
    def send(self, email: CampaignEmail) -> str: ...


class CampaignEmailCoordinator:
    def __init__(self, store: CampaignStore, transport: CampaignEmailTransport) -> None:
        self.store = store
        self.transport = transport

    def send(self, campaign: Campaign) -> str:
        email = CampaignEmailPackager.prepare(campaign, self.store.output_dir(campaign))
        if campaign.email_status == "SENT" and campaign.email_idempotency_key == email.idempotency_key:
            return "already_sent"
        try:
            provider_id = self.transport.send(email)
        except Exception:
            campaign.email_status = "FAILED"
            self.store.save(campaign)
            raise
        campaign.email_status = "SENT"
        campaign.email_idempotency_key = email.idempotency_key
        campaign.emailed_at = utc_now()
        campaign.status = "EMAILED"
        self.store.save(campaign)
        return provider_id
