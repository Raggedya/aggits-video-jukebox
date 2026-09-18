from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

import requests

from aggits_video_factory.business_workflow import assemble_music_project
from aggits_video_factory.delivery import DeliveryError, request_delivery
from aggits_video_factory.desktop_forms import ProjectFormValues, validate_project_form
from aggits_video_factory.models import (
    PRIMARY_CTA_LABELS,
    BusinessConfig,
    MusicConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    ProjectValidationError,
    Video,
)
from aggits_video_factory.preview import PreviewServer
from aggits_video_factory.publisher import PublishError, Publisher
from aggits_video_factory import site_builder
from aggits_video_factory.site_builder import _story_sections, build_project_site, create_qr_card
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.supplementary_sources import SupplementarySourceResult, retrieve_supplementary_sources
from aggits_video_factory.youtube_api import ChannelCatalogue


CHANNEL = "https://www.youtube.com/@thefakeaways"
VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def sample_video(index: int = 1) -> Video:
    video_id = f"musicvideo{index:02d}"
    return Video(
        video_id=video_id,
        title=f"The Fakeaways - Song {index} (Official Music Video)",
        display_title=f"Song {index}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        embed_url=f"https://www.youtube.com/embed/{video_id}?autoplay=0",
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=210,
        channel_title="The Fakeaways",
        channel_id="UCmusicfixture",
    )


def music_project(
    *,
    cta_type: PrimaryCtaType = PrimaryCtaType.SPOTIFY,
    destination: str = "https://example.com/spotify",
    custom_label: str | None = None,
    slug: str = "the-fakeaways",
) -> Project:
    return Project(
        slug=slug,
        title="THE FAKEAWAYS",
        ticker_text="The band formed in 2018. Their music grew through live shows. A new album followed.",
        channel_url=CHANNEL,
        channel_id="UCmusicfixture",
        channel_title="The Fakeaways",
        channel_thumbnail="",
        project_type=ProjectType.MUSIC,
        additional_urls=["https://example.com/artist"],
        music_config=MusicConfig(primary_cta=PrimaryCta(
            cta_type=cta_type,
            destination_url=destination,
            custom_label=custom_label,
        )),
        source_channel_url=CHANNEL,
        manual_video_urls=[VIDEO_URL],
        videos=[sample_video(1), sample_video(2)],
    )


def business_project() -> Project:
    return Project(
        slug="shared-name",
        title="Shared Name",
        ticker_text="We create custom builds and put the customer first.",
        channel_url=CHANNEL,
        channel_id="UCbusinessfixture",
        channel_title="Shared Name",
        channel_thumbnail="",
        project_type=ProjectType.BUSINESS,
        additional_urls=["https://example.com/business"],
        business_config=BusinessConfig(shop_url="https://example.com/shop"),
        videos=[sample_video(1)],
    )


