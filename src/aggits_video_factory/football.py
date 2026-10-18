"""Football roster and presentation; no network or publication side effects."""
from dataclasses import dataclass, asdict, field
from copy import deepcopy
from pathlib import Path
import hashlib
import re
import shutil

from PIL import Image, ImageChops


@dataclass(slots=True)
class FootballConfig:
    # Name, ticker, channel and reviewed videos use the owning Project fields.
    club_id: str = "north-melbourne"
    logo_asset: str = ""
    base_colour: str = "#081426"
    primary_colour: str = "#005EB8"
    highlight_colour: str = "#FFFFFF"
    cta_label: str = "Visit club"
    cta_url: str = ""
    membership_url: str = ""
    clubs: list[dict] = field(default_factory=list)

    def __post_init__(self):
        from .models import _optional_http_url
        from urllib.parse import urlparse
        self.membership_url = _optional_http_url(self.membership_url, "Membership URL") or ""
        if self.membership_url:
            parsed = urlparse(self.membership_url)
            if not parsed.hostname or parsed.username or parsed.password or re.search(r"[\s\\]", self.membership_url):
                raise ValueError("Membership URL must be a complete http or https URL without credentials or spaces.")
            try:
                parsed.port
            except ValueError as error:
                raise ValueError("Membership URL has an invalid port.") from error
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", self.club_id):
            raise ValueError("Club ID must use lowercase letters, numbers and hyphens.")
        for name in ("base_colour", "primary_colour", "highlight_colour"):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", getattr(self, name)):
                raise ValueError("Football colours must use #RRGGBB format.")
        if not self.cta_label.strip() or len(self.cta_label) > 40:
            raise ValueError("Football CTA label must contain 1–40 characters.")
        if self.cta_url:
            from .models import PrimaryCta, PrimaryCtaType
            PrimaryCta(PrimaryCtaType.CUSTOM, self.cta_url, custom_label=self.cta_label)
        if not isinstance(self.clubs, list) or len(self.clubs) > 18:
            raise ValueError("Football supports a maximum of 18 clubs.")
        ids = []
        for club in self.clubs:
            if not isinstance(club, dict) or not str(club.get("title", "")).strip():
                raise ValueError("Each Football club needs a name.")
            settings = club.get("settings", {})
            if not isinstance(settings, dict):
                raise ValueError("Club settings must be an object.")
            if settings.get("clubs"):
                raise ValueError("Nested Football rosters are not supported.")
            parsed = FootballConfig.from_dict(settings)
            ids.append(parsed.club_id)
            from .models import Video
            videos = [Video.from_dict(item) for item in club.get("videos", [])]
            excluded = set(club.get("excluded_video_ids", []))
            if len([v for v in videos if v.video_id not in excluded]) > 50:
                raise ValueError("Each club supports a maximum of 50 included videos.")
        if len(ids) != len(set(ids)):
            raise ValueError("Football club IDs must be unique.")
        if ids and self.club_id not in ids:
            raise ValueError("Selected club is not in the Football roster.")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Football configuration must be an object.")
        return cls(**{key: value[key] for key in cls.__dataclass_fields__ if key in value})


CLUB_FIELDS = ("title", "ticker_text", "channel_url", "source_channel_url", "channel_id",
               "channel_title", "channel_thumbnail", "manual_video_urls", "excluded_video_ids")


def club_record(project):
    record = {name: deepcopy(getattr(project, name)) for name in CLUB_FIELDS}
    record["videos"] = [video.to_dict() for video in project.videos]
    record["settings"] = {k: v for k, v in project.football_config.to_dict().items() if k != "clubs"}
    return record


def club_records(project):
    """Legacy top-level fields are the selected-club editing view, never another club."""
    records = deepcopy(project.football_config.clubs)
    selected = club_record(project)
    for index, record in enumerate(records):
        if record["settings"]["club_id"] == project.football_config.club_id:
            records[index] = selected
            break
    else:
        records.append(selected)
    return records


def persisted_config(project):
    value = project.football_config.to_dict()
    # Preserve old one-club serialization until a roster is explicitly edited.
    if value["clubs"]:
        value["clubs"] = club_records(project)
    FootballConfig.from_dict(value)
    return value


def select_club_project(project, record):
    from .models import Video
    selected = deepcopy(project)
    for key in CLUB_FIELDS:
        setattr(selected, key, deepcopy(record.get(key, [] if key.endswith("_ids") or key == "manual_video_urls" else "")))
    selected.videos = [Video.from_dict(item) for item in record.get("videos", [])]
    selected.football_config = FootballConfig.from_dict({**record["settings"], "clubs": club_records(project)})
    return selected


