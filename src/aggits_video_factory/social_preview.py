from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import resource_path


SOCIAL_PREVIEW_SIZE = (1200, 630)
SOCIAL_PREVIEW_TEMPLATE = "templates/social-preview/crispy-bits-social-preview-template.png"
SOCIAL_PREVIEW_VERSION = "v1"
TITLE_SAFE_REGION = (120, 166, 1080, 306)
TITLE_FILL = "#f6e8c8"
TITLE_GOLD = "#b98235"
TITLE_SHADOW = "#050403"


@dataclass(frozen=True, slots=True)
class TitleLayout:
    lines: tuple[str, ...]
    font_size: int
    bounds: tuple[int, int, int, int]


def normalise_social_title(title: str | None) -> str:
    cleaned = re.sub(r"\s+", " ", str(title or "").strip())
    return (cleaned or "CRISPY BITS").upper()


def social_preview_filename(title: str | None) -> str:
    source = f"{SOCIAL_PREVIEW_VERSION}\0{normalise_social_title(title)}".encode("utf-8")
    digest = hashlib.sha256(source).hexdigest()[:12]
    return f"social-card-{SOCIAL_PREVIEW_VERSION}-{digest}.jpg"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/ariblk.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _candidate_lines(words: list[str], line_count: int) -> list[tuple[str, ...]]:
    if line_count == 1:
        return [(" ".join(words),)]
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
        box = draw.textbbox((0, 0), line, font=font, stroke_width=2)
        widths.append(box[2] - box[0])
        heights.append(box[3] - box[1])
    return widths, heights


def fit_social_title(draw: ImageDraw.ImageDraw, title: str | None) -> TitleLayout:
    value = normalise_social_title(title)
    words = value.split()
    left, top, right, bottom = TITLE_SAFE_REGION
    max_width = right - left
    # Reserve room for the restrained dimensional shadow inside the safe area.
    max_height = bottom - top - 8
    strategies = (
        (1, 104, 68, 0),
        (2, 78, 43, 7),
        (3, 56, 32, 4),
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

    # An unusually long unbroken title is divided deterministically rather than cropped.
    for line_count in (2, 3):
        chunk_size = (len(value) + line_count - 1) // line_count
        lines = tuple(value[index:index + chunk_size] for index in range(0, len(value), chunk_size))
        if len(lines) > line_count:
            continue
        for size in range(31, 17, -1):
            font = _font(size)
            widths, heights = _line_metrics(draw, lines, font)
            spacing = 7 if line_count == 2 else 4
            total_height = sum(heights) + spacing * (len(lines) - 1)
            if max(widths) <= max_width and total_height <= max_height:
                widest = max(widths)
                block_left = (SOCIAL_PREVIEW_SIZE[0] - widest) // 2
                block_top = top + (max_height - total_height) // 2
                return TitleLayout(lines=lines, font_size=size, bounds=(block_left, block_top, block_left + widest, block_top + total_height))

    # The desktop title limit makes this unreachable, but keep a valid safe fallback.
    return fit_social_title(draw, "CRISPY BITS")


def _draw_fitted_title(canvas: Image.Image, title: str | None) -> TitleLayout:
    draw = ImageDraw.Draw(canvas)
    layout = fit_social_title(draw, title)
    font = _font(layout.font_size)
    left, top, right, bottom = TITLE_SAFE_REGION
    _, heights = _line_metrics(draw, layout.lines, font)
    spacing = 7 if len(layout.lines) == 2 else 4 if len(layout.lines) == 3 else 0
    total_height = sum(heights) + spacing * (len(layout.lines) - 1)
    y = top + (bottom - top - total_height) // 2
    rendered_left = right
    rendered_right = left
    for line, height in zip(layout.lines, heights):
        box = draw.textbbox((0, 0), line, font=font, stroke_width=2)
        width = box[2] - box[0]
        x = (canvas.width - width) // 2 - box[0]
        draw.text((x + 7, y + 8), line, font=font, fill=TITLE_SHADOW, stroke_width=4, stroke_fill=TITLE_SHADOW)
        draw.text((x + 3, y + 4), line, font=font, fill="#8b5a23", stroke_width=3, stroke_fill="#241509")
        draw.text((x, y), line, font=font, fill=TITLE_FILL, stroke_width=2, stroke_fill=TITLE_GOLD)
        rendered_left = min(rendered_left, x - 2)
        rendered_right = max(rendered_right, x + width + 11)
        y += height + spacing
    return TitleLayout(
        lines=layout.lines,
        font_size=layout.font_size,
        bounds=(rendered_left, top + (bottom - top - total_height) // 2, rendered_right, y - spacing + 8),
    )


def _generic_template() -> Image.Image:
    canvas = Image.new("RGB", SOCIAL_PREVIEW_SIZE, "#060504")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((338, 28, 862, 132), radius=34, fill="#0d3b30", outline=TITLE_GOLD, width=5)
    brand_font = _font(55)
    draw.text((600, 80), "CRISPY BITS", anchor="mm", font=brand_font, fill=TITLE_FILL, stroke_width=2, stroke_fill=TITLE_GOLD)
    draw.line((110, 158, 1090, 158), fill=TITLE_GOLD, width=3)
    draw.line((110, 314, 1090, 314), fill=TITLE_GOLD, width=3)
    draw.ellipse((450, 345, 750, 575), fill="#8b0710", outline="#d39b3f", width=14)
    press_font = _font(56)
    draw.text((600, 448), "PRESS", anchor="mm", font=press_font, fill=TITLE_FILL, stroke_width=2, stroke_fill="#5a170d")
    hit_font = _font(28)
    draw.text((600, 604), "HIT IT", anchor="mm", font=hit_font, fill=TITLE_FILL)
    return canvas


def create_social_preview(title: str | None, destination: Path) -> TitleLayout:
    try:
        template = Image.open(resource_path(SOCIAL_PREVIEW_TEMPLATE)).convert("RGB")
        canvas = ImageOps.fit(template, SOCIAL_PREVIEW_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    except (OSError, ValueError):
        canvas = _generic_template()

    try:
        layout = _draw_fitted_title(canvas, title)
    except (OSError, ValueError):
        canvas = _generic_template()
        layout = _draw_fitted_title(canvas, "CRISPY BITS")

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Baseline JPEG maximises compatibility with conservative social crawlers.
    canvas.save(destination, format="JPEG", quality=92, optimize=True, progressive=False)
    return layout


def replace_social_preview(title: str | None, directory: Path) -> Path:
    filename = social_preview_filename(title)
    destination = directory / filename
    for existing in directory.glob("social-card-*.jpg"):
        if existing.name != filename and existing.is_file():
            existing.unlink()
    create_social_preview(title, destination)
    return destination
