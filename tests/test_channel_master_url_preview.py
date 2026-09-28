from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from aggits_video_factory.business_workflow import assemble_reviewed_project
from aggits_video_factory.channel_master_preview import (
    MAX_URL_PREVIEW_IMAGE_BYTES,
    inspect_url_preview_image,
    materialize_url_preview_image,
)
from aggits_video_factory.desktop_forms import ProjectFormValues, project_to_form_values, validate_project_form
from aggits_video_factory.models import ChannelMasterConfig, PrimaryCta, PrimaryCtaType, Project, ProjectType, Video
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.youtube_api import ChannelCatalogue


def _video() -> Video:
    return Video(
        video_id="preview0001",
        title="Preview fixture",
        display_title="Preview Fixture",
        url="https://www.youtube.com/watch?v=preview0001",
        embed_url="https://www.youtube.com/embed/preview0001",
        thumbnail_url="https://i.ytimg.com/vi/preview0001/hqdefault.jpg",
        published_at="2026-09-01T00:00:00Z",
        duration_seconds=90,
        channel_title="Fixture Channel",
    )


def _project(slug: str = "test-channel-master", reference: str = "") -> Project:
    return Project(
        slug=slug,
        title="TEST CHANNEL MASTER",
        ticker_text="CHANNEL MASTER TEST TICKER",
        channel_url="https://www.youtube.com/channel/UCpreview",
        channel_id="UCpreview",
        channel_title="Fixture Channel",
        channel_thumbnail="",
        project_type=ProjectType.CHANNEL_MASTER,
        channel_master_config=ChannelMasterConfig(
            palette="MIDNIGHT",
            primary_cta=PrimaryCta(PrimaryCtaType.VISIT_WEBSITE, "https://example.com"),
            contact_url="https://example.com/contact",
            url_preview_image=reference,
        ),
        videos=[_video()],
        published_url=f"https://crispy-bits.pages.dev/jukeboxes/{slug}/",
    )


def _make_image(path: Path, image_format: str, colour: tuple[int, int, int], size=(1200, 630)) -> None:
    Image.new("RGB", size, colour).save(path, format=image_format)