def import_club_logos(project, directory):
    records = club_records(project)
    for record in records:
        settings = record["settings"]
        settings["logo_asset"] = import_logo(settings.get("logo_asset", ""), directory)
        if settings["club_id"] == project.football_config.club_id:
            project.football_config.logo_asset = settings["logo_asset"]
    if project.football_config.clubs:
        project.football_config.clubs = records


def inspect_logo(path: Path):
    if path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Club logo must not exceed 5 MB.")
    try:
        with Image.open(path) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Club logo must be PNG, JPEG or WebP.")
            suffix = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[image.format]
            image.verify()
        with Image.open(path) as image:
            image.load()
        return suffix
    except (OSError, SyntaxError) as error:
        raise ValueError("Club logo could not be read.") from error


def logo_layout(path: Path):
    """Measure empty padding only; keep the original asset bytes unchanged.

    Opaque margins are ignored only when the entire outside border is one
    identical colour. Any uncertainty retains the complete original canvas.
    """
    with Image.open(path) as source:
        image = source.convert("RGBA")
        width, height = image.size
        alpha = image.getchannel("A")
        bounds = alpha.getbbox()
        if alpha.getextrema() == (255, 255):
            rgb = image.convert("RGB")
            background = rgb.getpixel((0, 0))
            difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, background))
            border = [difference.crop(box).getbbox() for box in (
                (0, 0, width, 1), (0, height-1, width, height),
                (0, 0, 1, height), (width-1, 0, width, height))]
            bounds = difference.getbbox() if not any(border) else (0, 0, width, height)
        if not bounds:
            bounds = (0, 0, width, height)
        # Retain a little blank safety margin around every edge of the mark.
        left, top, right, bottom = bounds
        left, top = max(0, left-2), max(0, top-2)
        right, bottom = min(width, right+2), min(height, bottom+2)
        return {"width": width, "height": height, "bounds": [left, top, right-left, bottom-top]}


def logo_source(reference: str, project_dir: Path) -> Path:
    path = Path(reference)
    if path.is_absolute():
        return path
    resolved = (project_dir / path).resolve()
    if not resolved.is_relative_to((project_dir / "assets").resolve()):
        raise ValueError("Club logo must be a project asset.")
    return resolved


def import_logo(reference: str, project_dir: Path) -> str:
    if not reference:
        return ""
    source = logo_source(reference, project_dir)
    suffix = inspect_logo(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    relative = f"assets/football-logo-{digest}{suffix}"
    target = project_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return relative


def package_football(project, destination: Path, videos: list) -> dict:
    persisted_config(project)  # Validate the complete roster, including programmatic edits.
    if project.football_config.clubs:
        from .site_builder import _reel_short_title
        clubs = []
        for record in club_records(project):
            selected = select_club_project(project, record)
            selected.football_config.clubs = []
            catalogue = []
            for video in selected.videos:
                if video.video_id in selected.excluded_video_ids:
                    continue
                catalogue.append({"id": video.video_id, "videoId": video.video_id,
                    "title": video.title, "displayTitle": video.display_title,
                    "shortTitle": _reel_short_title(video.title), "url": video.url,
                    "videoURL": video.url, "embedUrl": video.embed_url,
                    "thumbnailUrl": video.thumbnail_url, "reelImage": video.thumbnail_url,
                    "category": video.channel_title, "metadata": video.channel_title,
                    "description": video.display_title, "storyText": video.display_title})
            clubs.extend(package_football(selected, destination, catalogue)["clubs"])
        return {"clubs": clubs}
    config = project.football_config
    logo = ""
    layout = None
    if config.logo_asset:
        source = logo_source(config.logo_asset, destination.parent)
        if Path(config.logo_asset).is_absolute():
            raise ValueError("Import the club logo into the project before previewing.")
        inspect_logo(source)
        layout = logo_layout(source)
        logo = f"assets/{source.name}"
        shutil.copy2(source, destination / logo)
    return {"clubs": [{
        "id": config.club_id, "name": project.title,
        "logo": logo, "logoLayout": layout, "channelUrl": project.source_channel_url or project.channel_url,
        "ticker": project.ticker_text, "ctaLabel": config.cta_label, "ctaUrl": config.cta_url,
        "membershipUrl": config.membership_url,
        "baseColour": config.base_colour, "primaryColour": config.primary_colour,
        "highlightColour": config.highlight_colour, "videos": [v for v in videos if valid_player_video(v)],
    }]}


def valid_player_video(video):
    """Reject malformed/mismatched saved records without changing their source."""
    from .youtube_api import YouTubeClient
    identifier = str(video.get("videoId") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", identifier):
        return False
    from urllib.parse import urlparse
    for key in ("url", "videoURL", "embedUrl"):
        value = video.get(key)
        if value:
            try:
                parsed = urlparse(value)
                if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
                    return False
                if YouTubeClient.video_id_from_url(value) != identifier:
                    return False
            except (ValueError, TypeError):
                return False
    return True
