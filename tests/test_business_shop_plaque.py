from __future__ import annotations

import json
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
    Video,
)
from aggits_video_factory.site_builder import build_project_site


ROOT = Path(__file__).parents[1]
TEMPLATE = (ROOT / "templates" / "machine.html").read_text(encoding="utf-8")
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
STYLES = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")


def sample_video() -> Video:
    return Video(
        video_id="dQw4w9WgXcQ",
        title="Plaque Test Video",
        display_title="Plaque Test Video",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        embed_url="https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=0",
        thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=180,
        channel_title="Plaque Test Business",
        channel_id="UCplaque",
    )


def business_project(shop_url: str | None) -> Project:
    return Project(
        slug="plaque-test-business",
        title="A VERY LONG PLAQUE TEST BUSINESS TITLE",
        ticker_text="Manual Business story.",
        channel_url="https://www.youtube.com/channel/UCplaque",
        channel_id="UCplaque",
        channel_title="Plaque Test Business",
        channel_thumbnail="",
        project_type=ProjectType.BUSINESS,
        additional_urls=["https://example.com/not-the-shop"],
        business_config=BusinessConfig(shop_url=shop_url),
        manual_video_urls=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
        videos=[sample_video()],
    )


def music_project() -> Project:
    return Project(
        slug="plaque-test-music",
        title="PLAQUE TEST MUSIC",
        ticker_text="Manual Music story.",
        channel_url="https://www.youtube.com/channel/UCplaque",
        channel_id="UCplaque",
        channel_title="Plaque Test Music",
        channel_thumbnail="",
        project_type=ProjectType.MUSIC,
        additional_urls=["https://example.com/not-the-cta"],
        music_config=MusicConfig(
            primary_cta=PrimaryCta(
                cta_type=PrimaryCtaType.SPOTIFY,
                destination_url="https://example.com/music",
            )
        ),
        videos=[sample_video()],
    )


def generated_config(project: Project) -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "site"
        build_project_site(project, output)
        return json.loads((output / "machine.json").read_text(encoding="utf-8"))


