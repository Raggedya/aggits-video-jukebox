from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import resource_path


SOCIAL_PREVIEW_SIZE = (1200, 630)
SOCIAL_PREVIEW_VERSION = "v2"
BANJO_SOCIAL_PREVIEW_SIZE = (1731, 909)
BANJO_SOCIAL_PREVIEW_VERSION = "banjo-v1"
BANJO_SOCIAL_PREVIEW_RESOURCE = "templates/social-preview/banjo-world-of-cars-social-preview.png"
BANJO_SOCIAL_PREVIEW_SHA256 = "6274661228cf248d4b27f701823752197d863cad2fb88b6c209674ef0fa1fbe2"
TITLE_SAFE_REGION = (110, 132, 1090, 370)
TOUCH_ICON_BOUNDS = (558, 394, 642, 496)
TITLE_FILL = "#f3ede0"
TITLE_EDGE = "#8c846f"
TITLE_SHADOW = "#010205"
VIGNETTE_CENTER = "#111f31"
VIGNETTE_EDGE = "#010307"
TOUCH_FILL = "#e9e1d1"
TOUCH_MUTED = "#817b6d"


@dataclass(frozen=True, slots=True)
class TitleLayout:
    lines: tuple[str, ...]
    font_size: int
    bounds: tuple[int, int, int, int]


def normalise_social_title(title: str | None) -> str:
    """Return the stored title with only insignificant whitespace normalised."""
    return re.sub(r"\s+", " ", str(title or "").strip())


def _is_banjo(project_type: object | None) -> bool:
    return str(getattr(project_type, "value", project_type) or "").lower() == "banjo"


def social_preview_filename(title: str | None, project_type: object | None = None) -> str:
    if _is_banjo(project_type):
        return f"social-card-{BANJO_SOCIAL_PREVIEW_VERSION}-{BANJO_SOCIAL_PREVIEW_SHA256[:12]}.png"
    source = f"{SOCIAL_PREVIEW_VERSION}\0{normalise_social_title(title)}".encode("utf-8")
    digest = hashlib.sha256(source).hexdigest()[:12]
    return f"social-card-{SOCIAL_PREVIEW_VERSION}-{digest}.jpg"