class MusicWorkflowTests(unittest.TestCase):
    def test_music_additional_url_matrix_is_bounded_recoverable_and_not_a_cta(self):
        for count in range(4):
            urls = [f"https://source-{index}.example/info" for index in range(count)]
            values = validate_project_form(ProjectFormValues(
                title="The Fakeaways",
                channel_url=CHANNEL,
                additional_urls=urls,
                story_text="Manual artist biography.",
                cta_label="Official Website",
                destination_url="https://artist.example/official",
            ), ProjectType.MUSIC)
            self.assertEqual(values.additional_urls, urls)
            self.assertEqual(values.story_text, "Manual artist biography.")
            self.assertEqual(values.music_config.primary_cta.destination_url, "https://artist.example/official")

        class UnreachableSession:
            def get(self, *_args, **_kwargs):
                raise requests.ConnectionError("unreachable")

            def close(self):
                return None

        def public_resolver(*_args, **_kwargs):
            return [(None, None, None, None, ("93.184.216.34", 443))]

        results = retrieve_supplementary_sources(
            ["https://unreachable.example/info", "http://localhost/private"],
            session=UnreachableSession(),
            resolver=public_resolver,
        )
        self.assertEqual([result.status for result in results], ["unavailable", "unavailable"])
        self.assertIn("unreachable", results[0].error)
        self.assertIn("public host", results[1].error)

    def test_music_cta_matrix_generates_deterministic_labels_destinations_and_button_configuration(self):
        matrix = list(PRIMARY_CTA_LABELS.items()) + [(PrimaryCtaType.CUSTOM, "PRE-ORDER ALBUM")]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (cta_type, expected_label) in enumerate(matrix):
                with self.subTest(cta_type=cta_type.value):
                    destination_url = f"https://example.com/{cta_type.value}"
                    project = music_project(
                        cta_type=cta_type,
                        destination=destination_url,
                        custom_label=expected_label if cta_type is PrimaryCtaType.CUSTOM else "STALE CUSTOM LABEL",
                        slug=f"music-{index}",
                    )
                    destination = root / project.slug
                    build_project_site(project, destination)
                    payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
                    cta = payload["musicConfig"]["primaryCTA"]
                    page = (destination / "index.html").read_text(encoding="utf-8")
                    script = (destination / "assets" / "video-machine.js").read_text(encoding="utf-8")
                    self.assertEqual(payload["projectType"], "music")
                    self.assertEqual(cta["type"], cta_type.value)
                    self.assertEqual(cta["displayLabel"], expected_label)
                    self.assertEqual(cta["destinationURL"], destination_url)
                    self.assertIn(f"<b>{expected_label}</b>", page)
                    self.assertIn("config.musicConfig?.primaryCTA", script)
                    self.assertIn("window.open(primaryActionDestination, '_blank', 'noopener,noreferrer')", script)
                    self.assertNotIn("shopURL", payload["customerConfig"])
                    self.assertNotIn("shopEnabled", payload["customerConfig"])

    def test_cta_validation_rejects_unsafe_schemes_and_custom_requires_label(self):
        for value in ("javascript:alert(1)", "file:///tmp/music", "data:text/html,hello", "C:\\music\\tickets"):
            with self.subTest(value=value), self.assertRaises(ProjectValidationError):
                PrimaryCta(cta_type=PrimaryCtaType.TICKETS, destination_url=value)
        with self.assertRaisesRegex(ProjectValidationError, "custom label"):
            PrimaryCta(cta_type=PrimaryCtaType.CUSTOM, destination_url="https://example.com/preorder")

    def test_standard_and_custom_cta_round_trip_clears_stale_labels(self):
        standard = PrimaryCta(
            cta_type=PrimaryCtaType.BANDCAMP,
            destination_url="https://example.com/bandcamp",
            display_label="PRE-ORDER ALBUM",
            custom_label="PRE-ORDER ALBUM",
        )
        self.assertEqual(standard.display_label, "BUY ON BANDCAMP")
        custom = PrimaryCta(
            cta_type=PrimaryCtaType.CUSTOM,
            destination_url="https://example.com/preorder",
            display_label="STALE STANDARD LABEL",
            custom_label="PRE-ORDER ALBUM",
        )
        self.assertEqual(custom.display_label, "PRE-ORDER ALBUM")
        restored = Project.from_dict(music_project(
            cta_type=PrimaryCtaType.CUSTOM,
            destination="https://example.com/preorder",
            custom_label="PRE-ORDER ALBUM",
        ).to_dict())
        self.assertEqual(restored.music_config.primary_cta.custom_label, "PRE-ORDER ALBUM")
        self.assertEqual(restored.music_config.primary_cta.destination_url, "https://example.com/preorder")

    def test_cross_type_configuration_isolation_and_business_regression(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            business = business_project()
            music = music_project(destination="https://example.com/tickets", cta_type=PrimaryCtaType.TICKETS)
            build_project_site(business, root / "business")
            build_project_site(music, root / "music")
            business_payload = json.loads((root / "business" / "machine.json").read_text(encoding="utf-8"))
            music_payload = json.loads((root / "music" / "machine.json").read_text(encoding="utf-8"))
            self.assertEqual(business_payload["customerConfig"]["shopURL"], "https://example.com/shop")
            self.assertNotIn("musicConfig", business_payload)
            self.assertEqual(music_payload["musicConfig"]["primaryCTA"]["destinationURL"], "https://example.com/tickets")
            self.assertNotIn("shopURL", music_payload["customerConfig"])
            self.assertNotIn("shopEnabled", music_payload["customerConfig"])
            self.assertEqual(business.business_config.shop_url, "https://example.com/shop")
            self.assertIsNone(business.music_config)
            self.assertIsNone(music.business_config)

    def test_music_cta_rebuild_removes_stale_destination_and_custom_label(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "site"
            project = music_project(
                cta_type=PrimaryCtaType.CUSTOM,
                destination="https://example.com/preorder",
                custom_label="PRE-ORDER ALBUM",
            )
            build_project_site(project, destination)
            self.assertIn("PRE-ORDER ALBUM", (destination / "machine.json").read_text(encoding="utf-8"))
            project.music_config = MusicConfig(primary_cta=PrimaryCta(
                cta_type=PrimaryCtaType.TICKETS,
                destination_url="https://example.com/tickets",
                custom_label="PRE-ORDER ALBUM",
            ))
            build_project_site(project, destination)
            rebuilt = (destination / "machine.json").read_text(encoding="utf-8")
            page = (destination / "index.html").read_text(encoding="utf-8")
            self.assertIn("GET TICKETS", rebuilt)
            self.assertIn("https://example.com/tickets", rebuilt)
            self.assertNotIn("PRE-ORDER ALBUM", rebuilt)
            self.assertNotIn("https://example.com/preorder", rebuilt)
            self.assertIn("<b>GET TICKETS</b>", page)

    def test_music_story_headings_are_type_appropriate_and_business_story_is_unchanged(self):
        music_text = "The band formed in 2018. Their sound developed on stage. The album was released in 2025."
        music_sections = _story_sections(music_text, "The Fakeaways", ProjectType.MUSIC)
        music_headings = {item["heading"] for item in music_sections}
        self.assertNotIn("CUSTOM BUILDS", music_headings)
        self.assertNotIn("CUSTOMER FIRST", music_headings)
        self.assertTrue(music_headings & {"THE BAND", "THE MUSIC", "ON STAGE", "THE RELEASES", "2018", "2025"})
        business_text = "We create custom builds. The customer comes first."
        self.assertEqual(
            _story_sections(business_text, "Example", ProjectType.BUSINESS),
            _story_sections(business_text, "Example"),
        )
        business_headings = [item["heading"] for item in _story_sections(business_text, "Example")]
        self.assertIn("CUSTOM BUILDS", business_headings)
        self.assertIn("CUSTOMER FIRST", business_headings)

    def test_reviewed_music_assembly_reuses_shared_video_review_and_preserves_manual_story(self):
        values = validate_project_form(ProjectFormValues(
            title="The Fakeaways",
            channel_url=CHANNEL,
            additional_urls=["https://example.com/artist", "https://example.com/label"],
            story_text="Manual artist story remains authoritative.",
            manual_video_urls=[VIDEO_URL],
            cta_label="Listen on Spotify",
            destination_url="https://example.com/spotify",
        ), ProjectType.MUSIC)
        catalogue = ChannelCatalogue(
            channel_id="UCmusicfixture",
            channel_title="The Fakeaways",
            channel_url=CHANNEL,
            channel_thumbnail="",
            videos=[sample_video(1), sample_video(2)],
        )
        results = [
            SupplementarySourceResult(url="https://example.com/artist", final_url="https://example.com/artist", status="retrieved", text="Supplementary artist context."),
            SupplementarySourceResult(url="https://example.com/label", final_url="", status="unavailable", error="unreachable"),
        ]
        project = assemble_music_project(
            values=values,
            catalogue=catalogue,
            selected_videos=[sample_video(1)],
            reviewed_videos=catalogue.videos,
            source_results=results,
            slug="the-fakeaways",
        )
        UUID(project.id)
        self.assertEqual(project.ticker_text, "Manual artist story remains authoritative.")
        self.assertEqual(project.additional_urls, ["https://example.com/artist", "https://example.com/label"])
        self.assertEqual(project.manual_video_urls, [VIDEO_URL])
        self.assertEqual(project.music_config.primary_cta.destination_url, "https://example.com/spotify")
        self.assertEqual(project.extra_fields["additional_source_context"][1]["status"], "unavailable")
        self.assertEqual(project.excluded_video_ids, ["musicvideo02"])

    def test_music_identity_cta_edits_and_publication_lifecycle_remain_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            store.project_dir("shared-name").mkdir(parents=True)
            slug = store.allocate_slug("Shared Name")
            self.assertEqual(slug, "shared-name-2")
            project = music_project(slug=slug)
            original_id = project.id
            store.save_project(project)
            build_project_site(project, store.project_dir(project.slug) / "site")
            workspace = Path(temporary) / "publisher-workspace"
            revisions = iter(["revision-one", "revision-two", "revision-three", "revision-four"])

            def fake_git(command, **_kwargs):
                if "diff" in command:
                    return f"public/crispy-bits/{project.slug}"
                if "rev-parse" in command:
                    return next(revisions)
                return ""

            publisher = Publisher(store)
            with patch.object(publisher, "ensure_workspace", return_value=workspace), \
                    patch.object(publisher, "_wait_for_publication"), \
                    patch("aggits_video_factory.publisher._run", side_effect=fake_git):
                first_url, first_revision = publisher.publish(project)
                project.status = "published"
                project.published_url = first_url
                project.publication_revision = first_revision
                store.save_project(project)

                project.title = "A COMPLETELY DIFFERENT ARTIST NAME"
                project.music_config = MusicConfig(primary_cta=PrimaryCta(
                    cta_type=PrimaryCtaType.BANDCAMP,
                    destination_url="https://example.com/bandcamp",
                ))
                project.status = "changes_pending"
                build_project_site(project, store.project_dir(project.slug) / "site")
                store.save_project(project)
                second_url, second_revision = publisher.publish(project)
                project.status = "published"
                project.publication_revision = second_revision
                store.save_project(project)

                publisher.unpublish(project)
                project.status = "unpublished"
                project.published_url = None
                project.publication_revision = None
                store.save_project(project)
                build_project_site(project, store.project_dir(project.slug) / "site")
                third_url, third_revision = publisher.publish(project)
                project.status = "published"
                project.published_url = third_url
                project.publication_revision = third_revision
                store.save_project(project)

            restored = store.load_project(project.slug)
            self.assertEqual(restored.id, original_id)
            self.assertEqual(restored.slug, "shared-name-2")
            self.assertEqual(first_url, second_url)
            self.assertEqual(first_url, third_url)
            self.assertEqual(restored.published_url, first_url)
            self.assertEqual(restored.music_config.primary_cta.cta_type, PrimaryCtaType.BANDCAMP)
            self.assertEqual(restored.music_config.primary_cta.destination_url, "https://example.com/bandcamp")
            library = json.loads((workspace / "public" / "crispy-bits" / "library.json").read_text(encoding="utf-8"))
            self.assertEqual(library[0]["projectType"], "music")

    def test_publisher_accepts_both_supported_types_and_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            publisher = Publisher(store)
            for project in (business_project(), music_project(slug="music-project")):
                build_project_site(project, store.project_dir(project.slug) / "site")
                workspace = Path(temporary) / project.slug
                with patch.object(publisher, "ensure_workspace", return_value=workspace), \
                        patch.object(publisher, "_wait_for_publication"), \
                        patch("aggits_video_factory.publisher._run", side_effect=lambda command, **_kwargs: "revision" if "rev-parse" in command else "staged" if "diff" in command else ""):
                    public_url, revision = publisher.publish(project)
                self.assertTrue(public_url.endswith(f"/{project.slug}/"))
                self.assertEqual(revision, "revision")
            with self.assertRaisesRegex(PublishError, "Unsupported project type"):
                publisher.publish(SimpleNamespace(project_type="unknown"))

    def test_music_delivery_payload_is_intercepted_and_type_aware(self):
        project = music_project()
        project.published_url = "https://raggedya.github.io/aggits-video-jukebox/crispy-bits/the-fakeaways/"
        project.publication_revision = "a" * 40
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"ok": True}
        with patch("aggits_video_factory.delivery.requests.post", return_value=response) as post:
            request_delivery(project, " Owner@Example.com ")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["slug"], project.slug)
        self.assertEqual(payload["title"], project.title)
        self.assertEqual(payload["publicUrl"], project.published_url)
        self.assertEqual(payload["qrUrl"], f"{project.published_url.rstrip('/')}/qr-card.png")
        self.assertEqual(payload["revision"], "a" * 40)
        self.assertEqual(payload["projectType"], "music")
        self.assertEqual(payload["productName"], "CRISPY BITS MUSIC")
        with self.assertRaisesRegex(DeliveryError, "Unsupported project type"):
            request_delivery(SimpleNamespace(project_type="unknown"), "owner@example.com")

    def test_music_qr_uses_the_expected_stable_public_url(self):
        project = music_project()
        project.published_url = "https://raggedya.github.io/aggits-video-jukebox/crispy-bits/the-fakeaways/"
        captured: list[str] = []
        original_add_data = site_builder.qrcode.QRCode.add_data

        def capture_add_data(instance, data, *args, **kwargs):
            captured.append(str(data))
            return original_add_data(instance, data, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            site_builder.qrcode.QRCode,
            "add_data",
            new=capture_add_data,
        ):
            destination = Path(temporary) / "music-qr.png"
            create_qr_card(project, destination)
            self.assertTrue(destination.is_file())
        self.assertEqual(captured, [project.published_url])

    def test_local_standard_and_custom_music_previews_serve_page_config_and_shared_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects = [
                music_project(),
                music_project(
                    cta_type=PrimaryCtaType.CUSTOM,
                    destination="https://example.com/preorder",
                    custom_label="PRE-ORDER ALBUM",
                    slug="the-fakeaways-preorder",
                ),
            ]
            for project in projects:
                destination = root / project.slug
                build_project_site(project, destination)
                preview = PreviewServer()
                try:
                    url = preview.start(destination)
                    page = requests.get(url, timeout=5)
                    config = requests.get(f"{url}machine.json", timeout=5).json()
                    script = requests.get(f"{url}assets/video-machine.js", timeout=5).text
                finally:
                    preview.stop()
                cta = project.music_config.primary_cta
                self.assertEqual(page.status_code, 200)
                self.assertIn(f"<b>{cta.display_label}</b>", page.text)
                self.assertIn('data-action="shop"', page.text)
                self.assertIn('data-action="play"', page.text)
                self.assertIn('data-action="spin-again"', page.text)
                self.assertIn("THE STORY SO FAR", page.text)
                self.assertEqual(config["musicConfig"]["primaryCTA"]["destinationURL"], cta.destination_url)
                self.assertIn("openPrimaryAction", script)
                self.assertIn("spinSingleReel", script)
                self.assertNotIn("shopURL", config["customerConfig"])


if __name__ == "__main__":
    unittest.main()
