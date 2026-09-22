from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.models import (
    BusinessConfig,
    BanjoConfig,
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
            ProjectType.BANJO: "BANJO'S WORLD OF CARS",
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
    if project_type is ProjectType.TOURISM:
        return Project(
        **common,
        tourism_config=TourismConfig(
            primary_cta=PrimaryCta(PrimaryCtaType.STAY, "https://example.com/stay"),
            more_info_url="https://example.com/info",
            stay_url="https://example.com/stay",
        ),
        )
    return Project(**common, banjo_config=BanjoConfig())


class MachineBrandHierarchyTests(unittest.TestCase):
    def test_project_hero_retains_current_brand_hierarchy_and_restores_plaque(self):
        self.assertNotIn('class="brand-masthead"', TEMPLATE)
        self.assertIn('class="customer-identity-subtitle" aria-hidden="true">&nbsp;</span>', TEMPLATE)
        self.assertNotIn("SPIN • DISCOVER • WATCH", TEMPLATE[TEMPLATE.index('data-shop-plaque'):TEMPLATE.index('discovery-zone')])
        self.assertLess(TEMPLATE.index('class="customer-identity"'), TEMPLATE.index('class="discovery-zone"'))
        self.assertIn('<h1 class="customer-identity-copy">', TEMPLATE)
        self.assertIn('<strong data-machine-title>{{MACHINE_TITLE}}</strong>', TEMPLATE)
        hero_rule = STYLES.split(".customer-identity{", 1)[1].split("}", 1)[0]
        self.assertIn("border:1px solid rgba(215,170,89,.72)", hero_rule)
        self.assertIn("border-radius:10px", hero_rule)
        self.assertIn("inset 0 1px rgba(255,236,187,.2)", hero_rule)
        self.assertIn("0 0 0 2px #24170c", hero_rule)

    def test_title_and_cta_use_the_canonical_condensed_plaque_typography(self):
        title_rule = STYLES.split(".customer-identity-copy>strong{", 1)[1].split("}", 1)[0]
        cta_rule = STYLES.split(".customer-identity-copy>.customer-identity-shop{", 1)[1].split("}", 1)[0]
        self.assertIn("font:950", title_rule)
        self.assertIn("clamp(19px,4.3vw,32px)", title_rule)
        self.assertIn("var(--font-display)", title_rule)
        self.assertIn("letter-spacing:.035em", title_rule)
        self.assertNotIn("font:", cta_rule)
        self.assertIn("const preferred = compact ? 25 : 32;", SCRIPT)
        self.assertIn("const oneLineMinimum = compact ? 15 : 18;", SCRIPT)

    def test_canonical_decorative_lines_are_restored_beneath_the_content(self):
        line_rule = STYLES.split(".customer-identity-subtitle{", 1)[1].split("}", 1)[0]
        self.assertIn("width:min(78%,450px)", line_rule)
        self.assertIn("margin-top:5px", line_rule)
        self.assertIn("gap:9px", line_rule)
        self.assertIn(".customer-identity-subtitle::before,.customer-identity-subtitle::after", STYLES)
        self.assertIn("linear-gradient(90deg,transparent,rgba(231,193,117,.72))", STYLES)

    def test_social_palette_is_retained_while_plaque_uses_canonical_green(self):
        self.assertIn(f"--hero-midnight:{VIGNETTE_CENTER}", STYLES)
        self.assertIn(f"--hero-near-black:{VIGNETTE_EDGE}", STYLES)
        self.assertIn(f"--hero-ivory:{TITLE_FILL}", STYLES)
        self.assertIn(f"--hero-gold:{TITLE_EDGE}", STYLES)
        hero_rule = STYLES.split(".customer-identity{", 1)[1].split("}", 1)[0]
        self.assertIn("linear-gradient(180deg,#0c332c,#020907 76%)", hero_rule)

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

    def test_all_project_types_generate_one_shared_hero_structure_with_banjo_scoping(self):
        for project_type in ProjectType:
            with self.subTest(project_type=project_type.value), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary)
                build_project_site(project_for(project_type), destination)
                page = (destination / "index.html").read_text(encoding="utf-8")
                self.assertEqual(page.count('class="customer-identity"'), 1)
                self.assertEqual(page.count('class="brand-signature"'), 1)
                self.assertNotIn('class="brand-masthead"', page)
                self.assertIn("customer-identity-subtitle", page)
                if project_type is ProjectType.BANJO:
                    self.assertIn("banjo-header-character", page)
                else:
                    self.assertNotIn("banjo-header-character", page)


if __name__ == "__main__":
    unittest.main()
