from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from qrcode.constants import ERROR_CORRECT_H

from .config import BRAND_NAME, PUBLIC_BASE_URL, resource_path
from .models import Project


BRASS = "#b88a4f"
DEEP_BRASS = "#4c3219"
CREAM = "#f2e4bf"
INK = "#070605"


def _story_sections(source: str, customer_name: str) -> list[dict[str, str]]:
    """Turn approved customer copy into readable story beats without adding facts."""
    cleaned = re.sub(r"\*{2,}[^*]+\*{2,}", " ", source or "")
    cleaned = re.sub(r"(\b(?:19|20)\d{2})\s+where\s+", r"\1. ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+I was promoted\b", ". I was promoted", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("; ", ". ")
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", re.sub(r"\s+", " ", cleaned).strip())
        if sentence.strip()
    ]
    fallback_headings = ["THE BEGINNING", "THE JOURNEY", "THE EXPERIENCE", "THE IDEA", "THE WORK", "THE APPROACH"]
    sections: list[dict[str, str]] = []
    for index, sentence in enumerate(sentences[:10]):
        years = re.findall(r"\b(?:19|20)\d{2}\b", sentence)
        lowered = sentence.casefold()
        if years:
            heading = years[-1]
        elif "promoted" in lowered:
            heading = "TEAM LEADERSHIP"
        elif "main aim" in lowered:
            heading = "THE AIM"
        elif "custom build" in lowered:
            heading = "CUSTOM BUILDS"
        elif "technology" in lowered:
            heading = "THE APPROACH"
        elif "customer" in lowered:
            heading = "CUSTOMER FIRST"
        else:
            heading = fallback_headings[min(index, len(fallback_headings) - 1)]
        sections.append({"heading": heading, "text": sentence})
    if not sections:
        sections.append({"heading": customer_name.upper(), "text": "Pull the lever and discover the story."})
    return sections


def _font(size: int, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: list[Path] = []
    if serif:
        candidates.extend([Path("C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf")])
    else:
        candidates.extend([
            Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        ])
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, minimum: int, *, serif: bool = False) -> ImageFont.ImageFont:
    for size in range(start_size, minimum - 1, -2):
        font = _font(size, bold=True, serif=serif)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
    return _font(minimum, bold=True, serif=serif)


def create_qr_card(project: Project, destination: Path) -> None:
    public_url = project.published_url or f"{PUBLIC_BASE_URL}/{project.slug}/"
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H, box_size=12, border=4)
    qr.add_data(public_url)
    qr.make(fit=True)
    template_path = resource_path("static/music-machine/crispy-bits-qr-template.png")
    canvas = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    code_size = 870
    qr_image = qr.make_image(fill_color="#102a22", back_color="#f4ead1").convert("RGB")
    qr_image = qr_image.resize((code_size, code_size), Image.Resampling.NEAREST)
    code_left = (canvas.width - code_size) // 2
    code_top = 170
    canvas.paste(qr_image, (code_left, code_top))

    plaque_width, plaque_height = 350, 154
    plaque_left = (canvas.width - plaque_width) // 2
    plaque_top = code_top + (code_size - plaque_height) // 2
    plaque = (plaque_left, plaque_top, plaque_left + plaque_width, plaque_top + plaque_height)
    draw.rounded_rectangle(plaque, radius=22, fill="#f4ead1", outline="#a9772d", width=5)
    draw.line((plaque_left + 34, plaque_top + 31, plaque_left + plaque_width - 34, plaque_top + 31), fill="#a9772d", width=2)
    title = project.title.upper()[:54]
    title_font = _fit_text(draw, title, plaque_width - 48, 48, 20, serif=True)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((canvas.width - (title_box[2] - title_box[0])) / 2, plaque_top + 46), title, font=title_font, fill="#102a22")
    star_x, star_y = canvas.width / 2, plaque_top + plaque_height - 23
    draw.polygon([
        (star_x, star_y - 11), (star_x + 3, star_y - 3), (star_x + 11, star_y), (star_x + 3, star_y + 3),
        (star_x, star_y + 11), (star_x - 3, star_y + 3), (star_x - 11, star_y), (star_x - 3, star_y - 3),
    ], fill="#a9772d")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", optimize=True)


