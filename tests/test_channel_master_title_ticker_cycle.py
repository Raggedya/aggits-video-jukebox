from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.models import ChannelMasterConfig, PrimaryCta, PrimaryCtaType, Project, ProjectType, Video
from aggits_video_factory.site_builder import build_project_site


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
STYLES = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")


def _project(ticker: str = "LOCAL MUSIC • LIVE THIS WEEK • GET TICKETS") -> Project:
    video = Video(
        video_id="tickercycle1",
        title="Ticker Cycle",
        display_title="Ticker Cycle",
        channel_title="Channel",
        url="https://www.youtube.com/watch?v=tickercycle1",
        embed_url="https://www.youtube.com/embed/tickercycle1",
        thumbnail_url="",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=60,
    )
    return Project(
        slug="ticker-cycle",
        title="CHANNEL MASTER",
        ticker_text=ticker,
        channel_url="https://www.youtube.com/channel/UCTICKERCYCLE",
        channel_id="UCTICKERCYCLE",
        channel_title="Ticker Cycle",
        channel_thumbnail="",
        project_type=ProjectType.CHANNEL_MASTER,
        videos=[video],
        channel_master_config=ChannelMasterConfig(
            primary_cta=PrimaryCta(PrimaryCtaType.EXPLORE, "https://example.com/explore"),
        ),
    )


def _function(name: str) -> str:
    start = SCRIPT.index(f"function {name}(")
    next_function = SCRIPT.find("\n  function ", start + 1)
    return SCRIPT[start:] if next_function < 0 else SCRIPT[start:next_function]


class ChannelMasterTitleTickerCycleTests(unittest.TestCase):
    def test_canonical_five_and_ten_second_cycle_uses_one_elapsed_time_clock(self):
        cycle = _function("syncChannelMasterIdentityCycle")
        self.assertIn("const CHANNEL_MASTER_TITLE_VISIBLE_DURATION = 5000;", SCRIPT)
        self.assertIn("const CHANNEL_MASTER_TICKER_VISIBLE_DURATION = 10000;", SCRIPT)
        self.assertIn("CHANNEL_MASTER_TITLE_VISIBLE_DURATION + CHANNEL_MASTER_TICKER_VISIBLE_DURATION", SCRIPT)
        self.assertIn("performance.now() - channelMasterIdentityCycleStartedAt", cycle)
        self.assertIn("elapsed % CHANNEL_MASTER_IDENTITY_CYCLE_DURATION", cycle)
        self.assertIn("phase < CHANNEL_MASTER_TITLE_VISIBLE_DURATION", cycle)
        self.assertIn("window.setTimeout(syncChannelMasterIdentityCycle", cycle)
        self.assertNotIn("setInterval", cycle)

    def test_ticker_is_mounted_once_before_cycle_and_never_recreated(self):
        start = _function("startChannelMasterHeaderTicker")
        channel_branch = start.split("if (activeProjectType === 'channel_master')", 1)[1].split("return;", 1)[0]
        self.assertLess(channel_branch.index("channelMasterHeaderTicker.hidden = false;"), channel_branch.index("syncChannelMasterIdentityCycle();"))
        self.assertLess(channel_branch.index("channelMasterHeaderTicker.hidden = false;"), channel_branch.index("channelMasterHeaderTickerCopy.scrollWidth"))
        self.assertLess(channel_branch.index("channelMasterHeaderTickerCopy.scrollWidth"), channel_branch.index("--channel-master-ticker-duration"))
        self.assertEqual(channel_branch.count("channelMasterHeaderTicker.hidden = false;"), 1)
        self.assertNotIn("innerHTML", start)
        self.assertNotIn("createElement", start)
        self.assertNotIn("remove", start)
        self.assertNotIn("animation", _function("syncChannelMasterIdentityCycle"))

    def test_original_distance_based_ticker_speed_is_measured_after_mount(self):
        start = _function("startChannelMasterHeaderTicker")
        self.assertEqual(start.count("travel / 42"), 2)
        self.assertEqual(start.count("Math.max(14, travel / 42)"), 2)
        legacy_branch = start.split("channelMasterHeaderTickerTimer = window.setTimeout", 1)[1]
        self.assertLess(legacy_branch.index("channelMasterHeaderTicker.hidden = false;"), legacy_branch.index("channelMasterHeaderTickerCopy.scrollWidth"))

    def test_hidden_ticker_keeps_running_and_only_opacity_selects_visible_layer(self):
        ticker_rule = STYLES.split('.music-machine[data-project-type="channel_master"] .channel-master-header-ticker{', 1)[1].split("}", 1)[0]
        ticker_span_rule = STYLES.split('.music-machine[data-project-type="channel_master"] .channel-master-header-ticker span{', 1)[1].split("}", 1)[0]
        selected_rule = STYLES.split('.customer-identity[data-shop-plaque-state="channel-master-ticker"] .channel-master-header-ticker{', 1)[1].split("}", 1)[0]
        self.assertIn("position:absolute", ticker_rule)
        self.assertIn("opacity:0", ticker_rule)
        self.assertIn("transition:opacity .55s ease", ticker_rule)
        self.assertIn("animation:channelMasterHeaderTicker", ticker_span_rule)
        self.assertIn("linear infinite", ticker_span_rule)
        self.assertIn("opacity:1", selected_rule)

    def test_empty_ticker_does_not_start_cycle_or_create_blank_interval(self):
        start = _function("startChannelMasterHeaderTicker")
        self.assertIn("!channelMasterHeaderTickerCopy?.textContent?.trim()", start)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(_project(ticker=""), destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("data-channel-master-header-ticker", page)

    def test_cycle_is_channel_master_only_and_legacy_products_keep_one_way_delay(self):
        start = _function("startChannelMasterHeaderTicker")
        self.assertIn("if (activeProjectType === 'channel_master')", start)
        self.assertIn("CHANNEL_MASTER_TICKER_DELAY", start)
        self.assertIn("const CHANNEL_MASTER_TICKER_DELAY = 10000;", SCRIPT)
        self.assertNotIn("white_label", _function("syncChannelMasterIdentityCycle"))
        self.assertNotIn("love_my_locals", _function("syncChannelMasterIdentityCycle"))

    def test_machine_actions_do_not_restart_ticker_or_visibility_clock(self):
        self.assertEqual(SCRIPT.count("startChannelMasterHeaderTicker();"), 1)
        for action in ("spin", "openVideo", "openPrimaryAction", "cancelChannelMasterIntro"):
            body = _function(action)
            self.assertNotIn("startChannelMasterHeaderTicker", body, action)
            self.assertNotIn("channelMasterIdentityCycleStartedAt", body, action)
            self.assertNotIn("channelMasterHeaderTicker.hidden", body, action)

    def test_layout_crossfade_and_reduced_motion_are_non_reflowing(self):
        self.assertIn('transition:opacity .55s ease', STYLES)
        self.assertIn('.music-machine[data-project-type="channel_master"] .channel-master-header-ticker{position:absolute', STYLES)
        self.assertIn('@media (prefers-reduced-motion:reduce)', STYLES)
        self.assertIn('.music-machine[data-project-type="channel_master"] .channel-master-header-ticker{transition-duration:.01ms!important}', STYLES)
        self.assertIn('animation:none!important', STYLES)

    def test_pagehide_cleans_up_authoritative_timer(self):
        self.assertIn("window.addEventListener('pagehide', () => window.clearTimeout(channelMasterHeaderTickerTimer));", SCRIPT)


if __name__ == "__main__":
    unittest.main()
