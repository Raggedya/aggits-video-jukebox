from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

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
from aggits_video_factory.white_label import materialize_white_label_logo


ROOT = Path(__file__).parents[1]
CSS = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
DESKTOP = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")


def make_logo(path: Path, size: tuple[int, int] = (720, 180), colour=(200, 30, 80, 180)) -> Path:
    Image.new("RGBA", size, colour).save(path, format="PNG")
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
        self.assertEqual(project_to_form_values(restored).custom_logo_path, managed.logo_asset_path)

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
        self.assertIn("max-width:100%", logo_rule)
        self.assertIn("max-height:100%", logo_rule)

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
