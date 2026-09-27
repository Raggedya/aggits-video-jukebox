"""Build the local, non-production Lorne Tourism visual QA fixture."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aggits_video_factory.models import (  # noqa: E402
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    TourismConfig,
    TourismDiscovery,
    Video,
)
from aggits_video_factory.site_builder import build_project_site  # noqa: E402


OUTPUT = ROOT / "_qa" / "tourism-lorne-preview"
MEDIA = OUTPUT.parent / "tourism-lorne-preview-media"
VIDEO_IDS = (
    "qeP2uWZt3fg", "hckwxq8rnr0", "UhpTiWyVa6k", "e7-sbwWWOLw",
    "pSzTPGlNa5U", "gtyKNFqutHM", "HAZlPuL3Qhw", "zYumtXF1nZM",
)
SAMPLES = (
    ("NATURE", "STEP OFF THE MAP", "SAMPLE NATURE DISCOVERY", "Development fixture only — replace with verified destination copy."),
    ("FOOD", "TASTE THE COAST", "SAMPLE FOOD DISCOVERY", "Development fixture only — replace with verified destination copy."),
    ("ACTIVITY", "TRY SOMETHING NEW", "SAMPLE ACTIVITY DISCOVERY", "Development fixture only — replace with verified destination copy."),
    ("ACCOMMODATION", "STAY A LITTLE LONGER", "SAMPLE STAY DISCOVERY", "Development fixture only — replace with verified destination copy."),
    ("NEARBY", "KEEP EXPLORING", "SAMPLE NEARBY DISCOVERY", "Development fixture only — replace with verified destination copy."),
)


def poster(category: str, index: int) -> Path:
    MEDIA.mkdir(parents=True, exist_ok=True)
    destination = MEDIA / f"sample-{category.lower()}.jpg"
    colours = ("#18374A", "#35412C", "#48351F", "#302B45", "#183B3A")
    image = Image.new("RGB", (1200, 675), colours[index])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 450, 1200, 675), fill="#05090D")
    draw.text((60, 510), f"DEVELOPMENT FIXTURE • {category}", fill="#D6AA60")
    image.save(destination, quality=90)
    return destination


def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    discoveries = [
        TourismDiscovery(
            id=f"lorne-sample-{index + 1}", location="Lorne, Victoria, Australia",
            category=category, hook=hook, headline=headline, body=body,
            image=str(poster(category, index)), cta_label="DISCOVER",
            cta_url="https://example.com/official-tourism",
            source_url="https://example.com/development-fixture",
        )
        for index, (category, hook, headline, body) in enumerate(SAMPLES)
    ]
    videos = [
        Video(
            video_id=video_id, title=f"DEVELOPMENT VIDEO FIXTURE {index + 1}",
            display_title=f"DEVELOPMENT VIDEO FIXTURE {index + 1}",
            url=f"https://www.youtube.com/watch?v={video_id}",
            embed_url=f"https://www.youtube-nocookie.com/embed/{video_id}",
            thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            published_at="2026-01-01T00:00:00Z", duration_seconds=120,
            channel_title="DEVELOPMENT FIXTURE", channel_id="UCdevelopmentfixture",
        )
        for index, video_id in enumerate(VIDEO_IDS)
    ]
    project = Project(
        slug="love-lorne-tourism-preview", title="LOVE LORNE",
        ticker_text="DEVELOPMENT PREVIEW ONLY • VIDEO + LOCAL DISCOVERY CARDS •",
        channel_url="https://www.youtube.com/@developmentfixture",
        channel_id="UCdevelopmentfixture", channel_title="DEVELOPMENT FIXTURE",
        channel_thumbnail="", project_type=ProjectType.TOURISM,
        tourism_config=TourismConfig(
            more_info_url="https://example.com/official-tourism",
            primary_cta=PrimaryCta(PrimaryCtaType.MORE_INFO, "https://example.com/official-tourism"),
            destination_title="LOVE LORNE", location="Lorne, Victoria, Australia",
            official_tourism_url="https://example.com/official-tourism",
            discoveries=discoveries,
        ),
        videos=videos,
    )
    build_project_site(project, OUTPUT)
    index_path = OUTPUT / "index.html"
    markup = index_path.read_text(encoding="utf-8")
    qa_driver = (
        "<script>/* LOCAL VISUAL QA ONLY */ Math.random=()=>0.1;"
        "addEventListener('load',()=>setTimeout(()=>document.querySelector('[data-action=\"spin-again\"]')?.click(),700));"
        "</script>\n"
    )
    index_path.write_text(markup.replace("</body>", f"{qa_driver}</body>"), encoding="utf-8")
    print(OUTPUT / "index.html")


if __name__ == "__main__":
    main()
