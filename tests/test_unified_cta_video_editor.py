from __future__ import annotations

import json
import importlib.util
import logging
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from aggits_video_factory.config import MAX_VIDEOS
from aggits_video_factory.desktop_forms import (
    BUSINESS_CTA_CHOICES,
    CTA_CHOICES,
    TOURISM_CTA_CHOICES,
    ProjectFormValues,
    project_to_form_values,
    validate_project_form,
)
from aggits_video_factory.models import (
    BUSINESS_CTA_TYPES,
    MUSIC_CTA_TYPES,
    TOURISM_CTA_TYPES,
    BusinessConfig,
    MusicConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    TourismConfig,
    Video,
    project_primary_cta,
)
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.video_editor import VideoEditError, VideoSelectionSession
from aggits_video_factory.youtube_api import ChannelCatalogue, YouTubeError


def video(index: int) -> Video:
    video_id = f"video{index:06d}"
    return Video(
        video_id=video_id,
        title=f"Video {index}",
        display_title=f"Video {index}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        embed_url=f"https://www.youtube.com/embed/{video_id}",
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=180,
        channel_title="Fixture Channel",
        channel_id="UCfixture",
    )


def project(kind: ProjectType, cta: PrimaryCta, *, published: bool = False) -> Project:
    configs = {
        ProjectType.BUSINESS: dict(business_config=BusinessConfig(shop_url="https://legacy.example/shop", primary_cta=cta)),
        ProjectType.MUSIC: dict(music_config=MusicConfig(primary_cta=cta)),
        ProjectType.TOURISM: dict(tourism_config=TourismConfig(
            more_info_url="https://legacy.example/info",
            stay_url="https://legacy.example/stay",
            primary_cta=cta,
        )),
    }
    return Project(
        slug=f"{kind.value}-fixture",
        title=f"{kind.value.title()} Fixture",
        ticker_text="Authoritative manually supplied biography.",
        channel_url="https://www.youtube.com/@fixture",
        channel_id="UCfixture",
        channel_title="Fixture Channel",
        channel_thumbnail="",
        project_type=kind,
        videos=[video(1), video(2)],
        excluded_video_ids=[video(2).video_id],
        status="published" if published else "draft",
        published_url=f"https://example.com/{kind.value}/" if published else None,
        **configs[kind],
    )


class FakeClient:
    def __init__(self, result: Video | Exception) -> None:
        self.result = result
        self.calls: list[list[str]] = []

    def fetch_videos(self, urls: list[str]) -> ChannelCatalogue:
        self.calls.append(urls)
        if isinstance(self.result, Exception):
            raise self.result
        return ChannelCatalogue("UCfixture", "Fixture Channel", "", "", [self.result])


