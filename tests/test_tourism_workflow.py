from __future__ import annotations

import importlib.util
import json
import tempfile
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from aggits_video_factory.business_workflow import assemble_tourism_project
from aggits_video_factory.delivery import request_delivery
from aggits_video_factory.diagnostics import close_logging
from aggits_video_factory.desktop_forms import (
    FormValidationError,
    ProjectFormValues,
    project_is_visible_in_tab,
    project_to_form_values,
    validate_project_form,
)
from aggits_video_factory.models import (
    BusinessConfig,
    MusicConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    ProjectValidationError,
    TourismConfig,
    Video,
)
from aggits_video_factory.publisher import Publisher
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.youtube_api import ChannelCatalogue, merge_video_selections


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "templates" / "machine.html").read_text(encoding="utf-8")
MORE_INFO = "https://example.com/tourism-information"
STAY = "https://example.com/accommodation"


def sample_video(index: int = 1) -> Video:
    video_id = f"tourismvideo{index:02d}"
    return Video(
        video_id=video_id,
        title=f"Visit Test Region - Discovery {index}",
        display_title=f"Discovery {index}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        embed_url=f"https://www.youtube.com/embed/{video_id}",
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=120,
        channel_title="Visit Test Region",
        channel_id="UCtourismfixture",
    )


def tourism_project(slug: str = "visit-test-region", title: str = "VISIT TEST REGION") -> Project:
    return Project(
        slug=slug,
        title=title,
        ticker_text="Test destination information.\n\nA second supplied paragraph remains in order.",
        channel_url="https://www.youtube.com/@visittestregion",
        channel_id="UCtourismfixture",
        channel_title="Visit Test Region",
        channel_thumbnail="",
        project_type=ProjectType.TOURISM,
        additional_urls=["https://example.com/context"],
        tourism_config=TourismConfig(more_info_url=MORE_INFO, stay_url=STAY),
        source_channel_url="https://www.youtube.com/@visittestregion",
        manual_video_urls=["https://www.youtube.com/watch?v=tourismvideo01"],
        excluded_video_ids=["excluded-tourism-video"],
        videos=[sample_video(1), sample_video(2)],
    )


def generated(project: Project) -> tuple[dict, str]:
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "site"
        build_project_site(project, output)
        return (
            json.loads((output / "machine.json").read_text(encoding="utf-8")),
            (output / "index.html").read_text(encoding="utf-8"),
        )


