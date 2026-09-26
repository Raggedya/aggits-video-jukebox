from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from PIL import Image, ImageChops, ImageDraw

from .models import WhiteLabelConfig


MAX_WHITE_LABEL_LOGO_BYTES = 5 * 1024 * 1024
MAX_WHITE_LABEL_LOGO_PIXELS = 40_000_000
MIN_LOGO_SCALE_PERCENT = 60
MAX_LOGO_SCALE_PERCENT = 120
MIN_LOGO_VERTICAL_POSITION = -2
MAX_LOGO_VERTICAL_POSITION = 2
BACKGROUND_REMOVAL_MODES = frozenset({"auto", "off"})
ALLOWED_WHITE_LABEL_LOGO_FORMATS = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "WEBP": (".webp", "image/webp"),
}


@dataclass(frozen=True, slots=True)
class WhiteLabelLogoDetails:
    source: Path
    suffix: str
    media_type: str
    width: int
    height: int
    has_transparency: bool


@dataclass(frozen=True, slots=True)
class PreparedWhiteLabelLogo:
    image: Image.Image
    status: str
    confidence: float
    original_width: int
    original_height: int
    visible_bbox: tuple[int, int, int, int]
    transparent_margin_percent: float

    @property
    def has_transparency(self) -> bool:
        return self.image.getchannel("A").getextrema()[0] < 255

    @property
    def aspect_ratio(self) -> float:
        return self.image.width / self.image.height


def validate_logo_adjustments(background_removal: str, scale_percent: int, vertical_position: int) -> tuple[str, int, int]:
    mode = str(background_removal or "auto").strip().lower()
    scale = int(scale_percent)
    position = int(vertical_position)
    if mode not in BACKGROUND_REMOVAL_MODES:
        raise ValueError("Background Removal must be AUTO or OFF.")
    if not MIN_LOGO_SCALE_PERCENT <= scale <= MAX_LOGO_SCALE_PERCENT:
        raise ValueError(f"Logo Scale must be between {MIN_LOGO_SCALE_PERCENT}% and {MAX_LOGO_SCALE_PERCENT}%.")
    if not MIN_LOGO_VERTICAL_POSITION <= position <= MAX_LOGO_VERTICAL_POSITION:
        raise ValueError("Logo Vertical Position is outside the supported header safe area.")
    return mode, scale, position


def inspect_white_label_logo(path: Path) -> WhiteLabelLogoDetails:
    source = Path(path).expanduser()
    if not source.is_file():
        raise ValueError("Please upload a valid customer logo file.")
    if source.stat().st_size > MAX_WHITE_LABEL_LOGO_BYTES:
        raise ValueError("The customer logo cannot exceed 5 MB.")
    try:
        with Image.open(source) as image:
            image.verify()
        with Image.open(source) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            alpha = image.convert("RGBA").getchannel("A")
            transparency = alpha.getextrema()[0] < 255
    except (OSError, ValueError) as error:
        raise ValueError("The selected customer logo is not a readable image.") from error
    if image_format not in ALLOWED_WHITE_LABEL_LOGO_FORMATS:
        raise ValueError("Customer logos must be PNG, JPEG or WebP images.")
    if width < 1 or height < 1 or width > 12000 or height > 12000 or width * height > MAX_WHITE_LABEL_LOGO_PIXELS:
        raise ValueError("The customer logo dimensions are not supported.")
    suffix, media_type = ALLOWED_WHITE_LABEL_LOGO_FORMATS[image_format]
    return WhiteLabelLogoDetails(source, suffix, media_type, width, height, transparency)


def _colour_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return sum((left - right) ** 2 for left, right in zip(first, second)) ** 0.5


