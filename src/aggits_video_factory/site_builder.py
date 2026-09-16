from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from qrcode.constants import ERROR_CORRECT_H

from .config import PUBLIC_BASE_URL, resource_path
from .models import Project


BRASS = "#b88a4f"
DEEP_BRASS = "#4c3219"
CREAM = "#f2e4bf"
INK = "#070605"


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
    qr_image = qr.make_image(fill_color=INK, back_color=CREAM).convert("RGB")
    qr_image = qr_image.resize((900, 900), Image.Resampling.NEAREST)

    canvas = Image.new("RGB", (1400, 1600), INK)
    draw = ImageDraw.Draw(canvas)
    for offset, color in [(26, BRASS), (38, DEEP_BRASS), (52, BRASS), (62, "#1d160d")]:
        draw.rounded_rectangle((offset, offset, 1400 - offset, 1600 - offset), radius=26, outline=color, width=5)
    draw.line((110, 290, 1290, 290), fill=BRASS, width=4)
    draw.polygon([(700, 273), (718, 290), (700, 307), (682, 290)], fill=BRASS)

    title = project.title.upper()
    title_font = _fit_text(draw, title, 1120, 104, 44, serif=True)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((1400 - (title_box[2] - title_box[0])) / 2, 130), title, font=title_font, fill=CREAM)

    panel = (225, 340, 1175, 1290)
    draw.rounded_rectangle(panel, radius=42, fill=CREAM, outline=BRASS, width=10)
    canvas.paste(qr_image, (250, 365))

    plaque = (430, 1372, 970, 1490)
    draw.rounded_rectangle(plaque, radius=24, fill="#24170d", outline=BRASS, width=5)
    brand_font = _font(58, bold=True, serif=True)
    brand = "AGGITS"
    brand_box = draw.textbbox((0, 0), brand, font=brand_font)
    draw.text(((1400 - (brand_box[2] - brand_box[0])) / 2, 1392), brand, font=brand_font, fill=CREAM)
    draw.text((700, 1468), "VIDEO DISCOVERY", font=_font(20, bold=True), fill=BRASS, anchor="mm", spacing=3)
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
    draw.text((548, 66), "AGGITS VIDEO MUSIC MACHINE", font=_font(24, bold=True, serif=True), fill=BRASS)
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
    description = f"Pull the AGGITS reel and discover one of {len(project.videos)} videos from {project.title}."
    replacements = {
        "{{META_DESCRIPTION}}": html.escape(description, quote=True),
        "{{CANONICAL_URL}}": html.escape(canonical, quote=True),
        "{{SOCIAL_IMAGE_URL}}": html.escape(social_url, quote=True),
        "{{PAGE_TITLE}}": html.escape(f"{project.title} — AGGITS Video Jukebox"),
        "{{MACHINE_LABEL}}": html.escape(f"{project.title} AGGITS Video Jukebox", quote=True),
        "{{MACHINE_TITLE}}": html.escape(project.title),
        "{{TICKER_TEXT}}": html.escape(project.ticker_text or "PULL FOR A VIDEO"),
    }
    template = resource_path("templates/machine.html").read_text(encoding="utf-8")
    for token, value in replacements.items():
        template = template.replace(token, value)
    (destination / "index.html").write_text(template, encoding="utf-8")

    payload = {
        "schemaVersion": 1,
        "slug": project.slug,
        "title": project.title,
        "tickerText": project.ticker_text,
        "channelId": project.channel_id,
        "channelTitle": project.channel_title,
        "channelUrl": project.channel_url,
        "videoCount": len(project.videos),
        "videos": [
            {
                "videoId": item.video_id,
                "title": item.title,
                "displayTitle": item.display_title,
                "url": item.url,
                "embedUrl": item.embed_url,
                "thumbnailUrl": item.thumbnail_url,
                "publishedAt": item.published_at,
                "durationSeconds": item.duration_seconds,
                "channelTitle": item.channel_title,
            }
            for item in project.videos
        ],
    }
    (destination / "machine.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    create_qr_card(project, destination / "qr-card.png")
    create_social_card(project, destination / "social-card.jpg")
    return destination / "index.html"