class TourismWorkflowTests(unittest.TestCase):
    def test_tourism_model_round_trip_and_optional_urls(self):
        project = tourism_project()
        encoded = project.to_dict()
        restored = Project.from_dict(encoded)

        self.assertEqual(restored.project_type, ProjectType.TOURISM)
        self.assertEqual(restored.tourism_config.more_info_url, MORE_INFO)
        self.assertEqual(restored.tourism_config.stay_url, STAY)
        self.assertIsNone(restored.business_config)
        self.assertIsNone(restored.music_config)
        self.assertEqual(restored.ticker_text, project.ticker_text)
        self.assertEqual(restored.manual_video_urls, project.manual_video_urls)
        self.assertEqual(restored.excluded_video_ids, project.excluded_video_ids)
        UUID(restored.id)

        no_urls = Project.from_dict({**encoded, "tourism_config": {}})
        self.assertIsNone(no_urls.tourism_config.more_info_url)
        self.assertIsNone(no_urls.tourism_config.stay_url)

    def test_tourism_url_validation_rejects_unsafe_protocols(self):
        valid = validate_project_form(ProjectFormValues(
            title="Visit Test Region",
            manual_video_urls=["https://youtu.be/dQw4w9WgXcQ"],
            story_text="Manual destination biography.",
            more_info_url=MORE_INFO,
            stay_url=STAY,
        ), ProjectType.TOURISM)
        self.assertEqual(valid.tourism_config.more_info_url, MORE_INFO)
        self.assertEqual(valid.tourism_config.stay_url, STAY)
        self.assertEqual(valid.tourism_config.primary_cta.cta_type, PrimaryCtaType.MORE_INFO)
        self.assertEqual(valid.tourism_config.primary_cta.destination_url, MORE_INFO)
        self.assertIsNone(valid.business_config)
        self.assertIsNone(valid.music_config)

        for field, values in (
            ("destination_url", {"more_info_url": "javascript:alert(1)", "stay_url": STAY}),
            ("stay_url", {"more_info_url": MORE_INFO, "stay_url": "file:///hotel"}),
        ):
            with self.subTest(field=field), self.assertRaises(FormValidationError) as caught:
                validate_project_form(ProjectFormValues(
                    title="Unsafe Tourism",
                    manual_video_urls=["https://youtu.be/dQw4w9WgXcQ"],
                    **values,
                ), ProjectType.TOURISM)
            self.assertEqual(caught.exception.field, field)

    def test_strict_cross_type_configuration_isolation(self):
        common = dict(
            slug="isolation",
            title="Isolation",
            ticker_text="Bio",
            channel_url="",
            channel_id="",
            channel_title="",
            channel_thumbnail="",
        )
        with self.assertRaises(ProjectValidationError):
            Project(**common, project_type=ProjectType.TOURISM, business_config=BusinessConfig())
        with self.assertRaises(ProjectValidationError):
            Project(**common, project_type=ProjectType.TOURISM, music_config=MusicConfig())
        with self.assertRaises(ProjectValidationError):
            Project(**common, project_type=ProjectType.BUSINESS, tourism_config=TourismConfig())
        with self.assertRaises(ProjectValidationError):
            Project(**common, project_type=ProjectType.MUSIC, tourism_config=TourismConfig(), music_config=MusicConfig(
                PrimaryCta(PrimaryCtaType.SPOTIFY, "https://example.com/music")
            ))

    def test_tourism_form_assembly_edit_round_trip_and_changes_pending(self):
        values = validate_project_form(ProjectFormValues(
            title="Visit Test Region",
            channel_url="https://www.youtube.com/@visittestregion",
            additional_urls=["https://example.com/context"],
            story_text="Manual tourism bio.",
            manual_video_urls=["https://youtu.be/dQw4w9WgXcQ"],
            more_info_url=MORE_INFO,
            stay_url=STAY,
        ), ProjectType.TOURISM)
        catalogue = ChannelCatalogue("UCtourismfixture", "Visit Test Region", values.channel_url, "", [sample_video(1)])
        created = assemble_tourism_project(
            values=values,
            catalogue=catalogue,
            selected_videos=[sample_video(1)],
            reviewed_videos=[sample_video(1), sample_video(2)],
            source_results=[],
            slug="visit-test-region",
        )
        original_id = created.id
        created.status = "published"
        created.published_url = "https://example.com/crispy-bits/visit-test-region/"
        created.publication_revision = "a" * 40

        edited_values = validate_project_form(replace(
            project_to_form_values(created),
            title="RENAMED DESTINATION",
            story_text="Edited manual tourism bio.",
            destination_url="https://example.com/tourism-information-b",
            more_info_url="https://example.com/tourism-information-b",
            stay_url="https://example.com/accommodation-b",
        ), ProjectType.TOURISM)
        edited = assemble_tourism_project(
            values=edited_values,
            catalogue=catalogue,
            selected_videos=[sample_video(2)],
            reviewed_videos=[sample_video(1), sample_video(2)],
            source_results=[],
            slug="ignored-new-slug",
            existing=created,
        )
        self.assertEqual(edited.id, original_id)
        self.assertEqual(edited.slug, "visit-test-region")
        self.assertEqual(edited.published_url, created.published_url)
        self.assertEqual(edited.status, "changes_pending")
        self.assertEqual(edited.tourism_config.more_info_url, "https://example.com/tourism-information-b")
        self.assertEqual(edited.tourism_config.stay_url, "https://example.com/accommodation-b")

    def test_shared_library_supports_two_tourism_projects_and_cross_type_collision(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            business = Project(
                slug="great-ocean-road", title="Great Ocean Road", ticker_text="Business bio", channel_url="",
                channel_id="", channel_title="", channel_thumbnail="", project_type=ProjectType.BUSINESS,
            )
            store.save_project(business)
            second_slug = store.allocate_slug("Great Ocean Road")
            first = tourism_project(second_slug, "Great Ocean Road")
            second = tourism_project("visit-another-region", "Visit Another Region")
            second.tourism_config = TourismConfig("https://example.com/another-info", "https://example.com/another-stay")
            second.ticker_text = "Independent second bio."
            store.save_project(first)
            store.save_project(second)

            projects = store.list_projects()
            tourism = [item for item in projects if project_is_visible_in_tab(item, ProjectType.TOURISM)]
            self.assertEqual(second_slug, "great-ocean-road-2")
            self.assertEqual(len(tourism), 2)
            self.assertEqual(len({item.id for item in tourism}), 2)
            self.assertEqual(len({item.slug for item in projects}), 3)
            self.assertFalse(project_is_visible_in_tab(first, ProjectType.BUSINESS))
            self.assertEqual(store.load_project(second.slug).ticker_text, "Independent second bio.")

    def test_shared_youtube_review_preserves_manual_priority_for_tourism(self):
        manual = [sample_video(2)]
        selected = merge_video_selections(manual, [sample_video(1), sample_video(2)], maximum=2)
        self.assertEqual([item.video_id for item in selected], ["tourismvideo02", "tourismvideo01"])

    def test_tourism_machine_preserves_legacy_urls_but_uses_one_primary_destination(self):
        config, page = generated(tourism_project())
        self.assertEqual(config["projectType"], "tourism")
        self.assertEqual(config["tourismConfig"], {
            "moreInfoURL": MORE_INFO,
            "moreInfoEnabled": True,
            "stayURL": STAY,
            "stayEnabled": True,
        })
        self.assertNotIn("musicConfig", config)
        self.assertNotIn("shopURL", config["customerConfig"])
        self.assertEqual(config["customerConfig"]["primaryAction"]["displayLabel"], "MORE INFO")
        self.assertEqual(config["customerConfig"]["primaryAction"]["destinationURL"], MORE_INFO)
        self.assertIn(">MORE INFO</b>", page)
        self.assertIn("const primaryAction = config.customerConfig?.primaryAction", SCRIPT)
        self.assertIn("window.open(plaqueDestination, '_blank', 'noopener,noreferrer')", SCRIPT)
        self.assertIn("window.open(primaryActionDestination, '_blank', 'noopener,noreferrer')", SCRIPT)
        self.assertNotEqual(MORE_INFO, STAY)

    def test_tourism_missing_urls_never_fall_back(self):
        project = tourism_project()
        project.tourism_config = TourismConfig()
        config, _ = generated(project)
        self.assertFalse(config["tourismConfig"]["moreInfoEnabled"])
        self.assertFalse(config["tourismConfig"]["stayEnabled"])
        self.assertIsNone(config["tourismConfig"]["moreInfoURL"])
        self.assertIsNone(config["tourismConfig"]["stayURL"])
        self.assertFalse(config["customerConfig"]["primaryAction"]["enabled"])
        self.assertEqual(config["customerConfig"]["primaryAction"]["destinationURL"], "")
        self.assertIn("shopPlaqueEnabled = Boolean(plaqueDestination)", SCRIPT)
        self.assertIn("primaryActionButton.disabled = !primaryActionDestination", SCRIPT)

    def test_tourism_url_edits_and_removal_do_not_leave_stale_destinations(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            project = tourism_project()
            build_project_site(project, output)
            first = (output / "machine.json").read_text(encoding="utf-8")
            self.assertIn(MORE_INFO, first)
            self.assertIn(STAY, first)

            project.tourism_config = TourismConfig(
                "https://example.com/tourism-information-b",
                "https://example.com/accommodation-b",
            )
            build_project_site(project, output)
            edited = json.loads((output / "machine.json").read_text(encoding="utf-8"))
            self.assertEqual(edited["tourismConfig"]["moreInfoURL"], "https://example.com/tourism-information-b")
            self.assertEqual(edited["tourismConfig"]["stayURL"], "https://example.com/accommodation-b")

            project.tourism_config = TourismConfig()
            build_project_site(project, output)
            removed = (output / "machine.json").read_text(encoding="utf-8")
            self.assertNotIn("tourism-information-b", removed)
            self.assertNotIn("accommodation-b", removed)

    def test_tourism_ticker_is_title_and_manual_bio_on_shared_continuous_lifecycle(self):
        project = tourism_project()
        config, page = generated(project)
        story = page.split('<section class="customer-story"', 1)[1].split("</section>", 1)[0]
        self.assertIn(project.title, story)
        self.assertIn(project.ticker_text, story)
        for heading in ("THE STORY SO FAR", "THE DESTINATION", "THE JOURNEY", "WHAT TO SEE"):
            self.assertNotIn(heading, story)
        self.assertEqual(config["customerConfig"]["customerStorySections"], [])
        self.assertIn("if ((storyTickerStarted || storyTickerStarting) && !force) return;", SCRIPT)
        spin_block = SCRIPT.split("  async function spin() {", 1)[1].split("  function resetLever", 1)[0]
        self.assertNotIn("startStoryTicker", spin_block)
        self.assertNotIn("is-scrolling", spin_block)

    def test_tourism_publisher_reuses_shared_namespace_publish_unpublish_and_republish(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            project = tourism_project()
            store.save_project(project)
            build_project_site(project, store.project_dir(project.slug) / "site")
            workspace = Path(temporary) / "workspace"
            revisions = iter(["revision-one", "revision-two", "revision-three"])

            def fake_git(command, **_kwargs):
                if "diff" in command:
                    return f"public/crispy-bits/{project.slug}"
                if "rev-parse" in command:
                    return next(revisions)
                return ""

            publisher = Publisher(store)
            with patch.object(publisher, "ensure_workspace", return_value=workspace), \
                    patch.object(publisher, "_wait_for_publication"), \
                    patch.object(publisher, "_wait_for_unpublication"), \
                    patch("aggits_video_factory.publisher._run", side_effect=fake_git):
                first_url, _ = publisher.publish(project)
                project.status = "published"
                store.save_project(project)
                publisher.unpublish(project)
                project.status = "unpublished"
                project.published_url = None
                project.publication_revision = None
                store.save_project(project)
                build_project_site(project, store.project_dir(project.slug) / "site")
                second_url, _ = publisher.publish(project)

            self.assertEqual(first_url, second_url)
            library = json.loads((workspace / "public" / "crispy-bits" / "library.json").read_text(encoding="utf-8"))
            self.assertEqual(library[0]["projectType"], "tourism")

    def test_tourism_publication_reconciliation_uses_shared_state_machine(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            project = tourism_project()
            publisher = Publisher(store)
            operation = publisher._start_operation(project, "publish")
            operation.target_revision = "b" * 40
            operation.expected_url = "https://example.com/crispy-bits/visit-test-region/"
            operation.verification_status = "pending"
            project.status = "verification_pending"
            store.save_project(project)

            with patch.object(publisher, "_publication_ready", return_value=True):
                result = publisher.reconcile(project)
            restored = store.load_project(project.slug)
            self.assertEqual(result, "published")
            self.assertEqual(restored.status, "published")
            self.assertEqual(restored.project_type, ProjectType.TOURISM)
            self.assertEqual(restored.publication_revision, "b" * 40)
            self.assertEqual(restored.tourism_config.more_info_url, MORE_INFO)
            self.assertEqual(restored.tourism_config.stay_url, STAY)

    def test_tourism_authenticated_delivery_payload_is_type_aware(self):
        project = tourism_project()
        project.status = "published"
        project.published_url = "https://raggedya.github.io/aggits-video-jukebox/crispy-bits/visit-test-region/"
        project.publication_revision = "a" * 40
        response = Mock(ok=True, status_code=201)
        response.json.return_value = {"ok": True, "id": "mock-delivery"}
        with patch("aggits_video_factory.delivery.requests.post", return_value=response) as post:
            request_delivery(project, "operator@example.com", secret="test-secret", timestamp=1_700_000_000, nonce="c" * 32)
        payload = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(payload["projectType"], "tourism")
        self.assertEqual(payload["productName"], "CRISPY BITS TOURISM")
        self.assertNotIn("moreInfoURL", payload)
        self.assertNotIn("stayURL", payload)

    def test_desktop_declares_three_tabs_in_required_order(self):
        desktop_path = ROOT / "desktop" / "video_jukebox_factory.py"
        source = desktop_path.read_text(encoding="utf-8")
        self.assertIn(
            "[ProjectType.BUSINESS, ProjectType.MUSIC, ProjectType.TOURISM]",
            source,
        )
        self.assertIn('"Primary Call to Action"', source)
        self.assertIn('"CTA Destination URL"', source)
        self.assertIn('"Custom Button Label"', source)
        self.assertIn('"Bio / About"', source)

        root = tk.Tk()
        root.withdraw()
        try:
            spec = importlib.util.spec_from_file_location("tourism_desktop_smoke", desktop_path)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            form = module.ProjectForm(root, ProjectType.TOURISM, lambda: None, lambda: None)
            self.assertIn("cta_type", form.field_widgets)
            self.assertIn("destination_url", form.field_widgets)
            self.assertIn("custom_label", form.field_widgets)
            self.assertNotIn("more_info_url", form.field_widgets)
            self.assertNotIn("stay_url", form.field_widgets)
            form.destroy()
        finally:
            root.destroy()

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            module, "ProjectStore", return_value=ProjectStore(Path(temporary))
        ):
            app = module.Factory()
            app.withdraw()
            try:
                self.assertEqual(
                    [app.notebook.tab(index, "text") for index in range(app.notebook.index("end"))],
                    ["BUSINESS", "MUSIC", "TOURISM"],
                )
                for width, height in ((1320, 820), (1120, 720)):
                    app.geometry(f"{width}x{height}")
                    app.update_idletasks()
                    self.assertGreaterEqual(app.winfo_reqwidth(), 1)
                    self.assertGreaterEqual(app.winfo_reqheight(), 1)
            finally:
                app.destroy()
                close_logging(Path(temporary))


if __name__ == "__main__":
    unittest.main()
