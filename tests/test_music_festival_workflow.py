from __future__ import annotations

import unittest
from pathlib import Path

from aggits_video_factory.desktop_forms import (
    MAX_INDIVIDUAL_VIDEO_URLS,
    FormValidationError,
    ProjectFormValues,
    validate_project_form,
)
from aggits_video_factory.models import ProjectType


DESKTOP_SOURCE = (Path(__file__).parents[1] / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")


def video_url(index: int) -> str:
    return f"https://youtu.be/festival{index:02d}"


class MusicFestivalWorkflowTests(unittest.TestCase):
    def test_music_accepts_twenty_five_mixed_artist_videos_without_a_channel(self):
        values = ProjectFormValues(
            title="Festival Fixture",
            channel_url="",
            manual_video_urls=[video_url(index) for index in range(1, 26)],
            cta_label="Get Tickets",
            destination_url="https://example.com/tickets",
        )
        validated = validate_project_form(values, ProjectType.MUSIC)

        self.assertEqual(validated.channel_url, "")
        self.assertEqual(validated.manual_video_urls, values.manual_video_urls)
        self.assertEqual(len(validated.manual_video_urls), MAX_INDIVIDUAL_VIDEO_URLS)
        self.assertEqual(validated.additional_urls, [])

    def test_music_routes_misplaced_youtube_pages_into_festival_video_list(self):
        first = video_url(1)
        second = video_url(2)
        validated = validate_project_form(ProjectFormValues(
            title="Festival Fixture",
            additional_urls=[second, "https://example.com/festival", first],
            manual_video_urls=[first],
            cta_label="Get Tickets",
            destination_url="https://example.com/tickets",
        ), ProjectType.MUSIC)

        self.assertEqual(validated.channel_url, "")
        self.assertEqual(validated.manual_video_urls, [first, second])
        self.assertEqual(validated.additional_urls, ["https://example.com/festival"])

    def test_music_blocks_more_than_twenty_five_unique_individual_videos(self):
        with self.assertRaises(FormValidationError) as context:
            validate_project_form(ProjectFormValues(
                title="Oversized Festival",
                manual_video_urls=[video_url(index) for index in range(1, 27)],
                cta_label="Get Tickets",
                destination_url="https://example.com/tickets",
            ), ProjectType.MUSIC)

        self.assertEqual(context.exception.field, "manual_video_urls")
        self.assertIn("No more than 25", str(context.exception))

    def test_music_form_makes_the_festival_workflow_explicit(self):
        self.assertIn('"YouTube Channel URL (Optional)"', DESKTOP_SOURCE)
        self.assertIn('f"Festival / Individual YouTube Videos (up to {MAX_INDIVIDUAL_VIDEO_URLS})"', DESKTOP_SOURCE)
        self.assertIn('self.manual_vars = [tk.StringVar() for _ in range(MAX_INDIVIDUAL_VIDEO_URLS)]', DESKTOP_SOURCE)
        self.assertIn('"Additional Web Page', DESKTOP_SOURCE)
        self.assertIn('"Channel optional — add up to {MAX_INDIVIDUAL_VIDEO_URLS} videos from any artists."', DESKTOP_SOURCE)


if __name__ == "__main__":
    unittest.main()