class ChannelMasterUrlPreviewValidationTests(unittest.TestCase):
    def test_png_jpg_jpeg_and_webp_are_real_images_and_keep_actual_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (("preview.png", "PNG"), ("preview.jpg", "JPEG"), ("preview.jpeg", "JPEG"), ("preview.webp", "WEBP"))
            for filename, image_format in cases:
                with self.subTest(filename=filename):
                    source = root / filename
                    _make_image(source, image_format, (20, 40, 60), size=(900, 500))
                    info = inspect_url_preview_image(source)
                    self.assertEqual((info.width, info.height), (900, 500))
                    self.assertLessEqual(info.file_size, MAX_URL_PREVIEW_IMAGE_BYTES)
                    self.assertIn(info.media_type, {"image/png", "image/jpeg", "image/webp"})

    def test_unsupported_fake_unreadable_and_oversize_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "preview.txt").write_text("not an image", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PNG, JPG, JPEG OR WEBP"):
                inspect_url_preview_image(root / "preview.txt")
            (root / "fake.png").write_text("not an image", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "COULD NOT BE READ"):
                inspect_url_preview_image(root / "fake.png")
            oversized = root / "oversized.png"
            with oversized.open("wb") as stream:
                stream.seek(MAX_URL_PREVIEW_IMAGE_BYTES)
                stream.write(b"x")
            with self.assertRaisesRegex(ValueError, "MAXIMUM FILE SIZE"):
                inspect_url_preview_image(oversized)

    def test_import_is_project_owned_hashed_and_survives_original_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "operator-selected.png"
            project_dir = root / "project"
            _make_image(source, "PNG", (10, 20, 30))
            reference = materialize_url_preview_image(str(source), project_dir)
            self.assertRegex(reference, r"^assets/channel-master-url-preview-[0-9a-f]{16}\.png$")
            project_copy = project_dir / reference
            expected = hashlib.sha256(project_copy.read_bytes()).hexdigest()
            source.unlink()
            self.assertTrue(project_copy.is_file())
            self.assertEqual(hashlib.sha256(project_copy.read_bytes()).hexdigest(), expected)

    def test_replacement_changes_asset_name_and_remove_clears_only_preview_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir = root / "project"
            first = root / "first.png"
            second = root / "second.png"
            _make_image(first, "PNG", (100, 0, 0))
            _make_image(second, "PNG", (0, 100, 0))
            first_reference = materialize_url_preview_image(str(first), project_dir)
            unrelated = project_dir / "assets" / "keep.txt"
            unrelated.write_text("keep", encoding="utf-8")
            second_reference = materialize_url_preview_image(str(second), project_dir)
            self.assertNotEqual(first_reference, second_reference)
            self.assertFalse((project_dir / first_reference).exists())
            self.assertTrue((project_dir / second_reference).exists())
            self.assertEqual(materialize_url_preview_image("", project_dir), "")
            self.assertFalse((project_dir / second_reference).exists())
            self.assertTrue(unrelated.exists())

    def test_project_relative_reference_cannot_escape_project_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.png"
            _make_image(outside, "PNG", (1, 2, 3))
            with self.assertRaisesRegex(ValueError, "PROJECT REFERENCE IS INVALID"):
                materialize_url_preview_image("assets/channel-master-url-preview-x/../../outside.png", root / "project")


class ChannelMasterUrlPreviewPersistenceTests(unittest.TestCase):
    def test_config_round_trip_and_old_project_compatibility(self):
        current = ChannelMasterConfig(url_preview_image="assets/channel-master-url-preview-a.png")
        self.assertEqual(ChannelMasterConfig.from_dict(current.to_dict()).url_preview_image, current.url_preview_image)
        self.assertEqual(ChannelMasterConfig.from_dict({"palette": "MIDNIGHT"}).url_preview_image, "")

    def test_projectstore_save_close_reopen_and_form_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            project = _project(reference="assets/channel-master-url-preview-1234567890abcdef.png")
            store.save_project(project)
            restored = ProjectStore(Path(temporary)).load_project(project.slug)
            self.assertEqual(restored.channel_master_config.url_preview_image, project.channel_master_config.url_preview_image)
            self.assertEqual(project_to_form_values(restored).url_preview_image, project.channel_master_config.url_preview_image)

    def test_white_label_never_receives_channel_master_preview_field(self):
        values = ProjectFormValues(
            title="WHITE LABEL",
            manual_video_urls=["https://www.youtube.com/watch?v=preview0001"],
            cta_label="Visit Website",
            destination_url="https://example.com",
            custom_logo_path="missing.png",
            url_preview_image="C:/operator/private.png",
        )
        # White Label proceeds to its own required logo validation without ever
        # attempting to inspect the Channel Master-only preview selection.
        with self.assertRaisesRegex(Exception, "logo|LOGO|read|READ"):
            validate_project_form(values, ProjectType.WHITE_LABEL)


class ChannelMasterUrlPreviewPublishingTests(unittest.TestCase):
    def _build_with_image(self, root: Path, slug: str, colour: tuple[int, int, int], size=(1200, 630)):
        source = root / f"{slug}-source.png"
        project_dir = root / slug
        _make_image(source, "PNG", colour, size=size)
        reference = materialize_url_preview_image(str(source), project_dir)
        project = _project(slug, reference)
        html_path = build_project_site(project, project_dir / "site")
        return project, project_dir, html_path, reference

    def test_open_graph_twitter_metadata_uses_public_https_custom_image_and_actual_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, project_dir, html_path, reference = self._build_with_image(root, "metadata-fixture", (1, 2, 3), (1000, 525))
            page = html_path.read_text(encoding="utf-8")
            filename = Path(reference).name
            public_url = f"{project.published_url.rstrip('/')}/{filename}"
            self.assertIn('<meta property="og:type" content="website">', page)
            self.assertIn('<meta property="og:title" content="TEST CHANNEL MASTER">', page)
            self.assertIn(f'<meta property="og:url" content="{project.published_url}">', page)
            self.assertIn(f'<meta property="og:image" content="{public_url}">', page)
            self.assertIn('<meta property="og:image:width" content="1000">', page)
            self.assertIn('<meta property="og:image:height" content="525">', page)
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', page)
            self.assertIn('<meta name="twitter:title" content="TEST CHANNEL MASTER">', page)
            self.assertIn(f'<meta name="twitter:image" content="{public_url}">', page)
            self.assertTrue((project_dir / "site" / filename).is_file())
            self.assertNotIn(str(root), page)
            self.assertNotIn("file://", page)

    def test_two_projects_cannot_cross_reference_preview_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_a, _, html_a, reference_a = self._build_with_image(root, "project-a", (255, 0, 0))
            project_b, _, html_b, reference_b = self._build_with_image(root, "project-b", (0, 0, 255))
            self.assertNotEqual(reference_a, reference_b)
            page_a = html_a.read_text(encoding="utf-8")
            page_b = html_b.read_text(encoding="utf-8")
            self.assertIn(Path(reference_a).name, page_a)
            self.assertNotIn(Path(reference_b).name, page_a)
            self.assertIn(Path(reference_b).name, page_b)
            self.assertNotIn(Path(reference_a).name, page_b)
            self.assertNotEqual(project_a.id, project_b.id)

    def test_replace_preserves_identity_page_url_and_qr_but_changes_image_url(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, project_dir, html_path, first_reference = self._build_with_image(root, "stable-machine", (255, 0, 0))
            first_qr = hashlib.sha256((project_dir / "site" / "qr-card.png").read_bytes()).hexdigest()
            identity = (project.id, project.slug, project.published_url)
            replacement = root / "replacement.png"
            _make_image(replacement, "PNG", (0, 255, 0))
            second_reference = materialize_url_preview_image(str(replacement), project_dir)
            project.channel_master_config.url_preview_image = second_reference
            build_project_site(project, project_dir / "site")
            second_qr = hashlib.sha256((project_dir / "site" / "qr-card.png").read_bytes()).hexdigest()
            page = html_path.read_text(encoding="utf-8")
            self.assertEqual((project.id, project.slug, project.published_url), identity)
            self.assertEqual(first_qr, second_qr)
            self.assertNotEqual(first_reference, second_reference)
            self.assertIn(Path(second_reference).name, page)
            self.assertNotIn(Path(first_reference).name, page)

    def test_removal_restores_default_preview_without_stale_custom_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, project_dir, _, reference = self._build_with_image(root, "remove-fixture", (1, 1, 1))
            old_filename = Path(reference).name
            project.channel_master_config.url_preview_image = materialize_url_preview_image("", project_dir)
            html_path = build_project_site(project, project_dir / "site")
            page = html_path.read_text(encoding="utf-8")
            self.assertNotIn(old_filename, page)
            self.assertFalse((project_dir / "site" / old_filename).exists())
            self.assertIn("social-card-", page)

    def test_published_edit_becomes_changes_pending_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "new.png"
            _make_image(source, "PNG", (4, 5, 6))
            existing = _project("published-edit")
            existing.status = "published"
            identity = (existing.id, existing.slug, existing.published_url)
            values = validate_project_form(ProjectFormValues(
                title=existing.title,
                manual_video_urls=[_video().url],
                story_text=existing.ticker_text,
                cta_label="Visit Website",
                destination_url="https://example.com",
                contact_url="https://example.com/contact",
                url_preview_image=str(source),
            ), ProjectType.CHANNEL_MASTER)
            revised = assemble_reviewed_project(
                project_type=ProjectType.CHANNEL_MASTER,
                values=values,
                catalogue=ChannelCatalogue(
                    channel_id=existing.channel_id,
                    channel_title=existing.channel_title,
                    channel_thumbnail="",
                    channel_url=existing.channel_url,
                    videos=[_video()],
                ),
                selected_videos=[_video()],
                reviewed_videos=[_video()],
                source_results=[],
                slug=existing.slug,
                existing=existing,
            )
            self.assertEqual(revised.status, "changes_pending")
            self.assertEqual((revised.id, revised.slug, revised.published_url), identity)

    def test_project_json_contains_no_operator_source_path_after_materialisation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "private" / "operator.png"
            source.parent.mkdir()
            _make_image(source, "PNG", (7, 8, 9))
            project_dir = root / "project"
            reference = materialize_url_preview_image(str(source), project_dir)
            project = _project(reference=reference)
            store = ProjectStore(root / "store")
            store.save_project(project)
            serialised = json.dumps(project.to_dict())
            self.assertNotIn(str(source.parent), serialised)
            self.assertEqual(project.channel_master_config.url_preview_image, reference)


class ChannelMasterUrlPreviewDesktopContractTests(unittest.TestCase):
    def test_desktop_contains_single_simple_channel_master_only_control(self):
        source = (Path(__file__).parents[1] / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")
        self.assertIn('text="URL Preview Image"', source)
        self.assertIn('text="SELECT IMAGE"', source)
        self.assertIn('text="REMOVE"', source)
        self.assertIn('text="RECOMMENDED: 1200 × 630 PX"', source)
        self.assertIn("if self.project_type is ProjectType.CHANNEL_MASTER:", source)
        self.assertNotIn('text="Facebook image"', source)
        self.assertNotIn('text="Twitter image"', source)


if __name__ == "__main__":
    unittest.main()
