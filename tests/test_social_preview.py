from __future__ import annotations

import functools
import tempfile
import threading
import unittest
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from PIL import Image, ImageDraw

from aggits_video_factory.models import (
    BusinessConfig,
    MusicConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    TourismConfig,
    Video,
)
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.publisher import _write_library
from aggits_video_factory.social_preview import (
    SOCIAL_PREVIEW_SIZE,
    SOCIAL_PREVIEW_VERSION,
    TITLE_SAFE_REGION,
    TOUCH_ICON_BOUNDS,
    create_social_preview,
    fit_social_title,
    normalise_social_title,
    social_preview_filename,
)


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.title = ""
        self._inside_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key:
                self.meta[key] = values.get("content") or ""
        elif tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href") or ""
        elif tag == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title += data


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def sample_video() -> Video:
    return Video(
        video_id="preview001",
        title="Preview test video",
        display_title="Preview test video",
        url="https://www.youtube.com/watch?v=preview001",
        embed_url="https://www.youtube.com/embed/preview001",
        thumbnail_url="https://i.ytimg.com/vi/preview001/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=120,
        channel_title="Preview Channel",
    )


def project_for(project_type: ProjectType, title: str = "WRAITH") -> Project:
    common = dict(
        slug=f"preview-{project_type.value}",
        title=title,
        ticker_text="Canonical manually supplied Bio text.",
        channel_url="https://www.youtube.com/channel/UCpreview",
        channel_id="UCpreview",
        channel_title="Preview Channel",
        channel_thumbnail="",
        project_type=project_type,
        videos=[sample_video()],
        published_url=f"https://example.com/crispy-bits/preview-{project_type.value}/",
    )
    if project_type is ProjectType.BUSINESS:
        return Project(**common, business_config=BusinessConfig())
    if project_type is ProjectType.MUSIC:
        return Project(
            **common,
            music_config=MusicConfig(PrimaryCta(PrimaryCtaType.SPOTIFY, "https://example.com/listen")),
        )
    return Project(**common, tourism_config=TourismConfig())


