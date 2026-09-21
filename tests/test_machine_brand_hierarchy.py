from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.models import (
    BusinessConfig,
    MusicConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    TourismConfig,
    Video,
)
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.social_preview import (
    TITLE_EDGE,
    TITLE_FILL,
    VIGNETTE_CENTER,
    VIGNETTE_EDGE,
)


ROOT = Path(__file__).parents[1]
TEMPLATE = (ROOT / "templates" / "machine.html").read_text(encoding="utf-8")
STYLES = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")


def sample_video() -> Video:
    return Video(
        video_id="hero0000001",
        title="Hero fixture video",
        display_title="Hero fixture video",
        url="https://www.youtube.com/watch?v=hero0000001",
        embed_url="https://www.youtube.com/embed/hero0000001",
        thumbnail_url="https://i.ytimg.com/vi/hero0000001/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=120,
        channel_title="Hero Fixture",
    )


def project_for(project_type: ProjectType) -> Project:
    common = dict(
        slug=f"hero-{project_type.value}",
        title={
            ProjectType.BUSINESS: "ACCESS WORKWEAR & SAFETY",
            ProjectType.MUSIC: "WRAITH",
            ProjectType.TOURISM: "VISIT MERIMBULA",
        }[project_type],
        ticker_text="Fixture Bio remains below the machine controls.",
        channel_url="https://www.youtube.com/channel/UChero",
        channel_id="UChero",
        channel_title="Hero Fixture",
        channel_thumbnail="",
        project_type=project_type,
        videos=[sample_video()],
    )
    if project_type is ProjectType.BUSINESS:
        return Project(**common, business_config=BusinessConfig(shop_url="https://example.com/quote"))
    if project_type is ProjectType.MUSIC:
        return Project(
            **common,
            music_config=MusicConfig(PrimaryCta(PrimaryCtaType.BOOK_US, "https://example.com/book-us")),
        )
    return Project(
        **common,
        tourism_config=TourismConfig(
            primary_cta=PrimaryCta(PrimaryCtaType.STAY, "https://example.com/stay"),
            more_info_url="https://example.com/info",
            stay_url="https://example.com/stay",
        ),
    )


class MachineBrandHierarchyTests(unittest.TestCase):
    def test_project_hero_replaces_top_brand_and_old_plaque(self):
        self.assertNotIn('class="brand-masthead"', TEMPLATE)
        self.assertNotIn("customer-identity-subtitle", TEMPLATE)
        self.assertNotIn("SPIN • DISCOVER • WATCH", TEMPLATE[TEMPLATE.index('data-shop-plaque'):TEMPLATE.index('discovery-zone')])
        self.assertLess(TEMPLATE.index('class="customer-identity"'), TEMPLATE.index('class="discovery-zone"'))
        self.assertIn('<h1 class="customer-identity-copy">', TEMPLATE)
        self.assertIn('<strong data-machine-title>{{MACHINE_TITLE}}</strong>', TEMPLATE)
        hero_rule = STYLES.split(".customer-identity{", 1)[1].split("}", 1)[0]
        self.assertNotIn("border:", hero_rule)
        self.assertNotIn("border-radius", hero_rule)

    def test_live_hero_and_social_card_share_exact_palette(self):
        self.assertIn(f"--hero-midnight:{VIGNETTE_CENTER}", STYLES)
        self.assertIn(f"--hero-near-black:{VIGNETTE_EDGE}", STYLES)
        self.assertIn(f"--hero-ivory:{TITLE_FILL}", STYLES)
        self.assertIn(f"--hero-gold:{TITLE_EDGE}", STYLES)
        hero_rule = STYLES.split(".customer-identity{", 1)[1].split("}", 1)[0]
        self.assertIn("radial-gradient", hero_rule)
        self.assertIn("var(--hero-midnight)", hero_rule)
        self.assertIn("var(--hero-near-black)", hero_rule)

    def test_title_fitter_uses_one_or_two_natural_lines_only(self):
        self.assertIn("function fitHeroTitle(text)", SCRIPT)
        self.assertIn("for (let size = preferred; size >= oneLineMinimum; size -= 1)", SCRIPT)
        self.assertIn("words.slice(0, index).join(' ')", SCRIPT)
        self.assertIn("words.slice(index).join(' ')", SCRIPT)
        self.assertIn("setHeroTitleLines(fitting[0].lines, size)", SCRIPT)
        self.assertIn("titleNode.dataset.titleLines = String(lines.length)", SCRIPT)
        self.assertNotIn("text-overflow:ellipsis", STYLES.split(".customer-identity-copy", 1)[1].split(".customer-identity-shop", 1)[0])
        self.assertNotIn("slice(0, 3)", SCRIPT.split("function fitHeroTitle", 1)[1].split("function fitHeroCta", 1)[0])

    def test_cta_morph_touch_destination_and_timing_remain_in_hero(self):
        hero = TEMPLATE[TEMPLATE.index('data-shop-plaque'):TEMPLATE.index('discovery-zone')]
        self.assertIn("data-shop-plaque-prompt", hero)
        self.assertIn('class="customer-identity-touch"', hero)
        self.assertIn("const SHOP_PLAQUE_TITLE_DURATION = 10000;", SCRIPT)
        self.assertIn("const SHOP_PLAQUE_PROMPT_DURATION = 3500;", SCRIPT)
        self.assertIn("plaqueDestination = primaryActionDestination;", SCRIPT)
        self.assertIn("window.open(plaqueDestination, '_blank', 'noopener,noreferrer');", SCRIPT)

    def test_small_footer_signature_is_logo_only(self):
        footer = TEMPLATE.split('<footer class="brand-signature"', 1)[1].split("</footer>", 1)[0]
        self.assertIn("crispy-bits-logo-cutout-v2.png", footer)
        self.assertNotIn("<p", footer)
        self.assertNotIn("POWERED BY", footer)
        self.assertNotIn("SPIN • DISCOVER • WATCH", footer)
        self.assertGreater(TEMPLATE.index('class="brand-signature"'), TEMPLATE.index('class="customer-story"'))
        self.assertIn("width:min(28%,190px)", STYLES)

    def test_all_project_types_generate_the_same_shared_hero_structure(self):
        for project_type in ProjectType:
            with self.subTest(project_type=project_type.value), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary)
                build_project_site(project_for(project_type), destination)
                page = (destination / "index.html").read_text(encoding="utf-8")
                self.assertEqual(page.count('class="customer-identity"'), 1)
                self.assertEqual(page.count('class="brand-signature"'), 1)
                self.assertNotIn('class="brand-masthead"', page)
                self.assertNotIn("customer-identity-subtitle", page)


if __name__ == "__main__":
    unittest.main()
