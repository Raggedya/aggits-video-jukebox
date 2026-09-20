from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.desktop_forms import (
    CTA_CHOICES,
    DEFAULT_CTA_LABEL,
    FormValidationError,
    ProjectFormValues,
    build_local_music_project,
    project_is_visible_in_tab,
    project_to_form_values,
    validate_project_form,
)
from aggits_video_factory.models import BusinessConfig, PrimaryCtaType, Project, ProjectType
from aggits_video_factory.store import ProjectStore


CHANNEL = "https://www.youtube.com/@example"
VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class DesktopFormTests(unittest.TestCase):
    def test_business_form_binds_schema_v3_fields_without_mixing_url_types(self):
        values = ProjectFormValues(
            title="  Great   Alpine Caravans  ",
            channel_url=CHANNEL,
            additional_urls=["https://example.com", "", "https://example.com/about"],
            story_text="A business story.",
            manual_video_urls=[VIDEO, ""],
            shop_url="https://example.com/shop",
        )
        validated = validate_project_form(values, ProjectType.BUSINESS)
        self.assertEqual(validated.title, "Great Alpine Caravans")
        self.assertEqual(validated.additional_urls, ["https://example.com", "https://example.com/about"])
        self.assertEqual(validated.manual_video_urls, [VIDEO])
        self.assertEqual(validated.business_config, BusinessConfig(shop_url="https://example.com/shop"))
        self.assertIsNone(validated.music_config)

    def test_music_standard_cta_maps_visible_label_to_stable_type(self):
        self.assertEqual(
            CTA_CHOICES,
            (
                ("Listen on Spotify", PrimaryCtaType.SPOTIFY),
                ("Buy on Bandcamp", PrimaryCtaType.BANDCAMP),
                ("Buy Music", PrimaryCtaType.BUY_MUSIC),
                ("Buy Merch", PrimaryCtaType.MERCH),
                ("Get Tickets", PrimaryCtaType.TICKETS),
                ("Apple Music", PrimaryCtaType.APPLE_MUSIC),
                ("Official Website", PrimaryCtaType.OFFICIAL_WEBSITE),
                ("Book Now", PrimaryCtaType.BOOK_NOW),
                ("Book Us", PrimaryCtaType.BOOK_US),
                ("SoundCloud", PrimaryCtaType.SOUNDCLOUD),
                ("Custom", PrimaryCtaType.CUSTOM),
            ),
        )
        values = ProjectFormValues(
            title="Example Band",
            channel_url=CHANNEL,
            cta_label="Listen on Spotify",
            destination_url="https://open.spotify.com/artist/example",
        )
        validated = validate_project_form(values, ProjectType.MUSIC)
        cta = validated.music_config.primary_cta
        self.assertEqual(cta.cta_type, PrimaryCtaType.SPOTIFY)
        self.assertEqual(cta.display_label, "LISTEN ON SPOTIFY")
        self.assertIsNone(validated.business_config)

    def test_custom_music_cta_requires_button_label_and_destination(self):
        missing_label = ProjectFormValues(
            title="Example Band",
            channel_url=CHANNEL,
            cta_label="Custom",
            destination_url="https://example.com/support",
        )
        with self.assertRaises(FormValidationError) as context:
            validate_project_form(missing_label, ProjectType.MUSIC)
        self.assertEqual(context.exception.field, "custom_label")

        missing_url = ProjectFormValues(
            title="Example Band",
            channel_url=CHANNEL,
            cta_label=DEFAULT_CTA_LABEL,
        )
        with self.assertRaises(FormValidationError) as context:
            validate_project_form(missing_url, ProjectType.MUSIC)
        self.assertEqual(context.exception.field, "destination_url")

    def test_form_validation_keeps_additional_and_manual_video_urls_separate(self):
        values = ProjectFormValues(
            title="Manual Source",
            additional_urls=["https://example.com/info"],
            manual_video_urls=[VIDEO],
        )
        validated = validate_project_form(values, ProjectType.BUSINESS)
        self.assertEqual(validated.channel_url, "")
        self.assertEqual(validated.additional_urls, ["https://example.com/info"])
        self.assertEqual(validated.manual_video_urls, [VIDEO])

    def test_local_music_save_round_trip_preserves_id_slug_and_type_on_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            first_values = validate_project_form(
                ProjectFormValues(
                    title="Example Band",
                    channel_url=CHANNEL,
                    cta_label="Buy on Bandcamp",
                    destination_url="https://example.bandcamp.com",
                ),
                ProjectType.MUSIC,
            )
            original = build_local_music_project(first_values, store.allocate_slug(first_values.title))
            store.save_project(original)

            edited_values = validate_project_form(
                ProjectFormValues(
                    title="Example Band Renamed",
                    channel_url=CHANNEL,
                    cta_label="Get Tickets",
                    destination_url="https://example.com/tickets",
                ),
                ProjectType.MUSIC,
            )
            edited = build_local_music_project(edited_values, "must-not-replace-existing", original)
            store.save_project(edited)
            restored = store.load_project(original.slug)
            self.assertEqual(restored.id, original.id)
            self.assertEqual(restored.slug, original.slug)
            self.assertEqual(restored.project_type, ProjectType.MUSIC)
            self.assertEqual(restored.title, "Example Band Renamed")
            self.assertEqual(restored.music_config.primary_cta.cta_type, PrimaryCtaType.TICKETS)

    def test_library_filter_and_form_round_trip_respect_project_type(self):
        business = Project(
            slug="business",
            title="Business",
            ticker_text="Business story",
            channel_url=CHANNEL,
            channel_id="",
            channel_title="Business",
            channel_thumbnail="",
            project_type=ProjectType.BUSINESS,
            additional_urls=["https://example.com/about"],
            business_config=BusinessConfig(shop_url="https://example.com/shop"),
            source_channel_url=CHANNEL,
            manual_video_urls=[VIDEO],
        )
        values = project_to_form_values(business)
        self.assertEqual(values.shop_url, "https://example.com/shop")
        self.assertEqual(values.additional_urls, ["https://example.com/about"])
        self.assertTrue(project_is_visible_in_tab(business, ProjectType.BUSINESS))
        self.assertFalse(project_is_visible_in_tab(business, ProjectType.MUSIC))


if __name__ == "__main__":
    unittest.main()