class UnifiedCtaTests(unittest.TestCase):
    def test_type_specific_option_lists_are_complete_and_isolated(self):
        self.assertEqual({item.value for item in BUSINESS_CTA_TYPES}, {
            "shop_now", "view_products", "get_a_quote", "book_now", "enquire_now",
            "find_a_store", "find_a_dealer", "book_a_demo", "contact_us", "visit_website", "custom",
        })
        self.assertEqual({item.value for item in MUSIC_CTA_TYPES}, {
            "spotify", "bandcamp", "buy_music", "merch", "tickets", "apple_music",
            "official_website", "book_now", "book_us", "soundcloud", "custom",
        })
        self.assertEqual({item.value for item in TOURISM_CTA_TYPES}, {
            "more_info", "stay", "explore", "book_now", "whats_on", "plan_your_visit",
            "visit_website", "custom",
        })
        self.assertEqual(len(BUSINESS_CTA_CHOICES), 11)
        self.assertEqual(len(CTA_CHOICES), 11)
        self.assertEqual(len(TOURISM_CTA_CHOICES), 8)
        self.assertNotIn(PrimaryCtaType.BOOK_US, BUSINESS_CTA_TYPES)
        self.assertNotIn(PrimaryCtaType.SHOP_NOW, TOURISM_CTA_TYPES)

    def test_top_and_bottom_use_same_structured_cta_for_all_project_types(self):
        cases = (
            (ProjectType.BUSINESS, PrimaryCtaType.GET_A_QUOTE, "GET A QUOTE", "https://example.com/quote"),
            (ProjectType.MUSIC, PrimaryCtaType.BOOK_US, "BOOK US", "https://example.com/book-us"),
            (ProjectType.TOURISM, PrimaryCtaType.PLAN_YOUR_VISIT, "PLAN YOUR VISIT", "https://example.com/plan"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for kind, cta_type, label, destination in cases:
                with self.subTest(kind=kind.value):
                    item = project(kind, PrimaryCta(cta_type, destination))
                    output = Path(temporary) / kind.value
                    build_project_site(item, output)
                    config = json.loads((output / "machine.json").read_text(encoding="utf-8"))
                    page = (output / "index.html").read_text(encoding="utf-8")
                    active = config["customerConfig"]["primaryAction"]
                    self.assertEqual(active, {
                        "type": cta_type.value,
                        "displayLabel": label,
                        "destinationURL": destination,
                        "enabled": True,
                    })
                    self.assertIn(f">{label}</b>", page)
                    self.assertEqual(config["videoCount"], 1)

        script = (Path(__file__).parents[1] / "static" / "video-machine.js").read_text(encoding="utf-8")
        self.assertIn("machine.dataset.projectType = activeProjectType", script)
        self.assertIn("primaryActionButton.dataset.ctaPlacement = 'bottom'", script)
        self.assertIn("shopPlaque.dataset.ctaPlacement = 'top'", script)
        self.assertIn("primaryActionButton.dataset.ctaType", script)
        self.assertIn("shopPlaque.dataset.ctaLabel", script)

    def test_custom_and_disabled_ctas_round_trip_without_stale_labels(self):
        for kind, label in (
            (ProjectType.BUSINESS, "REQUEST A CALLBACK"),
            (ProjectType.MUSIC, "SUPPORT THE BAND"),
            (ProjectType.TOURISM, "SEE THE REGION"),
        ):
            with self.subTest(kind=kind.value):
                values = ProjectFormValues(
                    title="Fixture", manual_video_urls=[video(1).url], cta_label="Custom",
                    destination_url="https://example.com/action", custom_label=label,
                )
                validated = validate_project_form(values, kind)
                config = validated.business_config or validated.music_config or validated.tourism_config
                self.assertEqual(config.primary_cta.display_label, label)
                restored_values = project_to_form_values(project(kind, config.primary_cta))
                self.assertEqual(restored_values.custom_label, label)

        disabled = PrimaryCta(PrimaryCtaType.SHOP_NOW, "", custom_label="STALE")
        self.assertEqual(disabled.display_label, "SHOP NOW")
        self.assertEqual(disabled.destination_url, "")

        with self.assertRaisesRegex(ValueError, "cannot exceed 40"):
            PrimaryCta(PrimaryCtaType.CUSTOM, "https://example.com", custom_label="X" * 41)

    def test_legacy_business_and_tourism_urls_are_preserved_and_adapted(self):
        business = Project.from_dict({**project(
            ProjectType.BUSINESS, PrimaryCta(PrimaryCtaType.SHOP_NOW, "https://example.com/shop")
        ).to_dict(), "business_config": {"shop_url": "https://example.com/shop"}})
        self.assertEqual(project_primary_cta(business).cta_type, PrimaryCtaType.SHOP_NOW)
        self.assertEqual(project_primary_cta(business).destination_url, "https://example.com/shop")

        source = project(ProjectType.TOURISM, PrimaryCta(PrimaryCtaType.MORE_INFO, "https://example.com/info")).to_dict()
        source["tourism_config"] = {
            "more_info_url": "https://example.com/info",
            "stay_url": "https://example.com/stay",
        }
        tourism = Project.from_dict(source)
        self.assertEqual(tourism.tourism_config.more_info_url, "https://example.com/info")
        self.assertEqual(tourism.tourism_config.stay_url, "https://example.com/stay")
        self.assertEqual(project_primary_cta(tourism).cta_type, PrimaryCtaType.MORE_INFO)
        self.assertEqual(project_primary_cta(tourism).destination_url, "https://example.com/info")


class VideoEditorTests(unittest.TestCase):
    def test_cancel_isolation_toggle_reinclude_and_identity_preservation(self):
        source = project(ProjectType.BUSINESS, PrimaryCta(PrimaryCtaType.GET_A_QUOTE, "https://example.com/quote"))
        original = source.to_dict()
        session = VideoSelectionSession(source)
        self.assertEqual(session.included_count, 1)
        session.set_included(video(1).video_id, False)
        session.set_included(video(2).video_id, True)
        self.assertEqual(source.to_dict(), original)  # Cancel is exact: source was never touched.
        revised = session.revised_project()
        self.assertEqual((revised.id, revised.slug, revised.project_type), (source.id, source.slug, source.project_type))
        self.assertIn(video(1).video_id, revised.excluded_video_ids)
        self.assertNotIn(video(2).video_id, revised.excluded_video_ids)
        self.assertEqual(project_primary_cta(revised).destination_url, "https://example.com/quote")

    def test_add_duplicate_reinstate_invalid_network_and_manual_round_trip(self):
        source = project(ProjectType.MUSIC, PrimaryCta(PrimaryCtaType.SOUNDCLOUD, "https://example.com/soundcloud"))
        session = VideoSelectionSession(source)
        result = session.add_url(video(2).url, FakeClient(video(99)))
        self.assertTrue(result.reinstated)
        with self.assertRaisesRegex(VideoEditError, "already included"):
            session.add_url(video(1).url, FakeClient(video(99)))
        with self.assertRaisesRegex(VideoEditError, "recognised"):
            session.add_url("https://example.com/not-youtube", FakeClient(video(99)))
        with self.assertRaises(YouTubeError):
            session.add_url(video(3).url, FakeClient(YouTubeError("quota unavailable")))

        added = session.add_url(video(3).url, FakeClient(video(3)))
        self.assertFalse(added.reinstated)
        revised = session.revised_project()
        self.assertIn(video(3).video_id, {item.video_id for item in revised.videos})
        self.assertIn(video(3).url, revised.manual_video_urls)
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            store.save_project(revised)
            restored = store.load_project(revised.slug)
            self.assertIn(video(3).video_id, {item.video_id for item in restored.videos})
            self.assertIn(video(3).url, restored.manual_video_urls)

    def test_limits_and_at_least_one_are_enforced_without_silent_replacement(self):
        source = project(ProjectType.TOURISM, PrimaryCta(PrimaryCtaType.STAY, "https://example.com/stay"))
        session = VideoSelectionSession(source, maximum=1)
        with self.assertRaisesRegex(VideoEditError, "Maximum 1"):
            session.set_included(video(2).video_id, True)
        session.set_included(video(1).video_id, False)
        with self.assertRaisesRegex(VideoEditError, "At least one"):
            session.revised_project()
        self.assertEqual(MAX_VIDEOS, 30)

    def test_published_edits_become_changes_pending_for_all_project_types(self):
        cases = (
            (ProjectType.BUSINESS, PrimaryCta(PrimaryCtaType.SHOP_NOW, "https://example.com/shop")),
            (ProjectType.MUSIC, PrimaryCta(PrimaryCtaType.SPOTIFY, "https://example.com/music")),
            (ProjectType.TOURISM, PrimaryCta(PrimaryCtaType.MORE_INFO, "https://example.com/info")),
        )
        for kind, cta in cases:
            with self.subTest(kind=kind.value):
                source = project(kind, cta, published=True)
                revised = VideoSelectionSession(source).revised_project()
                self.assertEqual(revised.status, "changes_pending")
                self.assertEqual(revised.id, source.id)
                self.assertEqual(revised.slug, source.slug)
                self.assertEqual(revised.published_url, source.published_url)

    def test_shared_video_editor_ui_smoke_at_supported_desktop_size(self):
        desktop_path = Path(__file__).parents[1] / "desktop" / "video_jukebox_factory.py"
        spec = importlib.util.spec_from_file_location("unified_cta_desktop", desktop_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        class Host(tk.Tk):
            _button = module.Factory._button
            _open_video_editor = module.Factory._open_video_editor

            def __init__(self):
                super().__init__()
                self.geometry("1120x720")
                self.settings = {"youtubeApiKey": "fixture"}
                self.logger = logging.getLogger("video-editor-ui-smoke")

        def widget_texts(widget: tk.Misc) -> list[str]:
            texts: list[str] = []
            for child in widget.winfo_children():
                try:
                    texts.append(str(child.cget("text")))
                except tk.TclError:
                    pass
                texts.extend(widget_texts(child))
            return texts

        host = Host()
        host.withdraw()
        try:
            fixture = project(
                ProjectType.BUSINESS,
                PrimaryCta(PrimaryCtaType.GET_A_QUOTE, "https://example.com/quote"),
            )
            host._open_video_editor(fixture)
            host.update_idletasks()
            dialogs = [child for child in host.winfo_children() if isinstance(child, tk.Toplevel)]
            self.assertEqual(len(dialogs), 1)
            dialog = dialogs[0]
            texts = widget_texts(dialog)
            self.assertIn("EDIT YOUTUBE VIDEOS", texts)
            self.assertIn("ADD YOUTUBE VIDEO URL", texts)
            self.assertIn("ADD VIDEO", texts)
            self.assertIn("SAVE CHANGES", texts)
            self.assertIn("CANCEL", texts)
            self.assertIn(f"1 / {MAX_VIDEOS} INCLUDED", texts)
            self.assertLessEqual(dialog.winfo_reqwidth(), 980)
            dialog.destroy()
        finally:
            host.destroy()


if __name__ == "__main__":
    unittest.main()