def create_social_card(project: Project, destination: Path) -> None:
    background = Image.new("RGB", (1200, 630), INK)
    cabinet_path = resource_path("static/music-machine/aggits-cabinet.webp")
    if cabinet_path.is_file():
        cabinet = Image.open(cabinet_path).convert("RGB")
        cabinet = ImageOps.fit(cabinet, (470, 705), centering=(0.5, 0.28))
        cabinet = ImageEnhance.Color(cabinet).enhance(0.15)
        cabinet = ImageEnhance.Contrast(cabinet).enhance(1.14)
        cabinet = ImageEnhance.Brightness(cabinet).enhance(0.72)
        cabinet = cabinet.filter(ImageFilter.GaussianBlur(0.25))
        background.paste(cabinet, (40, -38))
    draw = ImageDraw.Draw(background)
    draw.rectangle((500, 0, 1200, 630), fill="#090806")
    draw.line((548, 116, 1136, 116), fill=BRASS, width=3)
    draw.text((548, 66), f"{BRAND_NAME} VIDEO JUKEBOX", font=_font(24, bold=True, serif=True), fill=BRASS)
    title = project.title.upper()
    font = _fit_text(draw, title, 590, 78, 42, serif=True)
    draw.multiline_text((548, 166), title, font=font, fill=CREAM, spacing=10)
    draw.text((548, 430), f"{len(project.videos)} VIDEOS · ONE MECHANICAL REEL", font=_font(25, bold=True), fill="#d8bd82")
    draw.text((548, 484), "PULL · SELECT · WATCH", font=_font(22, bold=True), fill="#987044")
    draw.rounded_rectangle((548, 544, 800, 592), radius=12, outline=BRASS, width=2)
    draw.text((674, 568), "WATCH ON YOUTUBE", font=_font(18, bold=True), fill=CREAM, anchor="mm")
    destination.parent.mkdir(parents=True, exist_ok=True)
    background.save(destination, format="JPEG", quality=91, optimize=True)


def build_project_site(project: Project, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    assets = destination / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(resource_path("static"), assets)

    canonical = project.published_url or f"{PUBLIC_BASE_URL}/{project.slug}/"
    social_url = f"{canonical.rstrip('/')}/social-card.jpg"
    description = f"Pull the CRISPY BITS reel and discover one of {len(project.videos)} videos from {project.title}."
    story_sections = _story_sections(project.ticker_text, project.title)
    replacements = {
        "{{META_DESCRIPTION}}": html.escape(description, quote=True),
        "{{CANONICAL_URL}}": html.escape(canonical, quote=True),
        "{{SOCIAL_IMAGE_URL}}": html.escape(social_url, quote=True),
        "{{PAGE_TITLE}}": html.escape(f"{project.title} — CRISPY BITS Video Jukebox"),
        "{{MACHINE_LABEL}}": html.escape(f"{project.title} CRISPY BITS Video Jukebox", quote=True),
        "{{MACHINE_TITLE}}": html.escape(project.title),
        "{{TICKER_TEXT}}": html.escape(project.ticker_text or "PULL FOR A VIDEO"),
    }
    template = resource_path("templates/machine.html").read_text(encoding="utf-8")
    for token, value in replacements.items():
        template = template.replace(token, value)
    (destination / "index.html").write_text(template, encoding="utf-8")

    payload = {
        "schemaVersion": 2,
        "slug": project.slug,
        "title": project.title,
        "tickerText": project.ticker_text,
        "channelId": project.channel_id,
        "channelTitle": project.channel_title,
        "channelUrl": project.channel_url,
        "channelThumbnail": project.channel_thumbnail,
        "videoCount": len(project.videos),
        "customerConfig": {
            "customerName": project.title,
            "customerLogo": project.channel_thumbnail,
            "customerTheme": "cinematic-customer",
            "tagline": project.ticker_text,
            "customerTagline": "MORE STORIES • MORE TO DISCOVER",
            "customerStory": project.ticker_text,
            "customerStorySections": story_sections,
            "youtubeChannel": project.channel_url,
            "subscribeURL": f"https://www.youtube.com/channel/{project.channel_id}?sub_confirmation=1" if project.channel_id else project.channel_url,
            "primaryCTA": "VIEW ON YOUTUBE",
        },
        "videos": [
            {
                "id": item.video_id,
                "videoId": item.video_id,
                "title": item.title,
                "shortTitle": item.display_title,
                "displayTitle": item.display_title,
                "category": item.channel_title,
                "reelImage": item.thumbnail_url,
                "url": item.url,
                "videoURL": item.url,
                "embedUrl": item.embed_url,
                "thumbnailUrl": item.thumbnail_url,
                "description": f"A closer look at {item.display_title} from {item.channel_title or project.title}.",
                "storyText": f"{item.display_title}. Selected from {item.channel_title or project.title}. Press Play Video to watch the complete video on YouTube.",
                "metadata": f"{item.channel_title} • Video Discovery • YouTube",
                "shareText": f"{item.display_title} — {project.title}",
                "ctaLabel": "VIEW ON YOUTUBE",
                "ctaURL": item.url,
                "publishedAt": item.published_at,
                "durationSeconds": item.duration_seconds,
                "channelTitle": item.channel_title,
                "channelId": item.channel_id,
            }
            for item in project.videos
        ],
    }
    (destination / "machine.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    create_qr_card(project, destination / "qr-card.png")
    create_social_card(project, destination / "social-card.jpg")
    return destination / "index.html"
