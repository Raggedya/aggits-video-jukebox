from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.site_builder import build_project_site
from tests.test_business_shop_plaque import business_project, music_project


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
BUSINESS_INSTRUCTION = "PULL THE LEVER  ──────→"
MUSIC_INSTRUCTION = "PULL TO DISCOVER"


def generated_page(project) -> str:
    with tempfile.TemporaryDirectory() as temporary:
        destination = Path(temporary) / "site"
        build_project_site(project, destination)
        return (destination / "index.html").read_text(encoding="utf-8")


class BusinessInitialReelInstructionTests(unittest.TestCase):
    def test_business_initial_reel_uses_static_right_pointing_lever_instruction(self):
        page = generated_page(business_project("https://example.com/shop"))

        self.assertIn(f"<strong>{BUSINESS_INSTRUCTION}</strong>", page)
        self.assertNotIn(f"<strong>{MUSIC_INSTRUCTION}</strong>", page)
        self.assertTrue(BUSINESS_INSTRUCTION.endswith("→"))
        self.assertNotIn("←", BUSINESS_INSTRUCTION)

    def test_music_initial_reel_instruction_remains_unchanged(self):
        page = generated_page(music_project())

        self.assertIn(f"<strong>{MUSIC_INSTRUCTION}</strong>", page)
        self.assertNotIn(BUSINESS_INSTRUCTION, page)
        self.assertIn("const initialReelInstruction = activeProjectType === 'business'", SCRIPT)
        self.assertIn("? 'PULL THE LEVER  ──────→'", SCRIPT)
        self.assertIn(": 'PULL TO DISCOVER';", SCRIPT)

    def test_landing_re_spin_and_shop_plaque_paths_do_not_use_initial_instruction(self):
        spin_block = SCRIPT.split("  async function spin() {", 1)[1].split("  function resetLever", 1)[0]

        self.assertNotIn(BUSINESS_INSTRUCTION, spin_block)
        self.assertNotIn(MUSIC_INSTRUCTION, spin_block)
        self.assertIn("finalEntry: winner", spin_block)
        self.assertIn("renderRows: video => renderRows(video)", spin_block)
        self.assertIn("current = winner", spin_block)
        self.assertIn("respinButton.addEventListener('click', spin);", SCRIPT)
        self.assertIn("configureShopPlaque(config.customerConfig?.shopEnabled);", SCRIPT)


if __name__ == "__main__":
    unittest.main()
