from __future__ import annotations

import shutil
import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .config import MAX_SPONSOR_CREATIVES, MAX_SPONSOR_LOGO_BYTES, MAX_SPONSOR_MP4_BYTES
from .models import BanjoChoice, BanjoConfig, SponsorConfig, SponsorCreative, Video
from .youtube_api import YouTubeClient


BANJO_TITLE = "BANJO'S WORLD OF CARS"
BANJO_DEFAULT_SLUG = "banjos-world-of-cars"
SPONSOR_DISCOVERY_THRESHOLD = 5
BANJO_CHARACTER_SHA256 = "41c698b24918f303ade03945f82c15642e4ba589cfbae57ad35227003afa6b62"


class BanjoValidationError(ValueError):
    pass


def verify_banjo_character(path: Path) -> None:
    """Protect the exact approved, transparency-derived character asset."""
    asset = Path(path)
    if not asset.is_file():
        raise BanjoValidationError("The approved transparent Banjo character asset is missing.")
    if hashlib.sha256(asset.read_bytes()).hexdigest() != BANJO_CHARACTER_SHA256:
        raise BanjoValidationError("The approved Banjo character asset has been changed.")
    with Image.open(asset) as image:
        if image.mode != "RGBA" or image.getextrema()[3][0] != 0 or image.getextrema()[3][1] != 255:
            raise BanjoValidationError("The approved Banjo character must retain its transparent background.")


def validate_sponsor_mp4(source: Path) -> int:
    path = Path(source)
    if not path.is_file():
        raise BanjoValidationError("The selected sponsor MP4 file does not exist.")
    if path.suffix.casefold() != ".mp4":
        raise BanjoValidationError("Sponsor videos must be MP4 files.")
    size = path.stat().st_size
    if size > MAX_SPONSOR_MP4_BYTES:
        raise BanjoValidationError("Sponsor MP4 files cannot exceed 10 MB.")
    return size


def import_sponsor_mp4(source: Path, project_directory: Path, *, active: bool = True) -> SponsorCreative:
    """Copy a selected creative into project-controlled storage.

    Original absolute paths are intentionally never serialized. Replacing a
    creative calls this function again and therefore receives a new ID.
    """
    source = Path(source)
    size = validate_sponsor_mp4(source)
    creative_id = str(uuid4())
    relative = Path("assets") / f"sponsor-{creative_id}.mp4"
    destination = project_directory / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".mp4.tmp")
    shutil.copy2(source, temporary)
    temporary.replace(destination)
    return SponsorCreative(
        creative_id=creative_id,
        asset_path=relative.as_posix(),
        filename=source.name,
        active=active,
        size_bytes=size,
    )


def validate_sponsor_logo(source: Path) -> int:
    path = Path(source)
    if not path.is_file():
        raise BanjoValidationError("The selected Sponsor Logo file does not exist.")
    suffix = path.suffix.casefold()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise BanjoValidationError("Sponsor Logo must be a PNG, JPG, JPEG or WebP image.")
    size = path.stat().st_size
    if size > MAX_SPONSOR_LOGO_BYTES:
        raise BanjoValidationError("Sponsor Logo files cannot exceed 2 MB.")
    expected_formats = {".png": {"PNG"}, ".jpg": {"JPEG"}, ".jpeg": {"JPEG"}, ".webp": {"WEBP"}}
    try:
        with Image.open(path) as image:
            if image.format not in expected_formats[suffix]:
                raise BanjoValidationError("Sponsor Logo contents do not match the selected image type.")
            image.verify()
    except BanjoValidationError:
        raise
    except (OSError, ValueError) as error:
        raise BanjoValidationError("Sponsor Logo is not a valid PNG, JPG, JPEG or WebP image.") from error
    return size


def import_sponsor_logo(source: Path, project_directory: Path) -> tuple[str, str, int]:
    source = Path(source)
    size = validate_sponsor_logo(source)
    relative = Path("assets") / f"sponsor-logo-{uuid4()}{source.suffix.casefold()}"
    destination = project_directory / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copy2(source, temporary)
    temporary.replace(destination)
    return relative.as_posix(), source.name, size


def sponsor_media_summary(creatives: list[SponsorCreative]) -> tuple[int, int]:
    return len(creatives), sum(item.size_bytes for item in creatives)


