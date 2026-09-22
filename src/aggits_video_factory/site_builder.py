from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_H

from .config import BANJO_SUBMISSION_ENDPOINT, BRAND_NAME, PUBLIC_BASE_URL, resource_path
from .banjo import BANJO_TITLE, validate_sponsor_logo, validate_sponsor_mp4, verify_banjo_character
from .models import Project, ProjectType, project_primary_cta
from .social_preview import (
    BANJO_SOCIAL_PREVIEW_SIZE,
    SOCIAL_PREVIEW_SIZE,
    replace_social_preview,
    social_preview_filename,
)


BRASS = "#b88a4f"
DEEP_BRASS = "#4c3219"
CREAM = "#f2e4bf"
INK = "#070605"
BANJO_SPONSOR_CONTACT_EMAIL = "andrewharris501@gmail.com"
BANJO_SPONSOR_CONTACT_SUBJECT = "Banjo Sponsorship Enquiry"
BANJO_SPONSOR_CONTACT_HREF = (
    f"mailto:{BANJO_SPONSOR_CONTACT_EMAIL}?subject={quote(BANJO_SPONSOR_CONTACT_SUBJECT)}"
)


def included_project_videos(project: Project):
    excluded = set(project.excluded_video_ids)
    return [video for video in project.videos if video.video_id not in excluded]


def _banjo_ticker_text(value: str) -> str:
    parts = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"[\r\n]+", str(value or ""))]
    return " • ".join(part for part in parts if part)


def _story_sections(
    source: str,
    customer_name: str,
    project_type: ProjectType = ProjectType.BUSINESS,
) -> list[dict[str, str]]:
    """No generated editorial sections: every project type renders its stored Bio verbatim."""
    return []