def _corner_means(image: Image.Image) -> list[tuple[int, int, int]]:
    width, height = image.size
    patch = max(1, min(20, width // 25, height // 25))
    boxes = (
        (0, 0, patch, patch),
        (width - patch, 0, width, patch),
        (0, height - patch, patch, height),
        (width - patch, height - patch, width, height),
    )
    means: list[tuple[int, int, int]] = []
    for box in boxes:
        colours = list(image.crop(box).getdata())
        means.append(tuple(round(sum(pixel[channel] for pixel in colours) / len(colours)) for channel in range(3)))
    return means


def _background_reference(image: Image.Image) -> tuple[tuple[int, int, int], float, float, int]:
    corners = _corner_means(image)
    reference = tuple(round(median(colour[channel] for colour in corners)) for channel in range(3))
    corner_spread = max(_colour_distance(colour, reference) for colour in corners)
    width, height = image.size
    edge_pixels: list[tuple[int, int, int]] = []
    step = max(1, (2 * width + 2 * height) // 4000)
    pixels = image.load()
    for x in range(0, width, step):
        edge_pixels.extend((pixels[x, 0], pixels[x, height - 1]))
    for y in range(0, height, step):
        edge_pixels.extend((pixels[0, y], pixels[width - 1, y]))
    tolerance = 36
    matched = sum(_colour_distance(pixel, reference) <= tolerance for pixel in edge_pixels)
    edge_ratio = matched / max(1, len(edge_pixels))
    return reference, corner_spread, edge_ratio, tolerance


def _remove_edge_connected_background(image: Image.Image) -> tuple[Image.Image, bool, float]:
    rgb = image.convert("RGB")
    reference, corner_spread, edge_ratio, tolerance = _background_reference(rgb)
    confidence = max(0.0, min(1.0, edge_ratio * (1.0 - min(corner_spread, 90.0) / 120.0)))
    if corner_spread > 34 or edge_ratio < 0.84 or confidence < 0.64:
        return image, False, confidence

    solid = Image.new("RGB", rgb.size, reference)
    red, green, blue = ImageChops.difference(rgb, solid).split()
    maximum_difference = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    candidate = maximum_difference.point(lambda value: 255 if value <= tolerance else 0)
    padded = Image.new("L", (image.width + 2, image.height + 2), 255)
    padded.paste(candidate, (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128, thresh=0)
    connected = padded.crop((1, 1, image.width + 1, image.height + 1))
    alpha = connected.point(lambda value: 0 if value == 128 else 255)
    result = image.copy()
    result.putalpha(alpha)
    return result, True, confidence


def _trim_visible_artwork(image: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int], float]:
    alpha = image.getchannel("A")
    meaningful = alpha.point(lambda value: 255 if value > 8 else 0)
    bbox = meaningful.getbbox()
    if bbox is None:
        raise ValueError("The selected customer logo contains no visible artwork.")
    left, top, right, bottom = bbox
    padding = max(4, min(64, round(max(right - left, bottom - top) * 0.035)))
    crop_box = (
        max(0, left - padding),
        max(0, top - padding),
        min(image.width, right + padding),
        min(image.height, bottom + padding),
    )
    trimmed = image.crop(crop_box)
    trimmed_alpha = trimmed.getchannel("A")
    visible_bbox = trimmed_alpha.point(lambda value: 255 if value > 8 else 0).getbbox() or (0, 0, trimmed.width, trimmed.height)
    histogram = trimmed_alpha.histogram()
    transparent_pixels = sum(histogram[:9])
    margin_percent = round(transparent_pixels * 100 / max(1, trimmed.width * trimmed.height), 2)
    return trimmed, visible_bbox, margin_percent


def _has_useful_transparency(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    non_opaque = sum(histogram[:250])
    return non_opaque / max(1, image.width * image.height) >= 0.005


def prepare_white_label_logo(path: Path, background_removal: str = "auto") -> PreparedWhiteLabelLogo:
    details = inspect_white_label_logo(path)
    mode, _, _ = validate_logo_adjustments(background_removal, 100, 0)
    with Image.open(details.source) as source:
        image = source.convert("RGBA")
    original_width, original_height = image.size
    if _has_useful_transparency(image):
        status = "existing_transparency"
        confidence = 1.0
    elif mode == "off":
        status = "off"
        confidence = 1.0
    else:
        image, removed, confidence = _remove_edge_connected_background(image)
        status = "removed" if removed else "not_confident"
    trimmed, visible_bbox, margin_percent = _trim_visible_artwork(image)
    return PreparedWhiteLabelLogo(
        image=trimmed,
        status=status,
        confidence=round(confidence, 4),
        original_width=original_width,
        original_height=original_height,
        visible_bbox=visible_bbox,
        transparent_margin_percent=margin_percent,
    )


def materialize_white_label_logo(
    source_path: str,
    project_dir: Path,
    *,
    background_removal: str = "auto",
    scale_percent: int = 100,
    vertical_position: int = 0,
    original_filename: str | None = None,
) -> WhiteLabelConfig:
    mode, scale, position = validate_logo_adjustments(background_removal, scale_percent, vertical_position)
    details = inspect_white_label_logo(Path(source_path))
    branding_dir = project_dir / "white-label"
    branding_dir.mkdir(parents=True, exist_ok=True)
    original = branding_dir / f"original-logo{details.suffix}"
    if details.source.resolve() != original.resolve():
        temporary_original = branding_dir / f".original-logo{details.suffix}.tmp"
        shutil.copy2(details.source, temporary_original)
        temporary_original.replace(original)
    prepared = prepare_white_label_logo(original, mode)
    processed = branding_dir / "processed-logo.png"
    temporary_processed = branding_dir / ".processed-logo.png.tmp"
    prepared.image.save(temporary_processed, format="PNG", optimize=True)
    temporary_processed.replace(processed)
    retained = {original.resolve(), processed.resolve()}
    for pattern in ("original-logo.*", "processed-logo.*", "customer-logo.*"):
        for sibling in branding_dir.glob(pattern):
            if sibling.is_file() and sibling.resolve() not in retained:
                sibling.unlink()
    return WhiteLabelConfig(
        logo_asset_path=str(processed.resolve()),
        original_logo_path=str(original.resolve()),
        original_filename=Path(original_filename or details.source.name).name,
        media_type="image/png",
        width=prepared.image.width,
        height=prepared.image.height,
        original_width=prepared.original_width,
        original_height=prepared.original_height,
        background_removal=mode,
        background_removal_status=prepared.status,
        background_confidence=prepared.confidence,
        scale_percent=scale,
        vertical_position=position,
        has_transparency=prepared.has_transparency,
        visible_bbox=prepared.visible_bbox,
        transparent_margin_percent=prepared.transparent_margin_percent,
        aspect_ratio=round(prepared.aspect_ratio, 6),
    )


def package_white_label_logo(config: WhiteLabelConfig, assets_dir: Path) -> str:
    details = inspect_white_label_logo(Path(config.logo_asset_path))
    destination_dir = assets_dir / "white-label"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "customer-logo.png"
    if details.suffix == ".png" and details.source.resolve() != destination.resolve():
        shutil.copy2(details.source, destination)
    elif details.suffix != ".png":
        with Image.open(details.source) as source:
            source.convert("RGBA").save(destination, format="PNG", optimize=True)
    return f"assets/white-label/{destination.name}"
