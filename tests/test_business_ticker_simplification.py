from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.models import ProjectType
from aggits_video_factory.site_builder import _story_sections, build_project_site
from tests.test_business_shop_plaque import business_project, music_project


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")


def generated_site(project) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as temporary:
        destination = Path(temporary) / "site"
        build_project_site(project, destination)
        page = (destination / "index.html").read_text(encoding="utf-8")
        config = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
        return page, config


class BusinessTickerSimplificationTests(unittest.TestCase):
    def test_business_ticker_is_one_title_followed_by_unmodified_bio_only(self):
        project = business_project("https://example.com/shop")
        project.title = "TOTAL TOOLS"
        project.ticker_text = (
            "Total Tools has been helping Australian tradies for more than 30 years.\n\n"
            "Built around Every Tool, Every Trade, the business has grown nationwide.\n\n"
            "Total Tools brings together leading professional brands."
        )

        page, config = generated_site(project)
        story_markup = page.split('<section class="customer-story"', 1)[1].split("</section>", 1)[0]

        self.assertEqual(story_markup.count("<h3>TOTAL TOOLS</h3>"), 1)
        self.assertIn(project.ticker_text, story_markup)
        self.assertEqual(config["customerConfig"]["customerStory"], project.ticker_text)
        self.assertEqual(config["customerConfig"]["customerStorySections"], [])
        self.assertLess(story_markup.index("TOTAL TOOLS"), story_markup.index("Total Tools has been helping"))
        self.assertLess(story_markup.index("helping Australian tradies"), story_markup.index("Built around"))
        self.assertLess(story_markup.index("Built around"), story_markup.index("leading professional brands"))

    def test_business_has_no_generic_or_generated_editorial_headings(self):
        project = business_project("https://example.com/shop")
        project.ticker_text = "A real supplied biography. Its paragraph order remains intact."
        page, config = generated_site(project)
        story_markup = page.split('<section class="customer-story"', 1)[1].split("</section>", 1)[0]
        forbidden = {
            "THE STORY SO FAR", "THE BEGINNING", "THE JOURNEY", "THE RANGE",
            "OUR STORY", "CUSTOM BUILDS", "CUSTOMER FIRST", "THE NEXT CHAPTER",
            "THE BUSINESS", "THE EXPERIENCE", "THE PRODUCTS", "THE FUTURE",
        }

        self.assertEqual(_story_sections(project.ticker_text, project.title, ProjectType.BUSINESS), [])
        for heading in forbidden:
            self.assertNotIn(heading, story_markup)
            self.assertNotIn(heading, json.dumps(config["customerConfig"]))

    def test_business_uses_manual_bio_and_not_supplementary_or_video_copy(self):
        project = business_project("https://example.com/shop")
        project.ticker_text = "Manual Business Bio — exactly as supplied."
        project.additional_urls = ["https://example.com/supplementary"]
        page, config = generated_site(project)

        self.assertIn(project.ticker_text, page)
        self.assertEqual(config["customerConfig"]["customerStory"], project.ticker_text)
        self.assertNotIn(project.additional_urls[0], page)
        self.assertNotIn(project.additional_urls[0], config["customerConfig"]["customerStory"])

    def test_music_uses_one_title_and_original_bio_without_generated_headings(self):
        project = music_project()
        project.title = "THE FAKEAWAYS"
        project.ticker_text = "The band formed together.\n\nTheir original music developed on stage."
        page, config = generated_site(project)
        story_markup = page.split('<section class="customer-story"', 1)[1].split("</section>", 1)[0]

        self.assertEqual(story_markup.count("<h3>THE FAKEAWAYS</h3>"), 1)
        self.assertIn(project.ticker_text, story_markup)
        self.assertEqual(config["customerConfig"]["customerStory"], project.ticker_text)
        self.assertEqual(config["customerConfig"]["customerStorySections"], [])
        self.assertNotIn("THE STORY SO FAR", story_markup)
        self.assertNotIn("THE BEGINNING", story_markup)
        self.assertNotIn("THE MUSIC", story_markup)
        self.assertIn("masterStorySections = [];", SCRIPT)

    def test_selected_video_story_integration_and_scrolling_remain_unchanged(self):
        self.assertIn("appendStoryText(section, 'h4', titleOnly(video));", SCRIPT)
        self.assertIn("appendStoryText(section, 'p', video.storyText", SCRIPT)
        self.assertIn("storyTrack.classList.add('is-scrolling');", SCRIPT)
        self.assertIn("@keyframes storyCrawl", (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8"))

    def test_other_business_machine_controls_and_shop_paths_remain_present(self):
        page, config = generated_site(business_project("https://example.com/shop"))

        for marker in ('data-reel="0"', 'class="lever"', 'data-action="share"', 'data-action="play"',
                       'data-action="shop"', 'data-action="spin-again"', 'data-story-window'):
            self.assertIn(marker, page)
        self.assertEqual(config["customerConfig"]["shopURL"], "https://example.com/shop")
        self.assertTrue(config["customerConfig"]["shopEnabled"])


if __name__ == "__main__":
    unittest.main()
