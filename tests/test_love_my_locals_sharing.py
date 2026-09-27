from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qrcode
from PIL import Image
from qrcode.constants import ERROR_CORRECT_H

from aggits_video_factory.config import resource_path
from aggits_video_factory.love_my_locals import (
    LoveMyLocalsError,
    LoveMyLocalsFormValues,
    assemble_project,
    validate_form,
)
from aggits_video_factory.models import (
    BusinessConfig,
    LoveMyLocalsCandidate,
    LoveMyLocalsConfig,
    Project,
    ProjectType,
    Video,
)
from aggits_video_factory.site_builder import build_project_site, create_qr_card
from aggits_video_factory.social_preview import (
    LOVE_MY_LOCALS_LOGO_RESOURCE,
    LOVE_MY_LOCALS_TOUCH_ICON_BOUNDS,
    SOCIAL_PREVIEW_SIZE,
    create_love_my_locals_social_preview,
    social_preview_filename,
)
from aggits_video_factory.store import ProjectStore


def _video() -> Video:
    return Video(
        video_id="share000001",
        title="Box Hill local story",
        display_title="Box Hill local story",
        url="https://www.youtube.com/watch?v=share000001",
        embed_url="https://www.youtube.com/embed/share000001",
        thumbnail_url="https://i.ytimg.com/vi/share000001/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        channel_title="Box Hill Community",
        duration_seconds=120,
    )


def _project(*, locations: list[str] | None = None, public_title: str = "Box Hill") -> Project:
    names = locations or ["Box Hill", "Box Hill North", "Box Hill South"]
    video = _video()
    config = LoveMyLocalsConfig(
        locations=names,
        public_title=public_title,
        resolved_geography="Victoria, Australia",
        candidates=[LoveMyLocalsCandidate(
            video=video,
            matched_location=names[0],
            match_basis=["title"],
            relevance_score=3,
            local_texture_score=4,
            active=True,
        )],
    )
    return Project(
        slug="box-hill",
        title="legacy multi-location title",
        ticker_text="LOVE MY LOCALS • BOX HILL • BOX HILL NORTH • BOX HILL SOUTH •",
        channel_url="",
        channel_id="",
        channel_title="Love My Locals",
        channel_thumbnail="",
        project_type=ProjectType.LOVE_MY_LOCALS,
        love_my_locals_config=config,
        videos=[video],
        published_url="https://example.com/crispy-bits/box-hill/",
    )


