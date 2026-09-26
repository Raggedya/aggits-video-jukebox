from __future__ import annotations

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from aggits_video_factory.config import ticker_limit_for_project_type, video_limit_for_project_type
from aggits_video_factory.delivery import request_delivery
from aggits_video_factory.desktop_forms import (
    FormValidationError,
    ProjectFormValues,
    project_is_visible_in_tab,
    project_to_form_values,
    validate_project_form,
)
from aggits_video_factory.models import (
    ChannelMasterConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    Video,
    WhiteLabelConfig,
)
from aggits_video_factory.publisher import _validate_project_type
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.white_label import (
    materialize_white_label_logo,
    prepare_white_label_logo,
    validate_logo_adjustments,
)
from desktop.video_jukebox_factory import ProjectForm


ROOT = Path(__file__).parents[1]
CSS = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
DESKTOP = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")


def make_logo(path: Path, size: tuple[int, int] = (720, 180), colour=(200, 30, 80, 180)) -> Path:
    Image.new("RGBA", size, colour).save(path, format="PNG")
    return path


def make_opaque_logo(path: Path, background: str, *, size: tuple[int, int] = (600, 240)) -> Path:
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((150, 75, 450, 165), radius=14, fill="#c79638")
    draw.rectangle((260, 95, 340, 145), fill="#000000")
    image.save(path, format="JPEG" if path.suffix.lower() in {".jpg", ".jpeg"} else "PNG", quality=95)
    return path


def fixture_video() -> Video:
    return Video(
        video_id="whitelabel1",
        title="White Label fixture video",
        display_title="White Label fixture video",
        url="https://www.youtube.com/watch?v=whitelabel1",
        embed_url="https://www.youtube.com/embed/whitelabel1",
        thumbnail_url="https://i.ytimg.com/vi/whitelabel1/hqdefault.jpg",
        published_at="2026-09-01T00:00:00Z",
        duration_seconds=120,
        channel_title="Golden Robot Records",
    )


def white_label_project(logo: Path, *, slug: str = "golden-robot-records") -> Project:
    with Image.open(logo) as image:
        width, height = image.size
    return Project(
        slug=slug,
        title="GOLDEN ROBOT RECORDS",
        ticker_text="NEW MUSIC • FRESH DISCOVERIES",
        channel_url="https://www.youtube.com/channel/UCgoldenrobot",
        channel_id="UCgoldenrobot",
        channel_title="Golden Robot Records",
        channel_thumbnail="https://example.com/youtube-channel-thumbnail.jpg",
        project_type=ProjectType.WHITE_LABEL,
        channel_master_config=ChannelMasterConfig(
            palette="MIDNIGHT",
            primary_cta=PrimaryCta(PrimaryCtaType.VISIT_WEBSITE, "https://example.com/golden-robot"),
            contact_url="https://example.com/contact",
        ),
        white_label_config=WhiteLabelConfig(
            logo_asset_path=str(logo),
            original_filename=logo.name,
            media_type="image/png",
            width=width,
            height=height,
        ),
        videos=[fixture_video()],
    )


