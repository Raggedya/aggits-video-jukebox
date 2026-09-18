from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

import requests

from aggits_video_factory.business_workflow import assemble_business_project
from aggits_video_factory.delivery import DeliveryError, request_delivery
from aggits_video_factory.desktop_forms import ProjectFormValues, validate_project_form
from aggits_video_factory.models import BusinessConfig, MusicConfig, Project, ProjectType, Video
from aggits_video_factory.preview import PreviewServer
from aggits_video_factory.publisher import Publisher
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.supplementary_sources import (
    MAX_EXTRACTED_TEXT,
    MAX_RESPONSE_BYTES,
    SupplementarySourceResult,
    retrieve_supplementary_source,
    retrieve_supplementary_sources,
)
from aggits_video_factory.youtube_api import ChannelCatalogue


def sample_video() -> Video:
    return Video(
        video_id="dQw4w9WgXcQ",
        title="Example Business Video",
        display_title="Example Business Video",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        embed_url="https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=0",
        thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=180,
        channel_title="Example Business",
        channel_id="UCexample",
    )


def business_project(*, shop_url: str | None = None, slug: str = "test-business-a") -> Project:
    return Project(
        slug=slug,
        title="TEST BUSINESS A",
        ticker_text="The manually supplied Business story remains authoritative.",
        channel_url="https://www.youtube.com/channel/UCexample",
        channel_id="UCexample",
        channel_title="Example Business",
        channel_thumbnail="",
        project_type=ProjectType.BUSINESS,
        additional_urls=["https://example.com/about"],
        business_config=BusinessConfig(shop_url=shop_url),
        source_channel_url="https://www.youtube.com/@example",
        manual_video_urls=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
        videos=[sample_video()],
    )


class FakeResponse:
    def __init__(self, status_code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.closed = False
        self.ok = 200 <= status_code < 300
        self.content = body

    def iter_content(self, chunk_size: int):
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index:index + chunk_size]

    def close(self) -> None:
        self.closed = True

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self) -> None:
        self.closed = True


def public_resolver(host: str, port: int, **_kwargs):
    return [(2, 1, 6, "", ("8.8.8.8", port))]