class BusinessShopPlaqueTests(unittest.TestCase):
    def test_business_shop_configuration_is_the_only_plaque_destination(self):
        shop_url = "https://example.com/exact-shop?collection=featured"
        project = business_project(shop_url)
        config = generated_config(project)

        self.assertEqual(config["projectType"], "business")
        self.assertTrue(config["customerConfig"]["shopEnabled"])
        self.assertEqual(config["customerConfig"]["shopURL"], shop_url)
        self.assertNotEqual(config["customerConfig"]["shopURL"], project.additional_urls[0])
        self.assertIn("shopDestination = String(config.customerConfig?.shopURL || '').trim();", SCRIPT)
        self.assertNotIn("shopDestination = String(config.channelURL", SCRIPT)
        self.assertNotIn("shopDestination = String(config.additionalURLs", SCRIPT)

    def test_plaque_defaults_to_business_title_and_cycles_at_restrained_intervals(self):
        self.assertIn('<strong data-machine-title>{{MACHINE_TITLE}}</strong>', TEMPLATE)
        self.assertIn('data-shop-plaque-prompt aria-hidden="true">SHOP NOW →</strong>', TEMPLATE)
        self.assertIn("const SHOP_PLAQUE_TITLE_DURATION = 10000;", SCRIPT)
        self.assertIn("const SHOP_PLAQUE_PROMPT_DURATION = 3500;", SCRIPT)
        self.assertIn("shopPlaque.dataset.shopPlaqueState = 'title';", SCRIPT)
        self.assertIn("scheduleShopPlaqueState('shop', SHOP_PLAQUE_TITLE_DURATION);", SCRIPT)
        self.assertIn("state === 'shop' ? 'title' : 'shop'", SCRIPT)
        self.assertIn("state === 'shop' ? SHOP_PLAQUE_PROMPT_DURATION : SHOP_PLAQUE_TITLE_DURATION", SCRIPT)
        self.assertIn("transition:opacity .7s ease", STYLES)

    def test_both_visual_states_share_one_click_and_keyboard_shop_handler(self):
        self.assertIn("shopPlaque.addEventListener('click'", SCRIPT)
        self.assertIn("if (shopPlaqueEnabled) openShop();", SCRIPT)
        self.assertIn("shopPlaque.addEventListener('keydown'", SCRIPT)
        self.assertIn("event.key === 'Enter' || event.key === ' '", SCRIPT)
        self.assertIn("window.open(shopDestination, '_blank', 'noopener,noreferrer');", SCRIPT)
        self.assertNotIn("data-shop-plaque-state ===", SCRIPT)
        self.assertIn("shopPlaque.setAttribute('role', 'link');", SCRIPT)
        self.assertIn("shopPlaque.setAttribute('tabindex', '0');", SCRIPT)
        self.assertIn("`Visit ${machineIdentity || 'this business'} online shop`", SCRIPT)
        self.assertNotIn("aria-live", TEMPLATE[TEMPLATE.index('data-shop-plaque'):TEMPLATE.index('reel-and-lever')])

    def test_no_shop_business_is_static_non_actionable_and_has_no_fallback(self):
        config = generated_config(business_project(None))

        self.assertFalse(config["customerConfig"]["shopEnabled"])
        self.assertIsNone(config["customerConfig"]["shopURL"])
        self.assertIn("shopPlaqueEnabled = activeProjectType === 'business' && shopEnabled === true && Boolean(shopDestination);", SCRIPT)
        self.assertIn("shopPlaque.removeAttribute('role');", SCRIPT)
        self.assertIn("shopPlaque.removeAttribute('tabindex');", SCRIPT)
        self.assertIn("shopPlaque.removeAttribute('aria-label');", SCRIPT)

    def test_music_never_enables_or_consumes_the_business_shop_plaque(self):
        config = generated_config(music_project())

        self.assertEqual(config["projectType"], "music")
        self.assertNotIn("shopURL", config["customerConfig"])
        self.assertNotIn("shopEnabled", config["customerConfig"])
        self.assertIn("activeProjectType === 'business'", SCRIPT)
        self.assertNotIn("activeProjectType === 'music' && shopEnabled", SCRIPT)

    def test_existing_bottom_shop_control_and_no_shop_state_are_unchanged(self):
        self.assertIn('data-action="shop" aria-label="{{PRIMARY_ACTION_ARIA}}" disabled', TEMPLATE)
        self.assertIn("const shopButton = primaryActionButton;", SCRIPT)
        self.assertIn("if (activeProjectType === 'business') shopButton.disabled = !shopDestination;", SCRIPT)
        self.assertIn("if (activeProjectType === 'music') openPrimaryAction();\n      else openShop();", SCRIPT)

    def test_plaque_timer_is_independent_of_spin_re_spin_and_video_selection(self):
        spin_block = SCRIPT.split("  async function spin() {", 1)[1].split("  function resetLever", 1)[0]
        self.assertNotIn("shopPlaqueTimer", spin_block)
        self.assertNotIn("shopPlaqueState", spin_block)
        self.assertIn("respinButton.addEventListener('click', spin);", SCRIPT)
        self.assertIn("window.addEventListener('pagehide', stopShopPlaqueCycle);", SCRIPT)

    def test_layout_responsive_focus_and_reduced_motion_rules_preserve_plaque_geometry(self):
        self.assertIn(".customer-identity-copy{display:grid", STYLES)
        self.assertIn("grid-area:1/1", STYLES)
        self.assertIn('.customer-identity[data-shop-plaque-state="shop"]', STYLES)
        self.assertIn(".customer-identity.is-shop-enabled:focus-visible", STYLES)
        self.assertIn("@media (prefers-reduced-motion:reduce)", STYLES)
        self.assertIn(".customer-identity-copy>strong{transition-duration:.01ms!important;transform:none!important;filter:none!important}", STYLES)
        self.assertIn(".customer-identity{min-height:56px;margin:0 3% 5px;padding:7px 10px 8px}", STYLES)
        self.assertIn(".customer-identity-copy>strong.is-very-long", STYLES)


if __name__ == "__main__":
    unittest.main()
