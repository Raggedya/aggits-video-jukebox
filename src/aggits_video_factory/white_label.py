from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .models import WhiteLabelConfig


MAX_WHITE_LABEL_LOGO_BYTES = 5 * 1024 * 1024
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
            bands = image.getbands()
            transparency = "A" in bands or "transparency" in image.info
    except (OSError, ValueError) as error:
        raise ValueError("The selected customer logo is not a readable image.") from error
    if image_format not in ALLOWED_WHITE_LABEL_LOGO_FORMATS:
        raise ValueError("Customer logos must be PNG, JPEG or WebP images.")
    if width < 1 or height < 1 or width > 12000 or height > 12000:
        raise ValueError("The customer logo dimensions are not supported.")
    suffix, media_type = ALLOWED_WHITE_LABEL_LOGO_FORMATS[image_format]
    return WhiteLabelLogoDetails(source, suffix, media_type, width, height, transparency)


def materialize_white_label_logo(source_path: str, project_dir: Path) -> WhiteLabelConfig:
    details = inspect_white_label_logo(Path(source_path))
    branding_dir = project_dir / "white-label"
    branding_dir.mkdir(parents=True, exist_ok=True)
    destination = branding_dir / f"customer-logo{details.suffix}"
    if details.source.resolve() != destination.resolve():
        temporary = branding_dir / f".customer-logo{details.suffix}.tmp"
        shutil.copy2(details.source, temporary)
        temporary.replace(destination)
    for sibling in branding_dir.glob("customer-logo.*"):
        if sibling != destination and sibling.is_file():
            sibling.unlink()
    return WhiteLabelConfig(
        logo_asset_path=str(destination.resolve()),
        original_filename=details.source.name,
        media_type=details.media_type,
        width=details.width,
        height=details.height,
    )


def package_white_label_logo(config: WhiteLabelConfig, assets_dir: Path) -> str:
    details = inspect_white_label_logo(Path(config.logo_asset_path))
    destination_dir = assets_dir / "white-label"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"customer-logo{details.suffix}"
    if details.source.resolve() != destination.resolve():
        shutil.copy2(details.source, destination)
    return f"assets/white-label/{destination.name}"