class LoveMyLocalsSharingTests(unittest.TestCase):
    def test_public_title_defaults_to_location_one_and_accepts_multi_word_places(self):
        bairnsdale = validate_form(LoveMyLocalsFormValues(locations=["Bairnsdale"]))
        self.assertEqual(bairnsdale.public_title, "Bairnsdale")
        box_hill = validate_form(LoveMyLocalsFormValues(
            locations=["Box Hill", "Box Hill North", "Box Hill South"],
        ))
        self.assertEqual(box_hill.public_title, "Box Hill")
        edited = validate_form(LoveMyLocalsFormValues(
            locations=["Surfers Paradise", "Broadbeach"], public_title="Gold Coast Locals",
        ))
        self.assertEqual(edited.public_title, "Gold Coast Locals")
        with self.assertRaises(LoveMyLocalsError):
            validate_form(LoveMyLocalsFormValues(locations=[], public_title=""))
        desktop_source = (Path(__file__).parents[1] / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")
        self.assertIn('"PUBLIC TITLE"', desktop_source)
        self.assertIn("single location shown on the public QR and social preview", desktop_source)

    def test_bairnsdale_public_title_drives_qr_and_url_preview(self):
        project = _project(locations=["Bairnsdale"], public_title="Bairnsdale")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(project, destination)
            head = (destination / "index.html").read_text(encoding="utf-8").split("</head>", 1)[0]
            self.assertIn("Love My Locals — Bairnsdale", head)
            preview = destination / social_preview_filename("Bairnsdale", ProjectType.LOVE_MY_LOCALS)
            self.assertTrue(preview.is_file())
            self.assertTrue((destination / "qr-card.png").is_file())

    def test_all_three_search_locations_survive_while_public_identity_uses_one_title(self):
        project = _project()
        self.assertEqual(project.title, "legacy multi-location title")
        self.assertEqual(project.love_my_locals_config.locations, ["Box Hill", "Box Hill North", "Box Hill South"])
        self.assertEqual(project.love_my_locals_config.resolved_locations, [
            "Box Hill, Victoria, Australia",
            "Box Hill North, Victoria, Australia",
            "Box Hill South, Victoria, Australia",
        ])
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(project, destination)
            machine = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
            self.assertEqual(machine["loveMyLocalsConfig"]["locations"], project.love_my_locals_config.locations)
            self.assertEqual(machine["loveMyLocalsConfig"]["publicTitle"], "Box Hill")
            head = (destination / "index.html").read_text(encoding="utf-8").split("</head>", 1)[0]
            self.assertIn("Love My Locals — Box Hill", head)
            self.assertNotIn("Box Hill North", head)
            self.assertNotIn("Box Hill South", head)

    def test_public_title_survives_save_reload_and_old_projects_fall_back_to_location_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            project = _project(public_title="Greater Box Hill")
            store.save_project(project)
            restored = store.load_project(project.slug)
            self.assertEqual(restored.title, "legacy multi-location title")
            self.assertEqual(restored.love_my_locals_config.public_title, "Greater Box Hill")
            legacy = restored.love_my_locals_config.to_dict()
            legacy.pop("public_title")
            restored_config = LoveMyLocalsConfig.from_dict(legacy)
            self.assertEqual(restored_config.public_title, "Box Hill")

    def test_assemble_project_keeps_discovery_locations_and_uses_edited_public_title(self):
        base = _project().love_my_locals_config
        project = assemble_project(
            LoveMyLocalsFormValues(
                locations=["Box Hill", "Box Hill North", "Box Hill South"],
                public_title="Box Hill",
            ),
            base,
            "box-hill",
        )
        self.assertEqual(project.title, "BOX HILL • BOX HILL NORTH • BOX HILL SOUTH")
        self.assertEqual(project.love_my_locals_config.public_title, "Box Hill")
        self.assertEqual(project.love_my_locals_config.locations, ["Box Hill", "Box Hill North", "Box Hill South"])

    def test_love_my_locals_qr_uses_approved_logo_and_preserves_exact_qr_matrix(self):
        project = _project()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "qr-card.png"
            with patch("aggits_video_factory.site_builder.resource_path", wraps=resource_path) as resolver:
                create_qr_card(project, destination)
            resolved_resources = [call.args[0] for call in resolver.call_args_list]
            self.assertEqual(resolved_resources, [LOVE_MY_LOCALS_LOGO_RESOURCE])

            probe = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H, box_size=1, border=4)
            probe.add_data(project.published_url)
            probe.make(fit=True)
            module_count = 17 + (4 * int(probe.version or 1)) + 8
            box_size = max(8, min(16, 880 // module_count))
            expected_qr = qrcode.QRCode(
                version=probe.version, error_correction=ERROR_CORRECT_H, box_size=box_size, border=4,
            )
            expected_qr.add_data(project.published_url)
            expected_qr.make(fit=False)
            expected = expected_qr.make_image(fill_color="#000000", back_color="#FFFFFF").convert("RGB")
            with Image.open(destination) as image:
                image = image.convert("RGB")
                self.assertEqual(image.size, (1200, 1500))
                self.assertEqual(image.getpixel((0, 0)), (0, 0, 0))
                left = (image.width - expected.width) // 2
                actual = image.crop((left, 510, left + expected.width, 510 + expected.height))
                self.assertEqual(actual.tobytes(), expected.tobytes())
                self.assertGreater(sum(1 for pixel in image.crop((0, 0, 1200, 330)).getdata() if pixel[1] > 140 and pixel[2] > 140), 100)

    def test_social_preview_is_black_1200_by_630_and_uses_only_love_my_locals_branding(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "preview.png"
            with patch("aggits_video_factory.social_preview.resource_path", wraps=resource_path) as resolver:
                layout = create_love_my_locals_social_preview("Box Hill", destination)
            self.assertEqual([call.args[0] for call in resolver.call_args_list], [LOVE_MY_LOCALS_LOGO_RESOURCE])
            self.assertEqual(layout.lines, ("BOX HILL",))
            with Image.open(destination) as image:
                image = image.convert("RGB")
                self.assertEqual(image.size, SOCIAL_PREVIEW_SIZE)
                self.assertEqual(image.getpixel((0, 0)), (0, 0, 0))
                self.assertEqual(image.getpixel((1199, 629)), (0, 0, 0))
                self.assertGreater(sum(1 for pixel in image.crop((0, 40, 1200, 340)).getdata() if pixel[1] > 140 and pixel[2] > 140), 100)
                left, top, right, bottom = LOVE_MY_LOCALS_TOUCH_ICON_BOUNDS
                icon = image.crop((left, top, right, bottom))
                self.assertGreater(sum(1 for pixel in icon.getdata() if sum(pixel) > 300), 50)

    def test_love_my_locals_social_filename_is_isolated_and_other_branding_paths_are_unchanged(self):
        locals_name = social_preview_filename("Box Hill", ProjectType.LOVE_MY_LOCALS)
        business_name = social_preview_filename("Box Hill", ProjectType.BUSINESS)
        self.assertTrue(locals_name.startswith("social-card-love-my-locals-v1-"))
        self.assertTrue(locals_name.endswith(".png"))
        self.assertTrue(business_name.startswith("social-card-v2-"))
        self.assertTrue(business_name.endswith(".jpg"))

        video = _video()
        business = Project(
            slug="business-test", title="Business Test", ticker_text="Test", channel_url="", channel_id="",
            channel_title="Business", channel_thumbnail="", project_type=ProjectType.BUSINESS,
            business_config=BusinessConfig(), videos=[video], published_url="https://example.com/business-test/",
        )
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "business-qr.png"
            with patch("aggits_video_factory.site_builder.resource_path", wraps=resource_path) as resolver:
                create_qr_card(business, destination)
            self.assertIn("static/music-machine/crispy-bits-qr-template.png", [call.args[0] for call in resolver.call_args_list])


if __name__ == "__main__":
    unittest.main()