class WhiteLabelWorkflowTests(unittest.TestCase):
    def test_type_inherits_channel_master_limits_and_ctas(self):
        self.assertEqual(ProjectType.WHITE_LABEL.value, "white_label")
        self.assertEqual(video_limit_for_project_type(ProjectType.WHITE_LABEL), 50)
        self.assertEqual(ticker_limit_for_project_type(ProjectType.WHITE_LABEL), 1500)
        with tempfile.TemporaryDirectory() as temporary:
            logo = make_logo(Path(temporary) / "golden-robot.png")
            validated = validate_project_form(ProjectFormValues(
                title="Golden Robot Records",
                channel_url="https://www.youtube.com/channel/UCgoldenrobot",
                story_text="A label ticker",
                cta_label="Visit Website",
                destination_url="https://example.com",
                custom_logo_path=str(logo),
            ), ProjectType.WHITE_LABEL)
        self.assertIsNotNone(validated.channel_master_config)
        self.assertEqual(validated.white_label_config.original_filename, "golden-robot.png")

    def test_logo_is_required_and_bad_images_are_rejected(self):
        base = ProjectFormValues(
            title="Golden Robot Records",
            channel_url="https://www.youtube.com/channel/UCgoldenrobot",
            cta_label="Visit Website",
            destination_url="https://example.com",
        )
        with self.assertRaises(FormValidationError) as missing:
            validate_project_form(base, ProjectType.WHITE_LABEL)
        self.assertEqual(missing.exception.field, "custom_logo")
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "not-an-image.png"
            invalid.write_text("not an image", encoding="utf-8")
            base.custom_logo_path = str(invalid)
            with self.assertRaises(FormValidationError) as unreadable:
                validate_project_form(base, ProjectType.WHITE_LABEL)
        self.assertEqual(unreadable.exception.field, "custom_logo")

    def test_project_round_trip_restores_project_specific_logo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_logo(root / "source.png")
            store = ProjectStore(root / "store")
            managed = materialize_white_label_logo(str(source), store.project_dir("golden-robot-records"))
            project = white_label_project(Path(managed.logo_asset_path))
            project.white_label_config = managed
            store.save_project(project)
            restored = ProjectStore(root / "store").load_project(project.slug)
        self.assertEqual(restored.project_type, ProjectType.WHITE_LABEL)
        self.assertEqual(restored.white_label_config.to_dict(), managed.to_dict())
        values = project_to_form_values(restored)
        self.assertEqual(values.custom_logo_path, managed.original_logo_path)
        self.assertEqual(values.logo_background_removal, "auto")
        self.assertEqual(values.logo_scale_percent, 100)
        self.assertEqual(values.logo_vertical_position, 0)

    def test_two_projects_package_distinct_logo_bytes_without_collisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_source = make_logo(root / "first.png", colour=(220, 20, 40, 180))
            second_source = make_logo(root / "second.png", colour=(20, 80, 220, 180))
            first_config = materialize_white_label_logo(str(first_source), root / "project-a")
            second_config = materialize_white_label_logo(str(second_source), root / "project-b")
            first = white_label_project(Path(first_config.logo_asset_path), slug="project-a")
            second = white_label_project(Path(second_config.logo_asset_path), slug="project-b")
            first.white_label_config = first_config
            second.white_label_config = second_config
            first_site = root / "project-a" / "site"
            second_site = root / "project-b" / "site"
            build_project_site(first, first_site)
            build_project_site(second, second_site)
            first_public = first_site / "assets" / "white-label" / "customer-logo.png"
            second_public = second_site / "assets" / "white-label" / "customer-logo.png"
            self.assertNotEqual(first_public.read_bytes(), second_public.read_bytes())
            self.assertEqual(first_public.read_bytes(), Path(first_config.logo_asset_path).read_bytes())

    def test_public_machine_uses_contained_customer_logo_and_discreet_attribution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logo = make_logo(root / "golden-robot.png", (1200, 220))
            project = white_label_project(logo)
            destination = root / "site"
            build_project_site(project, destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
            payload_text = (destination / "machine.json").read_text(encoding="utf-8")
            payload = json.loads(payload_text)
        self.assertIn('data-project-type="white_label"', page)
        self.assertIn('class="white-label-customer-logo"', page)
        self.assertIn('src="assets/white-label/customer-logo.png"', page)
        self.assertIn('alt="GOLDEN ROBOT RECORDS logo"', page)
        self.assertNotIn("channel-master-maker-mark", page)
        self.assertIn("POWERED BY", page)
        self.assertIn("CRISPY BITS", page)
        self.assertNotIn(str(logo), page)
        self.assertNotIn(str(logo), payload_text)
        self.assertEqual(payload["projectType"], "white_label")
        self.assertEqual(payload["whiteLabelConfig"]["logoAssetUrl"], "assets/white-label/customer-logo.png")
        self.assertIn("channelMasterConfig", payload)
        logo_rule = CSS.split('.music-machine[data-project-type="white_label"] .white-label-customer-logo img{', 1)[1].split("}", 1)[0]
        self.assertIn("object-fit:contain", logo_rule)
        self.assertIn("object-position:center", logo_rule)
        self.assertIn("max-width:var(--white-label-logo-width,70%)", logo_rule)
        self.assertIn("max-height:var(--white-label-logo-height,72%)", logo_rule)
        self.assertIn("--white-label-logo-width:70.0%", page)
        self.assertEqual(payload["whiteLabelConfig"]["scalePercent"], 100)
        self.assertEqual(payload["whiteLabelConfig"]["verticalPosition"], 0)

    def test_auto_removes_black_and_white_edge_backgrounds_but_preserves_internal_black(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, background in (("black.png", "#000000"), ("white.png", "#ffffff")):
                source = make_opaque_logo(root / name, background)
                prepared = prepare_white_label_logo(source, "auto")
                self.assertEqual(prepared.status, "removed")
                self.assertLess(prepared.image.getpixel((0, 0))[3], 10)
                center = prepared.image.getpixel((prepared.image.width // 2, prepared.image.height // 2))
                self.assertEqual(center[:3], (0, 0, 0))
                self.assertEqual(center[3], 255)

            misleading = Image.new("RGBA", (600, 240), (0, 0, 0, 255))
            misleading.putpixel((0, 0), (0, 0, 0, 254))
            ImageDraw.Draw(misleading).rectangle((150, 75, 450, 165), fill=(210, 160, 60, 255))
            misleading_path = root / "opaque-png-with-token-alpha.png"
            misleading.save(misleading_path)
            prepared = prepare_white_label_logo(misleading_path)
            self.assertEqual(prepared.status, "removed")
            self.assertTrue(prepared.has_transparency)

    def test_transparent_logo_is_trimmed_and_extreme_shapes_preserve_aspect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, canvas, artwork in (
                ("wide.png", (1200, 400), (100, 150, 1100, 250)),
                ("tall.png", (400, 1200), (150, 100, 250, 1100)),
                ("square.png", (900, 900), (150, 150, 750, 750)),
            ):
                image = Image.new("RGBA", canvas, (0, 0, 0, 0))
                ImageDraw.Draw(image).rectangle(artwork, fill=(210, 160, 60, 255))
                source = root / name
                image.save(source)
                prepared = prepare_white_label_logo(source)
                self.assertEqual(prepared.status, "existing_transparency")
                self.assertLess(prepared.image.width, canvas[0])
                self.assertLess(prepared.image.height, canvas[1])
                left, top, right, bottom = prepared.visible_bbox
                expected_ratio = (artwork[2] - artwork[0] + 1) / (artwork[3] - artwork[1] + 1)
                actual_ratio = (right - left) / (bottom - top)
                self.assertAlmostEqual(actual_ratio, expected_ratio, delta=0.03)

    def test_jpeg_is_processed_and_complex_photographic_background_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jpeg = make_opaque_logo(root / "logo.jpg", "#ffffff")
            prepared_jpeg = prepare_white_label_logo(jpeg)
            self.assertEqual(prepared_jpeg.status, "removed")
            self.assertTrue(prepared_jpeg.has_transparency)

            photograph = Image.new("RGB", (420, 240))
            pixels = photograph.load()
            for y in range(240):
                for x in range(420):
                    pixels[x, y] = ((x * 7 + y * 3) % 256, (x * 2 + y * 11) % 256, (x * 13 + y) % 256)
            photo_path = root / "photograph.jpg"
            photograph.save(photo_path, quality=92)
            prepared_photo = prepare_white_label_logo(photo_path)
            self.assertEqual(prepared_photo.status, "not_confident")
            self.assertFalse(prepared_photo.has_transparency)

    def test_off_preserves_background_and_materialization_keeps_original_and_processed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_opaque_logo(root / "golden-robot.png", "#000000")
            off = prepare_white_label_logo(source, "off")
            self.assertEqual(off.status, "off")
            self.assertFalse(off.has_transparency)
            config = materialize_white_label_logo(
                str(source), root / "project", background_removal="auto", scale_percent=115, vertical_position=-2,
            )
            self.assertTrue(Path(config.original_logo_path).is_file())
            self.assertEqual(Path(config.original_logo_path).read_bytes(), source.read_bytes())
            self.assertTrue(Path(config.logo_asset_path).is_file())
            self.assertEqual(Path(config.logo_asset_path).suffix, ".png")
            self.assertEqual(config.background_removal_status, "removed")
            self.assertEqual(config.scale_percent, 115)
            self.assertEqual(config.vertical_position, -2)
            project = white_label_project(Path(config.logo_asset_path))
            project.white_label_config = config
            destination = root / "site"
            build_project_site(project, destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
            self.assertIn("--white-label-logo-width:80.5%", page)
            self.assertIn("--white-label-logo-height:82.8%", page)
            self.assertIn("--white-label-logo-y:-4px", page)

    def test_adjustment_bounds_and_legacy_defaults(self):
        self.assertEqual(validate_logo_adjustments("AUTO", 60, -2), ("auto", 60, -2))
        self.assertEqual(validate_logo_adjustments("off", 120, 2), ("off", 120, 2))
        for settings in (("maybe", 100, 0), ("auto", 59, 0), ("auto", 121, 0), ("auto", 100, 3)):
            with self.assertRaises(ValueError):
                validate_logo_adjustments(*settings)
        legacy = WhiteLabelConfig.from_dict({"logo_asset_path": "C:/project/customer-logo.png"})
        self.assertEqual(legacy.background_removal, "auto")
        self.assertEqual(legacy.scale_percent, 100)
        self.assertEqual(legacy.vertical_position, 0)

    def test_desktop_machine_header_preview_processes_logo_and_constrains_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = make_opaque_logo(Path(temporary) / "golden-robot.png", "#000000")
            root = tk.Tk()
            root.withdraw()
            try:
                form = ProjectForm(root, ProjectType.WHITE_LABEL, lambda: None, lambda: None)
                form.pack(fill="both", expand=True)
                form.custom_logo_var.set(str(source))
                form._update_white_label_logo_preview()
                for width, height in ((1320, 820), (1120, 720)):
                    root.geometry(f"{width}x{height}")
                    root.update_idletasks()
                    self.assertGreater(form.custom_logo_preview.winfo_reqwidth(), 0)
                    self.assertGreater(form.custom_logo_preview.winfo_reqheight(), 0)
                self.assertIn("Background removed", form.custom_logo_status.cget("text"))
                self.assertTrue(form.custom_logo_preview.find_all())
                for _ in range(20):
                    form._adjust_white_label_scale(5)
                    form._adjust_white_label_vertical(1)
                self.assertEqual(form.custom_logo_scale_var.get(), 120)
                self.assertEqual(form.custom_logo_vertical_var.get(), 2)
                form._adjust_white_label_vertical(0)
                self.assertEqual(form.custom_logo_vertical_var.get(), 0)
                form.custom_logo_background_var.set("OFF")
                form._update_white_label_logo_preview()
                self.assertIn("Background removal OFF", form.custom_logo_status.cget("text"))
            finally:
                root.destroy()

    def test_channel_master_engine_assets_remain_shared_and_mechanics_untouched(self):
        self.assertNotIn("white_label", (ROOT / "static" / "single-reel-engine.js").read_text(encoding="utf-8"))
        self.assertNotIn("white_label", (ROOT / "static" / "machine-mechanics-core.js").read_text(encoding="utf-8"))
        self.assertIn("startChannelMasterHeaderTicker();", SCRIPT)
        self.assertIn("['channel_master', 'white_label']", SCRIPT)

    def test_desktop_exposes_isolated_white_label_tab_and_branding_controls(self):
        self.assertIn("ProjectType.CHANNEL_MASTER, ProjectType.WHITE_LABEL", DESKTOP)
        for copy in (
            "CUSTOM BRANDING", "Custom Logo", "UPLOAD LOGO", "CHANGE LOGO", "REMOVE LOGO",
            "Transparent PNG recommended for best results.",
        ):
            self.assertIn(copy, DESKTOP)

    def test_publisher_delivery_and_library_visibility_accept_white_label(self):
        with tempfile.TemporaryDirectory() as temporary:
            logo = make_logo(Path(temporary) / "logo.png")
            project = white_label_project(logo)
            _validate_project_type(project)
            self.assertTrue(project_is_visible_in_tab(project, ProjectType.WHITE_LABEL))
            self.assertFalse(project_is_visible_in_tab(project, ProjectType.CHANNEL_MASTER))
            project.status = "published"
            project.published_url = "https://example.com/crispy-bits/golden-robot-records/"
            project.publication_revision = "a" * 40
            response = mock.Mock(status_code=200)
            response.json.return_value = {"ok": True, "id": "fixture", "sentAt": "2026-09-26T00:00:00Z"}
            with mock.patch("aggits_video_factory.delivery.requests.post", return_value=response) as post:
                request_delivery(project, "owner@example.com", secret="secret", timestamp=1_700_000_000, nonce="9" * 32)
        payload = json.loads(post.call_args.kwargs["data"].decode("utf-8"))
        self.assertEqual(payload["projectType"], "white_label")
        self.assertEqual(payload["productName"], "CRISPY BITS WHITE LABEL")


if __name__ == "__main__":
    unittest.main()
