from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
STYLES = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")


def function_block(name: str, next_name: str) -> str:
    return SCRIPT.split(f"  function {name}", 1)[1].split(f"  function {next_name}", 1)[0]


class TickerContinuityTests(unittest.TestCase):
    def test_landing_updates_content_without_restarting_the_mounted_ticker(self):
        update_story = function_block("updateStory", "updateSoundControl")
        selected_content = function_block("updateSelectedContent", "cancelPendingReveal")

        self.assertIn("storyTrack.replaceChildren(section);", update_story)
        self.assertNotIn("startStoryTicker", update_story)
        self.assertNotIn("classList.remove('is-scrolling')", update_story)
        self.assertIn("updateStory(video);", selected_content)
        self.assertNotIn("startStoryTicker", selected_content)

    def test_spin_re_spin_and_lever_paths_never_touch_ticker_lifecycle(self):
        spin_block = SCRIPT.split("  async function spin() {", 1)[1].split("  function resetLever", 1)[0]
        lever_block = SCRIPT.split("  function resetLever", 1)[1].split("  function playerUrl", 1)[0]
        bind_block = SCRIPT.split("  function bind() {", 1)[1].split("  async function load()", 1)[0]

        for block in (spin_block, lever_block, bind_block):
            self.assertNotIn("startStoryTicker", block)
            self.assertNotIn("is-scrolling", block)
            self.assertNotIn("--story-start", block)
            self.assertNotIn("--story-end", block)
        self.assertIn("respinButton.addEventListener('click', spin);", bind_block)

    def test_initialisation_is_idempotent_and_resize_is_the_only_forced_restart(self):
        ticker_start = function_block("startStoryTicker", "appendStoryText")

        self.assertIn("if ((storyTickerStarted || storyTickerStarting) && !force) return;", ticker_start)
        self.assertIn("const epoch = ++storyTickerEpoch;", ticker_start)
        self.assertIn("if (epoch !== storyTickerEpoch) return;", ticker_start)
        self.assertIn("storyTickerStarted = true;", ticker_start)
        self.assertIn("storyTickerStarting = false;", ticker_start)
        self.assertIn("window.setTimeout(startStoryTicker, 350);", SCRIPT)
        self.assertIn("document.fonts?.ready?.then(startStoryTicker)", SCRIPT)
        self.assertIn("startStoryTicker(true);", SCRIPT)
        self.assertEqual(SCRIPT.count("startStoryTicker(true);"), 1)

    def test_scroll_speed_direction_and_natural_loop_are_unchanged(self):
        self.assertIn(
            ".story-track.is-scrolling{animation:storyCrawl var(--story-duration,52s) linear "
            "var(--story-delay,1.5s) infinite both}",
            STYLES,
        )
        self.assertIn(
            "@keyframes storyCrawl{0%{transform:translate3d(0,var(--story-start,190px),0)}"
            "94%,100%{transform:translate3d(0,var(--story-end,-420px),0)}}",
            STYLES,
        )

    def test_business_music_and_tourism_share_the_same_continuous_ticker_lifecycle(self):
        self.assertIn("activeProjectType = String(config.projectType || 'business')", SCRIPT)
        self.assertIn("activeProjectType === 'tourism'", SCRIPT)
        self.assertEqual(SCRIPT.count("const storyTrack = machine.querySelector('[data-story-track]');"), 1)
        self.assertEqual(SCRIPT.count("storyTrack.classList.add('is-scrolling');"), 1)


if __name__ == "__main__":
    unittest.main()