def _reel_short_title(source: str) -> str:
    """Derive a compact reel nameplate without changing the source video title."""
    cleaned = re.sub(r"[^A-Za-z0-9.&+\- ]+", " ", source or "")
    cleaned = re.sub(r"\bTRIPPLE\b", "TRIPLE", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(1[5-9]|2[0-4])\s+([0-9])\s*(?=FT\b|FAMILY\b|TWO\b|TRIPLE\b|DOUBLE\b|CLUB\b|OFF[ -]?ROAD\b)",
        r"\1.\2 ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    upper = cleaned.upper()
    size_match = re.search(
        r"\b(\d{2}(?:\.\d{1,2})?)\s*(?:FT|FOOT\b|(?=(?:FAMILY|TWO|TRIPLE|DOUBLE|CLUB|OFF[ -]?ROAD)\b))",
        upper,
    )
    size = f"{size_match.group(1)} FT" if size_match else ""
    if "TRIPLE BUNK" in upper:
        subject = "TRIPLE BUNK"
    elif "DOUBLE BUNK" in upper:
        subject = "DOUBLE BUNK"
    elif "TWO PERSON" in upper or "TWO BIRTH" in upper or "COUPLE" in upper:
        subject = "COUPLES"
    elif "FAMILY" in upper:
        subject = "FAMILY"
    elif "TOY HAULER" in upper:
        subject = "TOY HAULER"
    elif "CLUB LOUNGE" in upper:
        subject = "CLUB LOUNGE"
    elif "ONSITE CARAVAN" in upper:
        subject = "ONSITE CARAVAN"
    elif "SLIDE-OUT KITCHEN" in upper or "SLIDE OUT KITCHEN" in upper:
        subject = "SLIDE-OUT KITCHEN"
    elif "TOURING" in upper or "TOURER" in upper:
        subject = "TOURER"
    elif "OFF-ROAD" in upper or "OFF ROAD" in upper or "OUTBACK" in upper:
        subject = "OFF-ROAD"
    elif "NEWEST MODEL" in upper:
        subject = "NEWEST MODELS"
    else:
        subject = ""
    candidate = " ".join(part for part in (size, subject) if part)
    if not candidate:
        noise = {"THE", "A", "AN", "AND", "OUR", "WITH", "MEET", "BUILD", "VIDEO", "GREAT", "ALPINE", "CARAVANS", "CARAVAN", "AVAILABLE", "STOCK"}
        words = [word for word in re.findall(r"[A-Z0-9.&+\-]+", upper) if word not in noise and not re.fullmatch(r"20\d{2}", word)]
        candidate = " ".join(words[:4]) or "VIDEO DISCOVERY"
    if len(candidate) <= 24:
        return candidate
    words = candidate.split()
    while len(" ".join(words)) > 24 and len(words) > 1:
        words.pop()
    return " ".join(words)[:24].rstrip()


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


def build_project_site(project: Project, destination: Path) -> Path:
    if project.project_type not in {
        ProjectType.BUSINESS, ProjectType.MUSIC, ProjectType.TOURISM,
        ProjectType.BANJO, ProjectType.CHANNEL_MASTER,
    }:
        raise ValueError(f"Unsupported project type: {project.project_type!r}.")
    primary_cta = project_primary_cta(project)
    music_cta = project.music_config.primary_cta if project.music_config else None
    tourism_config = project.tourism_config if project.project_type is ProjectType.TOURISM else None
    banjo_config = project.banjo_config if project.project_type is ProjectType.BANJO else None
    channel_master_config = project.channel_master_config if project.project_type is ProjectType.CHANNEL_MASTER else None
    if project.project_type is ProjectType.MUSIC and primary_cta is None:
        raise ValueError("A Music project requires a configured primary CTA before generation.")
    destination.mkdir(parents=True, exist_ok=True)
    assets = destination / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(resource_path("static"), assets)
    sponsor_logo_public_url = ""
    if project.project_type is ProjectType.BANJO:
        character = assets / "banjo" / "banjo-approved-header.png"
        verify_banjo_character(character)
        sponsor_output = assets / "banjo-sponsor"
        sponsor_output.mkdir(parents=True, exist_ok=True)
        for creative in banjo_config.sponsor.creatives if banjo_config else []:
            source = destination.parent / creative.asset_path
            validate_sponsor_mp4(source)
            shutil.copy2(source, sponsor_output / f"sponsor-{creative.creative_id}.mp4")
        sponsor = banjo_config.sponsor if banjo_config else None
        if sponsor and sponsor.logo_asset_path:
            logo_source = destination.parent / sponsor.logo_asset_path
            validate_sponsor_logo(logo_source)
            logo_name = Path(sponsor.logo_asset_path).name
            shutil.copy2(logo_source, sponsor_output / logo_name)
            sponsor_logo_public_url = f"assets/banjo-sponsor/{logo_name}"

    canonical = project.published_url if str(project.published_url or "").startswith("https://") else f"{PUBLIC_BASE_URL}/{project.slug}/"
    social_filename = social_preview_filename(project.title, project.project_type)
    social_url = f"{canonical.rstrip('/')}/{social_filename}"
    included_videos = included_project_videos(project)
    if not included_videos:
        raise ValueError("A project must include at least one video before generation.")
    social_title = project.title.strip() or BRAND_NAME
    description = (
        f"Hit it. Discover {social_title}." if project.project_type is ProjectType.CHANNEL_MASTER
        else f"Hit it. Discover {social_title} with Crispy Bits."
    )
    if project.project_type is ProjectType.BANJO:
        social_image_type = "image/png"
        social_image_width, social_image_height = BANJO_SOCIAL_PREVIEW_SIZE
        social_image_alt = "Fresh Video Update — Banjo's World of Cars"
    else:
        social_image_type = "image/jpeg"
        social_image_width, social_image_height = SOCIAL_PREVIEW_SIZE
        social_image_alt = f"{social_title} — Crispy Bits social preview"
    story_sections = _story_sections(project.ticker_text, project.title, project.project_type)
    banjo_ticker = _banjo_ticker_text(project.ticker_text) if project.project_type is ProjectType.BANJO else ""
    channel_master_ticker = _banjo_ticker_text(project.ticker_text) if project.project_type is ProjectType.CHANNEL_MASTER else ""
    primary_action_label = primary_cta.display_label if primary_cta else ("SHOW BANJO" if project.project_type is ProjectType.BANJO else "PRIMARY ACTION")
    primary_action_aria = (
        "Show Banjo your car"
        if project.project_type is ProjectType.BANJO
        else primary_action_label if primary_cta and primary_cta.destination_url else f"{primary_action_label} unavailable"
    )
    initial_reel_instruction = "PULL THE LEVER  ──────→"
    story_header_markup = ""
    story_aria_label = project.title
    banjo_sponsor_area_markup = ""
    if project.project_type is ProjectType.BANJO:
        sponsor = banjo_config.sponsor if banjo_config else None
        if sponsor and sponsor.active and sponsor.url:
            destination_url = html.escape(sponsor.url, quote=True)
            banjo_sponsor_area_markup = (
                '<section class="banjo-sponsor-area" data-banjo-sponsor-area>'
                f'<a class="banjo-sponsor-button" data-banjo-sponsor-button data-banjo-sponsor-mode="active" href="{destination_url}" target="_blank" rel="noopener noreferrer">VISIT OUR SPONSOR</a>'
                + (
                    f'<a class="banjo-sponsor-logo" data-banjo-sponsor-logo href="{destination_url}" target="_blank" rel="noopener noreferrer">'
                    f'<img src="{html.escape(sponsor_logo_public_url, quote=True)}" alt="{html.escape(sponsor.title, quote=True)} sponsor logo"></a>'
                    if sponsor_logo_public_url else ""
                )
                + '</section>'
            )
        else:
            banjo_sponsor_area_markup = (
                '<section class="banjo-sponsor-area banjo-sponsor-area--seeking" data-banjo-sponsor-area>'
                '<h2>BANJO IS LOOKING FOR SPONSORS</h2>'
                '<p>Interested in advertising on Banjo\'s World of Cars?</p>'
                f'<a class="banjo-sponsor-button" data-banjo-sponsor-button data-banjo-sponsor-mode="inquiry" href="{BANJO_SPONSOR_CONTACT_HREF}">EMAIL BANJO</a>'
                '</section>'
            )
    channel_master_contact_markup = ""
    if channel_master_config and channel_master_config.contact_url:
        contact_url = html.escape(channel_master_config.contact_url, quote=True)
        channel_master_contact_markup = (
            '<section class="channel-master-contact" data-channel-master-contact>'
            f'<a href="{contact_url}" target="_blank" rel="noopener noreferrer">CONTACT US</a></section>'
        )
    machine_theme_attribute = ""
    if channel_master_config:
        machine_theme_attribute = (
            ' style="'
            f'--theme-primary:{channel_master_config.resolved_primary};'
            f'--theme-secondary:{channel_master_config.resolved_secondary};'
            f'--theme-accent:{channel_master_config.resolved_accent}'
            '"'
        )
    replacements = {
        "{{META_DESCRIPTION}}": html.escape(description, quote=True),
        "{{CANONICAL_URL}}": html.escape(canonical, quote=True),
        "{{SOCIAL_IMAGE_URL}}": html.escape(social_url, quote=True),
        "{{SOCIAL_IMAGE_TYPE}}": social_image_type,
        "{{SOCIAL_IMAGE_WIDTH}}": str(social_image_width),
        "{{SOCIAL_IMAGE_HEIGHT}}": str(social_image_height),
        "{{SOCIAL_IMAGE_ALT}}": html.escape(social_image_alt, quote=True),
        "{{SOCIAL_TITLE}}": html.escape(social_title, quote=True),
        "{{DOCUMENT_TITLE}}": html.escape(social_title if project.project_type is ProjectType.CHANNEL_MASTER else f"{social_title} | Crispy Bits"),
        "{{MACHINE_LABEL}}": html.escape(
            project.title if project.project_type is ProjectType.CHANNEL_MASTER
            else BANJO_TITLE if project.project_type is ProjectType.BANJO
            else f"{project.title} CRISPY BITS Video Jukebox", quote=True
        ),
        "{{PROJECT_TYPE}}": project.project_type.value,
        "{{MACHINE_THEME_ATTRIBUTE}}": machine_theme_attribute,
        "{{UTILITY_CONTROLS_MARKUP}}": (
            "" if project.project_type in {ProjectType.BANJO, ProjectType.CHANNEL_MASTER} else
            '<nav class="utility-controls" aria-label="Machine controls">'
            '<button type="button" data-action="home"><span aria-hidden="true">⌂</span><b>HOME</b></button>'
            '<button type="button" data-action="sound" aria-pressed="true"><span data-sound-icon aria-hidden="true">♪</span><b data-sound-label>SOUND ON</b></button>'
            '</nav>'
        ),
        "{{BANJO_CHARACTER_MARKUP}}": (
            '<span class="banjo-header-character" aria-hidden="true"><img src="assets/banjo/banjo-approved-header.png" alt="" draggable="false"></span>'
            if project.project_type is ProjectType.BANJO else ""
        ),
        "{{BANJO_SPONSOR_PLAYER_MARKUP}}": (
            '<video data-sponsor-player preload="metadata" controls playsinline hidden aria-label="Sponsor video"></video>'
            if project.project_type is ProjectType.BANJO else ""
        ),
        "{{BANJO_CHOICE_MARKUP}}": (
            '<section class="banjo-choice-overlay" data-banjo-choice-overlay aria-hidden="true" role="status">'
            '<small>BANJO\'S CHOICE AWARD</small><strong data-banjo-choice-title></strong>'
            '<span>CHOSEN BY BANJO</span></section>'
            if project.project_type is ProjectType.BANJO else ""
        ),
        "{{BANJO_HEADER_TICKER_MARKUP}}": (
            '<div class="banjo-header-ticker" data-banjo-header-ticker aria-hidden="true" hidden>'
            f'<span data-banjo-header-ticker-copy>{html.escape(banjo_ticker)}</span></div>'
            f'<span class="visually-hidden" data-banjo-ticker-accessible>{html.escape(banjo_ticker)}</span>'
            if banjo_ticker else ""
        ),
        "{{CHANNEL_MASTER_HEADER_TICKER_MARKUP}}": (
            '<div class="channel-master-header-ticker" data-channel-master-header-ticker aria-hidden="true" hidden>'
            f'<span data-channel-master-header-ticker-copy>{html.escape(channel_master_ticker)}</span></div>'
            f'<span class="visually-hidden" data-channel-master-ticker-accessible>{html.escape(channel_master_ticker)}</span>'
            if channel_master_ticker else ""
        ),
        "{{BANJO_SUBMISSION_MARKUP}}": (
            '<section class="banjo-submission-backdrop" data-banjo-submission-modal hidden>'
            '<div class="banjo-submission-dialog" role="dialog" aria-modal="true" '
            'aria-labelledby="banjo-submission-title">'
            '<button type="button" class="banjo-submission-close" data-banjo-submission-close '
            'aria-label="Close Show Banjo form">&times;</button>'
            '<div data-banjo-submission-form-state>'
            '<h2 id="banjo-submission-title">SHOW BANJO YOUR CAR</h2>'
            '<p>Think Banjo should see your car? Send him the YouTube link.</p>'
            '<form data-banjo-submission-form novalidate>'
            '<label for="banjo-first-name">FIRST NAME</label>'
            '<input id="banjo-first-name" name="first_name" type="text" maxlength="50" autocomplete="given-name" required>'
            '<label for="banjo-email">EMAIL ADDRESS</label>'
            '<input id="banjo-email" name="email" type="email" maxlength="254" autocomplete="email" required>'
            '<label for="banjo-youtube-url">YOUTUBE VIDEO LINK</label>'
            '<input id="banjo-youtube-url" name="youtube_url" type="url" maxlength="300" inputmode="url" autocomplete="url" required>'
            '<div class="banjo-submission-trap" aria-hidden="true">'
            '<label for="banjo-company">COMPANY</label>'
            '<input id="banjo-company" name="company" type="text" tabindex="-1" autocomplete="off">'
            '</div>'
            '<p class="banjo-submission-privacy">We\'ll only use your email to contact you about your submission.</p>'
            '<p class="banjo-submission-error" data-banjo-submission-error role="alert" hidden></p>'
            '<button type="submit" class="banjo-submission-send" data-banjo-submission-send>SEND TO BANJO</button>'
            '</form></div>'
            '<div class="banjo-submission-success" data-banjo-submission-success hidden>'
            '<h2>THANKS — BANJO\'S GOT IT.</h2>'
            '<p>If Banjo adds your car, we\'ll let you know.</p>'
            '<button type="button" class="banjo-submission-send" data-banjo-submission-close>BACK TO THE CARS</button>'
            '</div></div></section>'
            if project.project_type is ProjectType.BANJO else ""
        ),
        "{{BANJO_SPONSOR_AREA_MARKUP}}": banjo_sponsor_area_markup,
        "{{CHANNEL_MASTER_CONTACT_MARKUP}}": channel_master_contact_markup,
        "{{MACHINE_TITLE}}": html.escape(project.title),
        "{{INITIAL_REEL_INSTRUCTION}}": initial_reel_instruction,
        "{{STORY_HEADER_MARKUP}}": story_header_markup,
        "{{STORY_ARIA_LABEL}}": html.escape(story_aria_label, quote=True),
        "{{TICKER_TEXT}}": html.escape(project.ticker_text or "PULL FOR A VIDEO"),
        "{{PRIMARY_ACTION_LABEL}}": html.escape(primary_action_label),
        "{{PRIMARY_ACTION_ARIA}}": html.escape(primary_action_aria, quote=True),
    }
    template = resource_path("templates/machine.html").read_text(encoding="utf-8")
    for token, value in replacements.items():
        template = template.replace(token, value)
    if project.project_type is ProjectType.CHANNEL_MASTER:
        template = re.sub(
            r'\s*<strong class="customer-identity-shop".*?</strong>', "", template,
            count=1, flags=re.DOTALL,
        )
        template = re.sub(
            r'\s*<section class="customer-story".*?</section>\s*(?=<footer class="brand-signature")', "", template,
            count=1, flags=re.DOTALL,
        )
        template = re.sub(
            r'\s*<footer class="brand-signature".*?</footer>', "", template,
            count=1, flags=re.DOTALL,
        )
        template = template.replace(
            '<meta property="og:site_name" content="CRISPY BITS Video Discovery">',
            f'<meta property="og:site_name" content="{html.escape(social_title, quote=True)}">',
        )
        template = template.replace(
            '  <link rel="preload" as="image" href="assets/music-machine/crispy-bits-logo-cutout-v2.png">\n', "",
        )
        template = template.replace(
            "Loading the Crispy Bits video discovery machine.", "Loading the video discovery machine.",
        )
    (destination / "index.html").write_text(template, encoding="utf-8")

    shop_url = project.business_config.shop_url if project.business_config else None
    customer_config = {
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
    }
    customer_config["primaryAction"] = {
        "type": primary_cta.cta_type.value if primary_cta else None,
        "displayLabel": primary_action_label,
        "destinationURL": primary_cta.destination_url if primary_cta else "",
        "enabled": bool(primary_cta and primary_cta.destination_url),
    }
    if project.project_type is ProjectType.BUSINESS:
        customer_config.update({"shopURL": shop_url, "shopEnabled": bool(shop_url)})

    payload = {
        "schemaVersion": 2,
        "projectType": project.project_type.value,
        "slug": project.slug,
        "title": project.title,
        "tickerText": project.ticker_text,
        "channelId": project.channel_id,
        "channelTitle": project.channel_title,
        "channelUrl": project.channel_url,
        "channelThumbnail": project.channel_thumbnail,
        "videoCount": len(included_videos),
        "customerConfig": customer_config,
        "videos": [
            ({
                "id": item.video_id,
                "videoId": item.video_id,
                "title": item.title,
                "shortTitle": _reel_short_title(item.title),
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
            } | ({
                "contentType": "youtube",
                "isBanjosChoice": bool(
                    banjo_config and any(choice.video_id == item.video_id and choice.active for choice in banjo_config.banjos_choice)
                ),
                "banjosChoiceTitle": next((
                    choice.display_title or item.display_title
                    for choice in (banjo_config.banjos_choice if banjo_config else [])
                    if choice.video_id == item.video_id
                ), ""),
            } if project.project_type is ProjectType.BANJO else {}))
            for item in included_videos
        ],
    }
    if music_cta:
        payload["musicConfig"] = {
            "primaryCTA": {
                "type": music_cta.cta_type.value,
                "displayLabel": music_cta.display_label,
                "destinationURL": music_cta.destination_url,
            }
        }
    if project.project_type is ProjectType.TOURISM:
        more_info_url = tourism_config.more_info_url if tourism_config else None
        stay_url = tourism_config.stay_url if tourism_config else None
        payload["tourismConfig"] = {
            "moreInfoURL": more_info_url,
            "moreInfoEnabled": bool(more_info_url),
            "stayURL": stay_url,
            "stayEnabled": bool(stay_url),
        }
    if project.project_type is ProjectType.BANJO:
        sponsor = banjo_config.sponsor if banjo_config else None
        payload["banjoConfig"] = {
            "title": BANJO_TITLE,
            "tickerText": banjo_ticker,
            "submission": {
                "endpoint": BANJO_SUBMISSION_ENDPOINT,
                "projectSlug": project.slug,
                "projectType": "banjo",
            },
            "banjosChoice": [
                {
                    "videoId": item.video_id,
                    "displayTitle": item.display_title,
                    "active": bool(item.active and item.video_id not in set(project.excluded_video_ids)),
                }
                for item in (banjo_config.banjos_choice if banjo_config else [])
            ],
            "sponsor": {
                "active": bool(sponsor and sponsor.active),
                "title": sponsor.title if sponsor else "",
                "url": sponsor.url or "" if sponsor else "",
                "logoAssetUrl": sponsor_logo_public_url,
                "normalDiscoveriesRequired": 5,
                "creatives": [
                    {
                        "creativeId": item.creative_id,
                        "assetUrl": f"assets/banjo-sponsor/sponsor-{item.creative_id}.mp4",
                        "active": bool(item.active),
                        "sizeBytes": item.size_bytes,
                    }
                    for item in (sponsor.creatives if sponsor else [])
                ],
            },
        }
    if project.project_type is ProjectType.CHANNEL_MASTER and channel_master_config:
        cta = channel_master_config.primary_cta
        payload["channelMasterConfig"] = {
            "tickerText": channel_master_ticker,
            "palette": {
                "name": channel_master_config.palette,
                "customPrimary": channel_master_config.custom_primary,
                "customAccent": channel_master_config.custom_accent,
                "resolvedPrimary": channel_master_config.resolved_primary,
                "resolvedSecondary": channel_master_config.resolved_secondary,
                "resolvedAccent": channel_master_config.resolved_accent,
            },
            "primaryAction": {
                "type": cta.cta_type.value if cta else None,
                "displayLabel": cta.display_label if cta else "PRIMARY ACTION",
                "destinationURL": cta.destination_url if cta else "",
                "enabled": bool(cta and cta.destination_url),
            } | ({"customLabel": cta.custom_label} if cta and cta.cta_type.value == "custom" else {}),
            "contact": {
                "url": channel_master_config.contact_url or "",
                "enabled": bool(channel_master_config.contact_url),
            },
        }
    (destination / "machine.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    create_qr_card(project, destination / "qr-card.png")
    replace_social_preview(project.title, destination, project.project_type)
    return destination / "index.html"