class BusinessWorkflowTests(unittest.TestCase):
    def test_reviewed_business_assembly_creates_draft_then_preserves_published_identity_as_changes_pending(self):
        values = validate_project_form(
            ProjectFormValues(
                title="TEST BUSINESS A",
                channel_url="https://www.youtube.com/@example",
                additional_urls=["https://example.com/about"],
                story_text="Manual story A",
                manual_video_urls=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
                shop_url="https://example.com/shop-a",
            ),
            ProjectType.BUSINESS,
        )
        catalogue = ChannelCatalogue(
            channel_id="UCexample",
            channel_title="Example Business",
            channel_url="https://www.youtube.com/channel/UCexample",
            channel_thumbnail="",
            videos=[sample_video()],
        )
        source = SupplementarySourceResult(
            url="https://example.com/about",
            final_url="https://example.com/about",
            status="retrieved",
            text="Supplementary context",
        )
        draft = assemble_business_project(
            values=values,
            catalogue=catalogue,
            selected_videos=catalogue.videos,
            reviewed_videos=catalogue.videos,
            source_results=[source],
            slug="test-business-a",
        )
        self.assertEqual(draft.status, "draft")
        UUID(draft.id)

        draft.status = "published"
        draft.published_url = "https://raggedya.github.io/aggits-video-jukebox/crispy-bits/test-business-a/"
        draft.published_at = "2026-09-18T00:00:00Z"
        draft.publication_revision = "revision-one"
        draft.delivery_status = "sent"
        original_id = draft.id
        values_b = validate_project_form(
            ProjectFormValues(
                title="COMPLETELY DIFFERENT BUSINESS TITLE",
                channel_url="https://www.youtube.com/@example",
                story_text="Manual story B",
                manual_video_urls=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
                shop_url="https://example.com/shop-b",
            ),
            ProjectType.BUSINESS,
        )
        edited = assemble_business_project(
            values=values_b,
            catalogue=catalogue,
            selected_videos=catalogue.videos,
            reviewed_videos=catalogue.videos,
            source_results=[],
            slug="must-not-replace-existing",
            existing=draft,
        )
        self.assertEqual(edited.status, "changes_pending")
        self.assertEqual(edited.id, original_id)
        self.assertEqual(edited.slug, "test-business-a")
        self.assertEqual(edited.published_url, draft.published_url)
        self.assertEqual(edited.publication_revision, "revision-one")
        self.assertEqual(edited.title, "COMPLETELY DIFFERENT BUSINESS TITLE")
        self.assertEqual(edited.business_config.shop_url, "https://example.com/shop-b")
        self.assertEqual(edited.ticker_text, "Manual story B")

    def test_configured_shop_url_is_the_only_shop_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "site"
            project = business_project(shop_url="https://example.com/shop")
            build_project_site(project, destination)
            payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
            script = (destination / "assets" / "video-machine.js").read_text(encoding="utf-8")
            page = (destination / "index.html").read_text(encoding="utf-8")

            self.assertEqual(payload["customerConfig"]["shopURL"], "https://example.com/shop")
            self.assertTrue(payload["customerConfig"]["shopEnabled"])
            self.assertNotEqual(payload["customerConfig"]["shopURL"], payload["customerConfig"]["subscribeURL"])
            self.assertNotEqual(payload["customerConfig"]["shopURL"], project.additional_urls[0])
            self.assertIn("shopDestination = String(config.customerConfig?.shopURL || '').trim()", script)
            self.assertIn("window.open(shopDestination, '_blank', 'noopener,noreferrer')", script)
            self.assertNotIn("sub_confirmation=1", script)
            self.assertIn('data-action="shop"', page)
            self.assertNotIn('data-action="subscribe"', page)
            self.assertNotIn("music_config", payload)

    def test_no_shop_is_disabled_and_never_falls_back_to_youtube(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "site"
            project = business_project(shop_url=None)
            build_project_site(project, destination)
            payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
            page = (destination / "index.html").read_text(encoding="utf-8")
            script = (destination / "assets" / "video-machine.js").read_text(encoding="utf-8")

            self.assertIsNone(payload["customerConfig"]["shopURL"])
            self.assertFalse(payload["customerConfig"]["shopEnabled"])
            self.assertIn('aria-label="Shop unavailable" disabled', page)
            self.assertIn("shopButton.disabled = !shopDestination", script)
            self.assertNotIn("current.channelId", script)

    def test_shop_update_and_removal_never_leave_a_stale_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "site"
            project = business_project(shop_url="https://example.com/shop-a")
            build_project_site(project, destination)
            self.assertIn("https://example.com/shop-a", (destination / "machine.json").read_text(encoding="utf-8"))

            project.business_config = BusinessConfig(shop_url="https://example.com/shop-b")
            build_project_site(project, destination)
            updated = (destination / "machine.json").read_text(encoding="utf-8")
            self.assertIn("https://example.com/shop-b", updated)
            self.assertNotIn("https://example.com/shop-a", updated)

            project.business_config = BusinessConfig()
            build_project_site(project, destination)
            removed = (destination / "machine.json").read_text(encoding="utf-8")
            self.assertNotIn("https://example.com/shop-a", removed)
            self.assertNotIn("https://example.com/shop-b", removed)
            self.assertIsNone(json.loads(removed)["customerConfig"]["shopURL"])

    def test_supplementary_source_success_is_text_only_and_bounded(self):
        body = b"""<!doctype html><html><head><title>Example Business</title>
        <meta name="description" content="Trusted business summary"></head>
        <body><script>doNotCapture()</script><h1>About us</h1><p>Public business context.</p></body></html>"""
        response = FakeResponse(200, body, {"content-type": "text/html", "content-length": str(len(body))})
        session = FakeSession([response])
        result = retrieve_supplementary_source("https://example.com/about", session=session, resolver=public_resolver)

        self.assertTrue(result.succeeded)
        self.assertEqual(result.title, "Example Business")
        self.assertEqual(result.summary, "Trusted business summary")
        self.assertIn("About us Public business context.", result.text)
        self.assertNotIn("doNotCapture", result.text)
        self.assertLessEqual(len(result.text), MAX_EXTRACTED_TEXT)
        self.assertFalse(session.calls[0][1]["allow_redirects"])
        self.assertTrue(session.calls[0][1]["stream"])
        self.assertEqual(session.calls[0][1]["timeout"], (5, 10))
        self.assertTrue(response.closed)

    def test_supplementary_source_failures_are_recoverable_and_private_hosts_are_blocked(self):
        success_body = b"<html><body><p>Second source remains usable.</p></body></html>"
        session = FakeSession([
            requests.ConnectionError("unreachable"),
            FakeResponse(200, success_body, {"content-type": "text/html"}),
        ])
        results = retrieve_supplementary_sources(
            ["https://unreachable.example", "https://working.example"],
            session=session,
            resolver=public_resolver,
        )
        self.assertEqual([result.status for result in results], ["unavailable", "retrieved"])
        self.assertIn("unreachable", results[0].error)
        self.assertIn("Second source remains usable", results[1].text)

        private_session = FakeSession([])
        private = retrieve_supplementary_sources(
            ["http://localhost/private"],
            session=private_session,
            resolver=public_resolver,
        )
        self.assertEqual(private[0].status, "unavailable")
        self.assertEqual(private_session.calls, [])

        oversized = FakeResponse(200, b"x", {"content-type": "text/plain", "content-length": str(MAX_RESPONSE_BYTES + 1)})
        oversized_result = retrieve_supplementary_sources(
            ["https://large.example"], session=FakeSession([oversized]), resolver=public_resolver,
        )
        self.assertEqual(oversized_result[0].status, "unavailable")
        self.assertIn("safety limit", oversized_result[0].error)

    def test_supplementary_context_stays_separate_from_story_videos_shop_and_deployed_actions(self):
        project = business_project(shop_url="https://example.com/shop")
        result = SupplementarySourceResult(
            url="https://example.com/about",
            final_url="https://example.com/about",
            status="retrieved",
            title="About",
            text="Supplementary material",
        )
        project.extra_fields["additional_source_context"] = [result.to_dict()]
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.ticker_text, "The manually supplied Business story remains authoritative.")
        self.assertEqual(restored.manual_video_urls, ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
        self.assertEqual(restored.additional_urls, ["https://example.com/about"])
        self.assertEqual(restored.business_config.shop_url, "https://example.com/shop")
        self.assertEqual(restored.extra_fields["additional_source_context"][0]["text"], "Supplementary material")

    def test_business_identity_survives_publish_edit_unpublish_and_republish_locally(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            project = business_project(shop_url="https://example.com/shop-a", slug=store.allocate_slug("TEST BUSINESS A"))
            original_id = project.id
            UUID(original_id)
            store.save_project(project)
            build_project_site(project, store.project_dir(project.slug) / "site")
            workspace = Path(temporary) / "isolated-publisher-workspace"
            revisions = iter(["revision-one", "revision-two", "revision-three", "revision-four"])

            def fake_git(command, **_kwargs):
                if "diff" in command:
                    return "public/crispy-bits/test-business-a"
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

                project.title = "COMPLETELY DIFFERENT BUSINESS TITLE"
                project.ticker_text = "Edited manual story."
                project.additional_urls = ["https://example.com/new-context"]
                project.business_config = BusinessConfig(shop_url="https://example.com/shop-b")
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
                self.assertFalse((workspace / "public" / "crispy-bits" / project.slug).exists())

                build_project_site(project, store.project_dir(project.slug) / "site")
                third_url, third_revision = publisher.publish(project)
                project.status = "published"
                project.published_url = third_url
                project.publication_revision = third_revision
                store.save_project(project)

            restored = store.load_project(project.slug)
            self.assertEqual(restored.id, original_id)
            self.assertEqual(restored.slug, "test-business-a")
            self.assertEqual(first_url, second_url)
            self.assertEqual(first_url, third_url)
            self.assertEqual(restored.published_url, first_url)
            self.assertEqual(restored.title, "COMPLETELY DIFFERENT BUSINESS TITLE")
            self.assertEqual(restored.business_config.shop_url, "https://example.com/shop-b")
            self.assertEqual(store.allocate_slug("TEST BUSINESS A"), "test-business-a-2")

    def test_local_preview_serves_generated_business_shop_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "site"
            build_project_site(business_project(shop_url="https://example.com/shop"), destination)
            preview = PreviewServer()
            try:
                url = preview.start(destination)
                page = requests.get(url, timeout=5)
                config = requests.get(f"{url}machine.json", timeout=5).json()
            finally:
                preview.stop()
            self.assertEqual(page.status_code, 200)
            self.assertIn("SHOP NOW", page.text)
            self.assertEqual(config["customerConfig"]["shopURL"], "https://example.com/shop")

    def test_delivery_request_is_intercepted_and_requires_verified_publication_fields(self):
        project = business_project(shop_url="https://example.com/shop")
        with self.assertRaises(DeliveryError):
            request_delivery(project, "owner@example.com")

        project.published_url = "https://raggedya.github.io/aggits-video-jukebox/crispy-bits/test-business-a/"
        project.publication_revision = "revision-one"
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"ok": True}
        with patch("aggits_video_factory.delivery.requests.post", return_value=response) as post:
            request_delivery(project, " Owner@Example.com ")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["email"], "owner@example.com")
        self.assertEqual(payload["publicUrl"], project.published_url)
        self.assertEqual(payload["qrUrl"], f"{project.published_url.rstrip('/')}/qr-card.png")
        self.assertEqual(payload["revision"], "revision-one")

    def test_publication_readiness_requires_machine_and_qr(self):
        with tempfile.TemporaryDirectory() as temporary:
            publisher = Publisher(ProjectStore(Path(temporary)))
            machine = Mock(ok=True)
            machine.json.return_value = {"slug": "test-business-a"}
            qr = Mock(ok=True, content=b"\x89PNG\r\n\x1a\ncontent")
            with patch("aggits_video_factory.publisher.requests.get", side_effect=[machine, qr]) as get:
                publisher._wait_for_publication("test-business-a", "revision-one", timeout=1)
            self.assertEqual(get.call_count, 2)
            self.assertIn("machine.json", get.call_args_list[0].args[0])
            self.assertIn("qr-card.png", get.call_args_list[1].args[0])

    def test_music_generation_requires_a_configured_primary_cta(self):
        project = Project(
            slug="music-only",
            title="Music Only",
            ticker_text="Music story",
            channel_url="https://youtube.com/@music",
            channel_id="UCmusic",
            channel_title="Music",
            channel_thumbnail="",
            project_type=ProjectType.MUSIC,
            music_config=MusicConfig(),
            videos=[sample_video()],
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "requires a configured primary CTA"):
                build_project_site(project, Path(temporary) / "site")


if __name__ == "__main__":
    unittest.main()
