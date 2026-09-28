from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import MAX_CHANNEL_MASTER_INTRO_MP4_BYTES


INTRO_ASSET_PREFIX = "channel-master-intro-"


class ChannelMasterIntroError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ChannelMasterIntroInfo:
    file_size: int


def _mp4_atom_types(path: Path) -> set[bytes]:
    """Read top-level ISO base-media atoms without trusting the extension."""
    atom_types: set[bytes] = set()
    size = path.stat().st_size
    with path.open("rb") as source:
        offset = 0
        while offset + 8 <= size:
            source.seek(offset)
            header = source.read(8)
            if len(header) != 8:
                break
            atom_size = int.from_bytes(header[:4], "big")
            atom_type = header[4:8]
            header_size = 8
            if atom_size == 1:
                extended = source.read(8)
                if len(extended) != 8:
                    raise ChannelMasterIntroError("INTRO MP4 COULD NOT BE READ.")
                atom_size = int.from_bytes(extended, "big")
                header_size = 16
            elif atom_size == 0:
                atom_size = size - offset
            if atom_size < header_size or offset + atom_size > size:
                raise ChannelMasterIntroError("INTRO MP4 COULD NOT BE READ.")
            atom_types.add(atom_type)
            offset += atom_size
    return atom_types


def inspect_intro_mp4(source: Path) -> ChannelMasterIntroInfo:
    path = Path(source)
    if not path.is_file():
        raise ChannelMasterIntroError("INTRO MP4 COULD NOT BE READ.")
    if path.suffix.casefold() != ".mp4":
        raise ChannelMasterIntroError("INTRO VIDEO MUST BE AN MP4 FILE.")
    file_size = path.stat().st_size
    if file_size <= 0:
        raise ChannelMasterIntroError("INTRO MP4 COULD NOT BE READ.")
    if file_size > MAX_CHANNEL_MASTER_INTRO_MP4_BYTES:
        raise ChannelMasterIntroError(
            f"INTRO MP4 EXCEEDS THE {MAX_CHANNEL_MASTER_INTRO_MP4_BYTES // (1024 * 1024)} MB MAXIMUM FILE SIZE."
        )
    try:
        atom_types = _mp4_atom_types(path)
    except OSError as error:
        raise ChannelMasterIntroError("INTRO MP4 COULD NOT BE READ.") from error
    if not {b"ftyp", b"moov", b"mdat"}.issubset(atom_types):
        raise ChannelMasterIntroError("INTRO MP4 COULD NOT BE READ.")
    return ChannelMasterIntroInfo(file_size=file_size)


def _resolve_project_reference(reference: str, project_directory: Path) -> Path:
    normalised = str(reference or "").strip().replace("\\", "/")
    if not normalised.startswith(f"assets/{INTRO_ASSET_PREFIX}") or not normalised.endswith(".mp4"):
        raise ChannelMasterIntroError("Stored Intro MP4 reference is invalid.")
    project_root = Path(project_directory).resolve()
    source = (project_root / normalised).resolve()
    if source.parent != (project_root / "assets").resolve():
        raise ChannelMasterIntroError("Stored Intro MP4 reference is invalid.")
    return source


def _remove_intro_assets(project_directory: Path, *, keep: Path | None = None) -> None:
    assets = Path(project_directory) / "assets"
    if not assets.is_dir():
        return
    keep_resolved = keep.resolve() if keep else None
    for candidate in assets.glob(f"{INTRO_ASSET_PREFIX}*.mp4"):
        if keep_resolved is None or candidate.resolve() != keep_resolved:
            candidate.unlink(missing_ok=True)


def materialize_intro_mp4(reference: str, project_directory: Path) -> str:
    project_directory = Path(project_directory)
    raw = str(reference or "").strip()
    if not raw:
        _remove_intro_assets(project_directory)
        return ""
    source = Path(raw)
    if not source.is_absolute():
        source = _resolve_project_reference(raw, project_directory)
    info = inspect_intro_mp4(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    relative = Path("assets") / f"{INTRO_ASSET_PREFIX}{digest}.mp4"
    destination = project_directory / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        temporary = destination.with_suffix(".mp4.tmp")
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    if destination.stat().st_size != info.file_size:
        destination.unlink(missing_ok=True)
        raise ChannelMasterIntroError("INTRO MP4 COULD NOT BE COPIED.")
    _remove_intro_assets(project_directory, keep=destination)
    return relative.as_posix()


def package_intro_mp4(reference: str, project_directory: Path, site_directory: Path) -> tuple[str, int]:
    source = _resolve_project_reference(reference, project_directory)
    info = inspect_intro_mp4(source)
    output = Path(site_directory) / "assets" / "channel-master-intro"
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.mp4"):
        stale.unlink(missing_ok=True)
    destination = output / source.name
    shutil.copy2(source, destination)
    return f"assets/channel-master-intro/{source.name}", info.file_size
