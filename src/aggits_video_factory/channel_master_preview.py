from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import shutil

from PIL import Image, UnidentifiedImageError


MAX_URL_PREVIEW_IMAGE_BYTES = 5 * 1024 * 1024
URL_PREVIEW_ASSET_PREFIX = "channel-master-url-preview-"

_FORMAT_DETAILS = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "WEBP": (".webp", "image/webp"),
}
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True, slots=True)
class UrlPreviewImageInfo:
    path: Path
    width: int
    height: int
    file_size: int
    media_type: str
    extension: str
    digest: str

    @property
    def asset_filename(self) -> str:
        return f"{URL_PREVIEW_ASSET_PREFIX}{self.digest[:16]}{self.extension}"


def inspect_url_preview_image(path: Path) -> UrlPreviewImageInfo:
    """Validate a real Channel Master social image without transforming it."""
    source = Path(path)
    if source.suffix.casefold() not in _ALLOWED_SUFFIXES:
        raise ValueError("PREVIEW IMAGE MUST BE PNG, JPG, JPEG OR WEBP.")
    try:
        file_size = source.stat().st_size
    except OSError as error:
        raise ValueError("PREVIEW IMAGE COULD NOT BE READ.") from error
    if file_size > MAX_URL_PREVIEW_IMAGE_BYTES:
        raise ValueError("PREVIEW IMAGE EXCEEDS THE MAXIMUM FILE SIZE.")
    if file_size <= 0:
        raise ValueError("PREVIEW IMAGE COULD NOT BE READ.")
    try:
        with Image.open(source) as image:
            image.verify()
        with Image.open(source) as image:
            image.load()
            image_format = str(image.format or "").upper()
            width, height = image.size
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise ValueError("PREVIEW IMAGE COULD NOT BE READ.") from error
    if image_format not in _FORMAT_DETAILS or width <= 0 or height <= 0:
        raise ValueError("PREVIEW IMAGE MUST BE PNG, JPG, JPEG OR WEBP.")
    extension, media_type = _FORMAT_DETAILS[image_format]
    if image_format == "JPEG" and source.suffix.casefold() not in {".jpg", ".jpeg"}:
        raise ValueError("PREVIEW IMAGE MUST BE PNG, JPG, JPEG OR WEBP.")
    if image_format != "JPEG" and source.suffix.casefold() != extension:
        raise ValueError("PREVIEW IMAGE MUST BE PNG, JPG, JPEG OR WEBP.")
    digest = sha256(source.read_bytes()).hexdigest()
    return UrlPreviewImageInfo(
        path=source,
        width=width,
        height=height,
        file_size=file_size,
        media_type=media_type,
        extension=extension,
        digest=digest,
    )


def _remove_old_assets(asset_dir: Path, keep: Path | None = None) -> None:
    if not asset_dir.is_dir():
        return
    keep_resolved = keep.resolve() if keep else None
    for candidate in asset_dir.glob(f"{URL_PREVIEW_ASSET_PREFIX}*"):
        if not candidate.is_file():
            continue
        if keep_resolved is not None and candidate.resolve() == keep_resolved:
            continue
        candidate.unlink()


def materialize_url_preview_image(reference: str, project_dir: Path) -> str:
    """Copy an operator selection into project-owned assets using its content hash."""
    raw = str(reference or "").strip()
    asset_dir = Path(project_dir) / "assets"
    if not raw:
        _remove_old_assets(asset_dir)
        return ""
    source = Path(raw)
    info = (
        inspect_url_preview_image(source)
        if source.is_absolute()
        else resolve_project_url_preview_image(raw, project_dir)
    )
    source = info.path
    asset_dir.mkdir(parents=True, exist_ok=True)
    destination = asset_dir / info.asset_filename
    if source.resolve() != destination.resolve():
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    _remove_old_assets(asset_dir, keep=destination)
    return (Path("assets") / destination.name).as_posix()


def resolve_project_url_preview_image(reference: str, project_dir: Path) -> UrlPreviewImageInfo:
    """Resolve only a project-controlled Channel Master preview asset."""
    relative = Path(str(reference or "").replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("PREVIEW IMAGE PROJECT REFERENCE IS INVALID.")
    if len(relative.parts) != 2 or relative.parts[0] != "assets":
        raise ValueError("PREVIEW IMAGE PROJECT REFERENCE IS INVALID.")
    if not relative.name.startswith(URL_PREVIEW_ASSET_PREFIX):
        raise ValueError("PREVIEW IMAGE PROJECT REFERENCE IS INVALID.")
    root = Path(project_dir).resolve()
    source = (root / relative).resolve()
    if source.parent != (root / "assets").resolve():
        raise ValueError("PREVIEW IMAGE PROJECT REFERENCE IS INVALID.")
    return inspect_url_preview_image(source)


def package_url_preview_image(reference: str, project_dir: Path, site_dir: Path) -> UrlPreviewImageInfo:
    """Publish the project-owned original beside the generated machine HTML."""
    info = resolve_project_url_preview_image(reference, project_dir)
    destination = Path(site_dir) / info.asset_filename
    Path(site_dir).mkdir(parents=True, exist_ok=True)
    if info.path.resolve() != destination.resolve():
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(info.path, temporary)
        temporary.replace(destination)
    _remove_old_assets(Path(site_dir), keep=destination)
    return UrlPreviewImageInfo(
        path=destination,
        width=info.width,
        height=info.height,
        file_size=info.file_size,
        media_type=info.media_type,
        extension=info.extension,
        digest=info.digest,
    )


def remove_packaged_url_preview_images(site_dir: Path) -> None:
    """Remove stale Channel Master custom previews when the option is cleared."""
    _remove_old_assets(Path(site_dir))