@dataclass(slots=True)
class BanjoSponsorScheduler:
    """Deterministic, session-local sponsor eligibility and fair rotation."""

    normal_discoveries: int = 0
    next_creative_index: int = 0
    current_is_sponsor: bool = False

    def record_normal_landing(self) -> None:
        self.current_is_sponsor = False
        self.normal_discoveries += 1

    def next_sponsor(self, creatives: list[SponsorCreative], sponsor_active: bool) -> SponsorCreative | None:
        active = [item for item in creatives if item.active and item.asset_path]
        if not sponsor_active or self.current_is_sponsor or self.normal_discoveries < SPONSOR_DISCOVERY_THRESHOLD or not active:
            return None
        selected = active[self.next_creative_index % len(active)]
        self.next_creative_index = (self.next_creative_index + 1) % len(active)
        self.normal_discoveries = 0
        self.current_is_sponsor = True
        return selected


def validate_creative_capacity(creatives: list[SponsorCreative]) -> None:
    if len(creatives) > MAX_SPONSOR_CREATIVES:
        raise BanjoValidationError("A Banjo project can contain no more than four sponsor MP4s.")


def materialize_banjo_config(
    values: object,
    videos: list[Video],
    included_video_ids: set[str],
    project_directory: Path,
    existing: BanjoConfig | None = None,
) -> BanjoConfig:
    """Resolve form-only paths into durable Banjo configuration."""
    known = {video.video_id: video for video in videos}
    choices: list[BanjoChoice] = []
    urls = list(getattr(values, "banjo_choice_urls", []))
    titles = list(getattr(values, "banjo_choice_titles", []))
    active_flags = list(getattr(values, "banjo_choice_active", []))
    for index, url in enumerate(urls[:4]):
        raw_url = str(url or "").strip()
        if not raw_url:
            continue
        video_id = YouTubeClient.video_id_from_url(raw_url)
        if not video_id or video_id not in known:
            raise BanjoValidationError("Banjo's Choice video could not be resolved as a public YouTube video.")
        display_title = titles[index].strip() if index < len(titles) else ""
        active = bool(active_flags[index]) if index < len(active_flags) else True
        choices.append(BanjoChoice(video_id, display_title, active and video_id in included_video_ids))

    previous = {item.asset_path: item for item in (existing.sponsor.creatives if existing else [])}
    creatives: list[SponsorCreative] = []
    paths = list(getattr(values, "sponsor_creative_paths", []))
    creative_flags = list(getattr(values, "sponsor_creative_active", []))
    for index, raw in enumerate(paths[:MAX_SPONSOR_CREATIVES]):
        enabled = bool(creative_flags[index]) if index < len(creative_flags) else True
        normalized = str(raw or "").replace("\\", "/").strip()
        if not normalized:
            continue
        if normalized in previous:
            original = previous[normalized]
            source = project_directory / original.asset_path
            validate_sponsor_mp4(source)
            creatives.append(SponsorCreative(
                creative_id=original.creative_id,
                asset_path=original.asset_path,
                filename=original.filename,
                active=enabled,
                size_bytes=source.stat().st_size,
            ))
        else:
            creatives.append(import_sponsor_mp4(Path(raw), project_directory, active=enabled))
    validate_creative_capacity(creatives)
    logo_asset_path = ""
    logo_filename = ""
    logo_size_bytes = 0
    requested_logo = str(getattr(values, "sponsor_logo_path", "") or "").replace("\\", "/").strip()
    previous_sponsor = existing.sponsor if existing else None
    if requested_logo:
        if previous_sponsor and requested_logo == previous_sponsor.logo_asset_path:
            logo_source = project_directory / previous_sponsor.logo_asset_path
            logo_size_bytes = validate_sponsor_logo(logo_source)
            logo_asset_path = previous_sponsor.logo_asset_path
            logo_filename = previous_sponsor.logo_filename
        else:
            logo_asset_path, logo_filename, logo_size_bytes = import_sponsor_logo(Path(requested_logo), project_directory)
    return BanjoConfig(
        banjos_choice=choices,
        sponsor=SponsorConfig(
            active=bool(getattr(values, "sponsor_active", False)),
            title=str(getattr(values, "sponsor_title", "")),
            url=str(getattr(values, "sponsor_url", "")) or None,
            creatives=creatives,
            logo_asset_path=logo_asset_path,
            logo_filename=logo_filename,
            logo_size_bytes=logo_size_bytes,
        ),
    )