def verify_banjo_social_preview(path: Path | None = None) -> Path:
    source = path or resource_path(BANJO_SOCIAL_PREVIEW_RESOURCE)
    if not source.is_file():
        raise FileNotFoundError(f"Approved Banjo social-preview image is missing: {source}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != BANJO_SOCIAL_PREVIEW_SHA256:
        raise ValueError("Approved Banjo social-preview image hash does not match the canonical asset.")
    with Image.open(source) as image:
        if image.format != "PNG" or image.size != BANJO_SOCIAL_PREVIEW_SIZE:
            raise ValueError(
                "Approved Banjo social-preview image must remain the canonical "
                f"{BANJO_SOCIAL_PREVIEW_SIZE[0]}x{BANJO_SOCIAL_PREVIEW_SIZE[1]} PNG."
            )
    return source


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/georgiab.ttf"),
        Path("C:/Windows/Fonts/timesbd.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    try:
        return ImageFont.truetype("DejaVuSerif-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _candidate_lines(words: list[str], line_count: int) -> list[tuple[str, ...]]:
    if line_count == 1:
        return [(" ".join(words),)] if words else []
    if len(words) < line_count:
        return []
    candidates: list[tuple[str, ...]] = []
    for cuts in combinations(range(1, len(words)), line_count - 1):
        boundaries = (0, *cuts, len(words))
        candidates.append(tuple(" ".join(words[boundaries[index]:boundaries[index + 1]]) for index in range(line_count)))
    return candidates


def _line_metrics(draw: ImageDraw.ImageDraw, lines: tuple[str, ...], font: ImageFont.ImageFont) -> tuple[list[int], list[int]]:
    widths: list[int] = []
    heights: list[int] = []
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font, stroke_width=1)
        widths.append(box[2] - box[0])
        heights.append(box[3] - box[1])
    return widths, heights


def fit_social_title(draw: ImageDraw.ImageDraw, title: str | None) -> TitleLayout:
    value = normalise_social_title(title)
    if not value:
        centre_x = SOCIAL_PREVIEW_SIZE[0] // 2
        centre_y = (TITLE_SAFE_REGION[1] + TITLE_SAFE_REGION[3]) // 2
        return TitleLayout(lines=(), font_size=0, bounds=(centre_x, centre_y, centre_x, centre_y))

    words = value.split()
    left, top, right, bottom = TITLE_SAFE_REGION
    max_width = right - left
    max_height = bottom - top - 8
    strategies = (
        (1, 118, 68, 0),
        (2, 88, 28, 10),
    )
    for line_count, maximum, minimum, spacing in strategies:
        candidates = _candidate_lines(words, line_count)
        for size in range(maximum, minimum - 1, -1):
            font = _font(size)
            fitting: list[tuple[int, tuple[str, ...], list[int], list[int]]] = []
            for lines in candidates:
                widths, heights = _line_metrics(draw, lines, font)
                total_height = sum(heights) + spacing * (len(lines) - 1)
                if max(widths) <= max_width and total_height <= max_height:
                    balance = max(widths) - min(widths)
                    fitting.append((balance, lines, widths, heights))
            if fitting:
                _, lines, widths, heights = min(fitting, key=lambda item: (item[0], max(item[2])))
                total_height = sum(heights) + spacing * (len(lines) - 1)
                block_top = top + (max_height - total_height) // 2
                widest = max(widths)
                block_left = (SOCIAL_PREVIEW_SIZE[0] - widest) // 2
                return TitleLayout(lines=lines, font_size=size, bounds=(block_left, block_top, block_left + widest, block_top + total_height))

    # Divide an unusually long unbroken title deterministically instead of cropping it.
    for line_count in (2,):
        chunk_size = (len(value) + line_count - 1) // line_count
        lines = tuple(value[index:index + chunk_size] for index in range(0, len(value), chunk_size))
        if len(lines) > line_count:
            continue
        for size in range(33, 17, -1):
            font = _font(size)
            widths, heights = _line_metrics(draw, lines, font)
            spacing = 10
            total_height = sum(heights) + spacing * (len(lines) - 1)
            if max(widths) <= max_width and total_height <= max_height:
                widest = max(widths)
                block_left = (SOCIAL_PREVIEW_SIZE[0] - widest) // 2
                block_top = top + (max_height - total_height) // 2
                return TitleLayout(lines=lines, font_size=size, bounds=(block_left, block_top, block_left + widest, block_top + total_height))

    # Project title validation should make this unreachable. A blank title is safer
    # than introducing branding or placeholder copy into the minimal card.
    centre_x = SOCIAL_PREVIEW_SIZE[0] // 2
    centre_y = (top + bottom) // 2
    return TitleLayout(lines=(), font_size=0, bounds=(centre_x, centre_y, centre_x, centre_y))


def _draw_fitted_title(canvas: Image.Image, title: str | None) -> TitleLayout:
    draw = ImageDraw.Draw(canvas)
    layout = fit_social_title(draw, title)
    if not layout.lines:
        return layout

    font = _font(layout.font_size)
    left, top, right, bottom = TITLE_SAFE_REGION
    _, heights = _line_metrics(draw, layout.lines, font)
    spacing = 10 if len(layout.lines) == 2 else 0
    total_height = sum(heights) + spacing * (len(layout.lines) - 1)
    y = top + (bottom - top - total_height) // 2
    rendered_left = right
    rendered_right = left
    for line, height in zip(layout.lines, heights):
        box = draw.textbbox((0, 0), line, font=font, stroke_width=1)
        width = box[2] - box[0]
        x = (canvas.width - width) // 2 - box[0]
        draw.text((x + 4, y + 5), line, font=font, fill=TITLE_SHADOW, stroke_width=2, stroke_fill=TITLE_SHADOW)
        draw.text((x, y), line, font=font, fill=TITLE_FILL, stroke_width=1, stroke_fill=TITLE_EDGE)
        rendered_left = min(rendered_left, x - 1)
        rendered_right = max(rendered_right, x + width + 6)
        y += height + spacing
    return TitleLayout(
        lines=layout.lines,
        font_size=layout.font_size,
        bounds=(rendered_left, top + (bottom - top - total_height) // 2, rendered_right, y - spacing + 5),
    )


def _create_luxe_background() -> Image.Image:
    """Create the deterministic midnight-blue elliptical vignette."""
    gradient = Image.radial_gradient("L").resize(SOCIAL_PREVIEW_SIZE, Image.Resampling.LANCZOS)
    return ImageOps.colorize(gradient, black=VIGNETTE_CENTER, white=VIGNETTE_EDGE).convert("RGB")


def _draw_touch_icon(canvas: Image.Image) -> None:
    """Draw a restrained static finger/target affordance without external assets."""
    left, top, right, bottom = TOUCH_ICON_BOUNDS
    scale = 4
    width = (right - left) * scale
    height = (bottom - top) * scale
    icon = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)

    def xy(x: float, y: float) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    centre_x, centre_y = 42, 20
    for radius, colour, line_width in ((18, TOUCH_MUTED, 1.5), (10, TOUCH_FILL, 1.4)):
        cx, cy = xy(centre_x, centre_y)
        r = round(radius * scale)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=colour, width=max(1, round(line_width * scale)))
    cx, cy = xy(centre_x, centre_y)
    point_radius = round(2.3 * scale)
    draw.ellipse((cx - point_radius, cy - point_radius, cx + point_radius, cy + point_radius), fill=TOUCH_FILL)

    # The hand follows the same finger-press silhouette used by the live machine,
    # simplified into a small static line icon for reliable raster rendering.
    hand_points = [
        xy(42, 22), xy(42, 61), xy(34, 53), xy(29, 52), xy(25, 55),
        xy(24, 60), xy(27, 65), xy(40, 82), xy(47, 88), xy(61, 88),
        xy(69, 82), xy(72, 73), xy(72, 57), xy(69, 53), xy(64, 52),
        xy(60, 55), xy(59, 49), xy(55, 46), xy(50, 47), xy(47, 51),
        xy(47, 25), xy(45, 22),
    ]
    dark_fill = (7, 13, 22, 245)
    draw.polygon(hand_points, fill=dark_fill)
    draw.line(hand_points + [hand_points[0]], fill=TOUCH_FILL, width=round(2.3 * scale), joint="curve")
    draw.line([xy(59, 55), xy(59, 67)], fill=TOUCH_MUTED, width=round(1.2 * scale))
    draw.line([xy(48, 51), xy(48, 67)], fill=TOUCH_MUTED, width=round(1.2 * scale))

    icon = icon.resize((right - left, bottom - top), Image.Resampling.LANCZOS)
    canvas.paste(icon, (left, top), icon)


def create_social_preview(title: str | None, destination: Path) -> TitleLayout:
    canvas = _create_luxe_background()
    layout = _draw_fitted_title(canvas, title)
    _draw_touch_icon(canvas)

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Baseline JPEG maximises compatibility with conservative social crawlers.
    canvas.save(destination, format="JPEG", quality=92, optimize=True, progressive=False)
    return layout


def replace_social_preview(
    title: str | None,
    directory: Path,
    project_type: object | None = None,
) -> Path:
    filename = social_preview_filename(title, project_type)
    destination = directory / filename
    for existing in directory.glob("social-card-*"):
        if existing.name != filename and existing.is_file():
            existing.unlink()
    if _is_banjo(project_type):
        source = verify_banjo_social_preview()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    else:
        create_social_preview(title, destination)
    return destination