class UniversalSocialPreviewTests(unittest.TestCase):
    def test_title_fitting_uses_measured_safe_region_for_required_matrix(self):
        canvas = Image.new("RGB", SOCIAL_PREVIEW_SIZE)
        draw = ImageDraw.Draw(canvas)
        cases = (
            ("WRAITH", 1),
            ("UNCLE MUNGO'S", 2),
            ("CAPRI APARTMENTS MERIMBULA", 2),
            ("THE EXTRAORDINARILY LONG MIDNIGHT TEST BUSINESS", 2),
        )
        left, top, right, bottom = TITLE_SAFE_REGION
        for title, maximum_lines in cases:
            with self.subTest(title=title):
                layout = fit_social_title(draw, title)
                self.assertLessEqual(len(layout.lines), maximum_lines)
                self.assertGreaterEqual(layout.bounds[0], left)
                self.assertGreaterEqual(layout.bounds[1], top)
                self.assertLessEqual(layout.bounds[2], right)
                self.assertLessEqual(layout.bounds[3], bottom)
                self.assertEqual(" ".join(layout.lines), title)

        mixed_case = "Good Night Out."
        self.assertEqual(normalise_social_title(mixed_case), mixed_case)
        self.assertEqual(" ".join(fit_social_title(draw, mixed_case).lines), mixed_case)

        unbroken = "X" * 120
        layout = fit_social_title(draw, unbroken)
        self.assertLessEqual(len(layout.lines), 2)
        self.assertEqual("".join(layout.lines), unbroken)
        self.assertGreaterEqual(layout.bounds[0], left)
        self.assertLessEqual(layout.bounds[2], right)

    def test_every_current_project_type_inherits_raw_crawler_metadata_and_unique_image(self):
        for project_type in ProjectType:
            with self.subTest(project_type=project_type.value), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary)
                project = project_for(project_type)
                build_project_site(project, destination)
                parser = MetadataParser()
                raw_html = (destination / "index.html").read_text(encoding="utf-8")
                parser.feed(raw_html)
                expected_url = project.published_url
                expected_image = f"{expected_url}{social_preview_filename(project.title)}"
                expected_description = f"Hit it. Discover {project.title} with Crispy Bits."
                self.assertEqual(parser.title, f"{project.title} | Crispy Bits")
                self.assertEqual(parser.canonical, expected_url)
                self.assertEqual(parser.meta["og:type"], "website")
                self.assertEqual(parser.meta["og:title"], project.title)
                self.assertEqual(parser.meta["og:description"], expected_description)
                self.assertEqual(parser.meta["og:url"], expected_url)
                self.assertEqual(parser.meta["og:image"], expected_image)
                self.assertEqual(parser.meta["og:image:secure_url"], expected_image)
                self.assertEqual(parser.meta["og:image:width"], "1200")
                self.assertEqual(parser.meta["og:image:height"], "630")
                self.assertEqual(parser.meta["og:image:alt"], f"{project.title} — Crispy Bits social preview")
                self.assertEqual(parser.meta["twitter:card"], "summary_large_image")
                self.assertEqual(parser.meta["twitter:title"], project.title)
                self.assertEqual(parser.meta["twitter:description"], expected_description)
                self.assertEqual(parser.meta["twitter:image"], expected_image)
                self.assertEqual(parser.meta["twitter:image:alt"], f"{project.title} — Crispy Bits social preview")
                self.assertEqual(parser.meta["description"], expected_description)
                self.assertTrue(expected_image.startswith("https://"))
                image_path = destination / social_preview_filename(project.title)
                self.assertTrue(image_path.is_file())
                with Image.open(image_path) as image:
                    self.assertEqual(image.size, SOCIAL_PREVIEW_SIZE)
                    self.assertEqual(image.format, "JPEG")

    def test_minimal_card_is_title_only_and_independent_of_project_content(self):
        rendered_cards: list[bytes] = []
        for project_type in ProjectType:
            with self.subTest(project_type=project_type.value), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary)
                project = project_for(project_type, "SHARED PROJECT TITLE")
                project.channel_thumbnail = f"https://example.com/{project_type.value}-customer-logo.png"
                project.ticker_text = f"Unique {project_type.value} Bio content that must not affect the card."
                build_project_site(project, destination)
                image_path = destination / social_preview_filename(project.title)
                rendered_cards.append(image_path.read_bytes())

        self.assertEqual(SOCIAL_PREVIEW_VERSION, "v2")
        self.assertTrue(all(card == rendered_cards[0] for card in rendered_cards[1:]))
        renderer_source = Path(create_social_preview.__code__.co_filename).read_text(encoding="utf-8")
        self.assertNotIn("crispy-bits-social-preview-template.png", renderer_source)
        self.assertNotIn('"PRESS"', renderer_source)
        self.assertNotIn('"HIT IT"', renderer_source)

    def test_dark_navy_vignette_and_small_touch_icon_are_rendered(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / social_preview_filename(None)
            layout = create_social_preview(None, destination)
            self.assertEqual(layout.lines, ())
            with Image.open(destination) as image:
                image = image.convert("RGB")
                corner = image.getpixel((8, 8))
                centre = image.getpixel((image.width // 2, image.height // 2))
                self.assertGreater(sum(centre), sum(corner) + 30)
                self.assertGreater(centre[2], centre[0])

                left, top, right, bottom = TOUCH_ICON_BOUNDS
                self.assertLess(right - left, image.width // 10)
                self.assertLess(bottom - top, image.height // 5)
                icon_point = image.getpixel(((left + right) // 2, top + 20))
                background_control = image.getpixel((left - 80, top + 20))
                self.assertGreater(sum(icon_point), sum(background_control) + 250)

    def test_title_edit_busts_cache_and_prunes_old_generated_card(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            project = project_for(ProjectType.BUSINESS, "WRAITH")
            build_project_site(project, destination)
            first_name = social_preview_filename(project.title)
            self.assertTrue((destination / first_name).is_file())
            project.title = "UNCLE MUNGO'S"
            build_project_site(project, destination)
            second_name = social_preview_filename(project.title)
            self.assertNotEqual(first_name, second_name)
            self.assertFalse((destination / first_name).exists())
            self.assertEqual([path.name for path in destination.glob("social-card-*.jpg")], [second_name])
            self.assertIn(second_name, (destination / "index.html").read_text(encoding="utf-8"))

    def test_existing_library_cards_keep_legacy_image_while_new_cards_use_versioned_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            versioned = social_preview_filename("WRAITH")
            _write_library(workspace, [
                {"slug": "legacy", "title": "Legacy", "videoCount": 1},
                {"slug": "wraith", "title": "WRAITH", "videoCount": 2, "socialImage": versioned},
            ])
            index = (workspace / "public" / "crispy-bits" / "index.html").read_text(encoding="utf-8")
            self.assertIn('legacy/social-card.jpg', index)
            self.assertIn(f'wraith/{versioned}', index)

    def test_missing_title_produces_valid_unbranded_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / social_preview_filename(None)
            layout = create_social_preview(None, destination)
            self.assertEqual(layout.lines, ())
            with Image.open(destination) as image:
                self.assertEqual(image.size, SOCIAL_PREVIEW_SIZE)
                self.assertEqual(image.format, "JPEG")

    def test_generated_image_is_served_without_authentication(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            project = project_for(ProjectType.BUSINESS)
            build_project_site(project, destination)
            handler = functools.partial(QuietHandler, directory=str(destination))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                filename = social_preview_filename(project.title)
                with urlopen(f"http://127.0.0.1:{server.server_port}/{filename}", timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), "image/jpeg")
                    self.assertTrue(response.read(3).startswith(b"\xff\xd8\xff"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
