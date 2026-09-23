from __future__ import annotations

import hashlib
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from aggits_video_factory.business_workflow import assemble_channel_master_project
from aggits_video_factory.config import (
    MAX_CHANNEL_MASTER_TICKER_LENGTH,
    MAX_CHANNEL_MASTER_REVIEW_VIDEOS,
    MAX_CHANNEL_MASTER_VIDEOS,
    video_limit_for_project_type,
)
from aggits_video_factory.delivery import request_delivery
from aggits_video_factory.desktop_forms import (
    BUSINESS_CTA_CHOICES,
    CHANNEL_MASTER_CTA_CHOICES,
    CTA_CHOICES,
    CTA_CHOICES_BY_PROJECT,
    TOURISM_CTA_CHOICES,
    FormValidationError,
    ProjectFormValues,
    project_is_visible_in_tab,
    project_to_form_values,
    validate_project_form,
)
from aggits_video_factory.models import (
    CHANNEL_MASTER_CTA_TYPES,
    CHANNEL_MASTER_PALETTES,
    ChannelMasterConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    ProjectValidationError,
    Video,
    allowed_primary_cta_types,
)
from aggits_video_factory.publisher import Publisher, _validate_project_type
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.video_editor import VideoEditError, VideoSelectionSession
from aggits_video_factory.youtube_api import ChannelCatalogue, merge_video_selections
from desktop.video_jukebox_factory import ProjectForm


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
DESKTOP = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")


def video(index: int) -> Video:
    video_id = f"master{index:05d}"[:11]
    return Video(
        video_id=video_id,
        title=f"Channel Master video {index}",
        display_title=f"Video {index}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        embed_url=f"https://www.youtube.com/embed/{video_id}",
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        published_at="2026-09-01T00:00:00Z",
        duration_seconds=90,
        channel_title="Master Channel",
    )


def master_project(*, count: int = 1, config: ChannelMasterConfig | None = None, ticker: str = "FIRST\nSECOND") -> Project:
    return Project(
        slug="channel-master-fixture",
        title="CHANNEL MASTER FIXTURE",
        ticker_text=ticker,
        channel_url="https://www.youtube.com/channel/UCmaster",
        channel_id="UCmaster",
        channel_title="Master Channel",
        channel_thumbnail="https://example.com/internal-thumbnail.jpg",
        project_type=ProjectType.CHANNEL_MASTER,
        additional_urls=["https://example.com/one", "https://example.com/two"],
        channel_master_config=config or ChannelMasterConfig(
            palette="OCEAN",
            primary_cta=PrimaryCta(PrimaryCtaType.TICKETS, "https://example.com/tickets"),
            contact_url="https://example.com/contact",
        ),
        videos=[video(index) for index in range(count)],
    )


class ChannelMasterModelTests(unittest.TestCase):
    def test_type_limits_and_ticker_policy_are_isolated(self):
        self.assertEqual(ProjectType.CHANNEL_MASTER.value, "channel_master")
        self.assertEqual(video_limit_for_project_type(ProjectType.CHANNEL_MASTER), 50)
        self.assertEqual(MAX_CHANNEL_MASTER_VIDEOS, 50)
        self.assertEqual(MAX_CHANNEL_MASTER_REVIEW_VIDEOS, 50)
        self.assertEqual(MAX_CHANNEL_MASTER_TICKER_LENGTH, 1500)
        for kind, expected in (
            (ProjectType.BUSINESS, 30), (ProjectType.MUSIC, 30),
            (ProjectType.TOURISM, 30), (ProjectType.BANJO, 40),
        ):
            self.assertEqual(video_limit_for_project_type(kind), expected)

    def test_exactly_fifty_videos_pass_and_fifty_one_fail(self):
        for count in (1, 5, 49, 50):
            with self.subTest(count=count):
                self.assertEqual(len(master_project(count=count).videos), count)
        with self.assertRaisesRegex(ProjectValidationError, "no more than 50"):
            master_project(count=51)
        source_catalogue = [video(i) for i in range(60)]
        review_pool = merge_video_selections([], source_catalogue, MAX_CHANNEL_MASTER_REVIEW_VIDEOS)
        self.assertEqual(len(review_pool), 50)
        self.assertEqual(
            [item.video_id for item in merge_video_selections([video(0)], [video(0), video(1)], 50)],
            [video(0).video_id, video(1).video_id],
        )

    def test_manual_urls_and_video_editor_respect_fifty_save_cancel_and_reinclude(self):
        urls = [f"https://www.youtube.com/watch?v=m{index:010d}" for index in range(50)]
        validated = validate_project_form(ProjectFormValues(
            title="MASTER TV", manual_video_urls=urls, cta_label="Visit Website",
            destination_url="https://example.com",
        ), ProjectType.CHANNEL_MASTER)
        self.assertEqual(len(validated.manual_video_urls), 50)
        with self.assertRaisesRegex(FormValidationError, "(?i)no more than 50"):
            validate_project_form(ProjectFormValues(
                title="MASTER TV", manual_video_urls=urls + ["https://www.youtube.com/watch?v=overflow001"],
                cta_label="Visit Website", destination_url="https://example.com",
            ), ProjectType.CHANNEL_MASTER)

        original = master_project(count=5)
        session = VideoSelectionSession(original)
        session.set_included(video(1).video_id, False)
        self.assertEqual(session.included_count, 4)
        session.set_included(video(1).video_id, True)
        self.assertEqual(session.included_count, 5)
        self.assertEqual(original.excluded_video_ids, [])  # Cancel leaves source untouched.
        session.set_included(video(2).video_id, False)
        revised = session.revised_project()
        self.assertIn(video(2).video_id, revised.excluded_video_ids)
        restored = VideoSelectionSession(revised)
        restored.set_included(video(2).video_id, True)
        self.assertNotIn(video(2).video_id, restored.revised_project().excluded_video_ids)

        full = VideoSelectionSession(master_project(count=50))
        with self.assertRaisesRegex(VideoEditError, "Maximum 50"):
            full.add_url("https://www.youtube.com/watch?v=newvideo001", mock.Mock())

    def test_deduplicated_cta_union_contains_every_current_source_action(self):
        union_types = [item[1] for item in CHANNEL_MASTER_CTA_CHOICES]
        source_types = {item[1] for item in (*BUSINESS_CTA_CHOICES, *CTA_CHOICES, *TOURISM_CTA_CHOICES)}
        self.assertEqual(set(union_types), source_types)
        self.assertEqual(set(union_types), set(CHANNEL_MASTER_CTA_TYPES))
        self.assertEqual(len(union_types), len(set(union_types)))
        self.assertEqual(union_types.count(PrimaryCtaType.BOOK_NOW), 1)
        self.assertEqual(union_types.count(PrimaryCtaType.VISIT_WEBSITE), 1)
        self.assertEqual(union_types.count(PrimaryCtaType.CUSTOM), 1)
        self.assertEqual(union_types[-1], PrimaryCtaType.CUSTOM)
        self.assertEqual(CTA_CHOICES_BY_PROJECT[ProjectType.BUSINESS], BUSINESS_CTA_CHOICES)
        self.assertEqual(CTA_CHOICES_BY_PROJECT[ProjectType.MUSIC], CTA_CHOICES)
        self.assertEqual(CTA_CHOICES_BY_PROJECT[ProjectType.TOURISM], TOURISM_CTA_CHOICES)
        self.assertEqual(CTA_CHOICES_BY_PROJECT[ProjectType.BANJO], ())
        visible_labels = {label.upper() for label, _ in CHANNEL_MASTER_CTA_CHOICES}
        self.assertTrue({
            "LISTEN ON SPOTIFY", "PLAN YOUR VISIT", "OFFICIAL WEBSITE",
            "VIEW PRODUCTS", "FIND A DEALER",
        }.issubset(visible_labels))

    def test_every_union_action_reuses_deterministic_identity_label_and_safe_url(self):
        for visible, cta_type in CHANNEL_MASTER_CTA_CHOICES:
            with self.subTest(cta=cta_type.value):
                kwargs = {"custom_label": "MY ACTION"} if cta_type is PrimaryCtaType.CUSTOM else {}
                cta = PrimaryCta(cta_type, "https://example.com/action", **kwargs)
                self.assertIn(cta_type, allowed_primary_cta_types(ProjectType.CHANNEL_MASTER))
                self.assertEqual(cta.display_label, "MY ACTION" if kwargs else visible.upper())
                config = ChannelMasterConfig(palette="MIDNIGHT", primary_cta=cta)
                self.assertEqual(config.resolved_primary, CHANNEL_MASTER_PALETTES["MIDNIGHT"][0])
        with self.assertRaises(ProjectValidationError):
            PrimaryCta(PrimaryCtaType.SHOP_NOW, "javascript:alert(1)")
        standard = PrimaryCta(PrimaryCtaType.BOOK_NOW, "https://example.com", custom_label="STALE")
        self.assertEqual(standard.display_label, "BOOK NOW")
        self.assertEqual(standard.custom_label, "STALE")

    def test_palette_resolution_is_safe_deterministic_and_round_trips(self):
        for name, expected in CHANNEL_MASTER_PALETTES.items():
            self.assertEqual(
                (ChannelMasterConfig(palette=name).resolved_primary,
                 ChannelMasterConfig(palette=name).resolved_secondary,
                 ChannelMasterConfig(palette=name).resolved_accent),
                expected,
            )
        custom = ChannelMasterConfig(palette="CUSTOM", custom_primary="#FFFFFF", custom_accent="#FFFFFF")
        self.assertNotEqual(custom.resolved_primary, "#FFFFFF")
        self.assertNotEqual(custom.resolved_secondary, custom.resolved_primary)
        self.assertNotEqual(custom.resolved_accent, "#FFFFFF")
        with self.assertRaises(ProjectValidationError):
            ChannelMasterConfig(palette="CUSTOM", custom_primary="red; background:url(x)", custom_accent="#123456")

        # Brand-inspired QA fixtures remain colour-only, safely muted, and
        # cannot affect the canonical mechanical assets or brass borders.
        for primary, accent in (
            ("#202020", "#FFD400"),  # Richmond-style
            ("#EC7FA9", "#FF9DBD"),  # Pink-Lemonade-style
            ("#52633A", "#91A957"),  # Brewmanity-style
        ):
            fixture = ChannelMasterConfig(palette="CUSTOM", custom_primary=primary, custom_accent=accent)
            self.assertLessEqual(int(fixture.resolved_primary[1:3], 16), int(primary[1:3], 16))
            self.assertRegex(fixture.resolved_secondary, r"^#[0-9A-F]{6}$")

        stored = ChannelMasterConfig(palette="OCEAN").to_dict()
        expected = (stored["resolved_primary"], stored["resolved_secondary"], stored["resolved_accent"])
        with mock.patch.dict(CHANNEL_MASTER_PALETTES, {"OCEAN": ("#111111", "#050505", "#222222")}):
            restored = ChannelMasterConfig.from_dict(stored)
        self.assertEqual(
            (restored.resolved_primary, restored.resolved_secondary, restored.resolved_accent), expected,
        )

    def test_ticker_limit_escaping_normalisation_and_single_lifecycle(self):
        self.assertEqual(len(master_project(ticker="X" * 1500).ticker_text), 1500)
        with self.assertRaisesRegex(ProjectValidationError, "1500"):
            master_project(ticker="X" * 1501)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(master_project(ticker="FIRST\n<script>alert(1)</script>\nTHIRD"), destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
        self.assertIn("FIRST • &lt;script&gt;alert(1)&lt;/script&gt; • THIRD", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertEqual(SCRIPT.count("startChannelMasterHeaderTicker();"), 1)
        ticker_function = SCRIPT.split("function startChannelMasterHeaderTicker()", 1)[1].split("function ", 1)[0]
        self.assertIn("CHANNEL_MASTER_TICKER_DELAY", ticker_function)
        self.assertIn("const CHANNEL_MASTER_TICKER_DELAY = 10000;", SCRIPT)

    def test_projectstore_dictionary_round_trip_preserves_identity_and_config(self):
        original = master_project()
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            store.save_project(original)
            restored = ProjectStore(Path(temporary)).load_project(original.slug)
        self.assertEqual((restored.id, restored.slug, restored.project_type), (original.id, original.slug, original.project_type))
        self.assertEqual(restored.channel_master_config.to_dict(), original.channel_master_config.to_dict())
        self.assertEqual(restored.additional_urls, original.additional_urls)
        self.assertEqual(project_to_form_values(restored).palette, "OCEAN")

    def test_cross_type_configs_are_rejected(self):
        with self.assertRaisesRegex(ProjectValidationError, "another project type"):
            Project.from_dict({**master_project().to_dict(), "business_config": {}})


class ChannelMasterWorkflowTests(unittest.TestCase):
    def test_form_validates_all_fields_and_uses_one_primary_url(self):
        values = validate_project_form(ProjectFormValues(
            title="MASTER TV",
            channel_url="https://www.youtube.com/channel/UCmaster",
            additional_urls=["https://example.com/one", "https://example.com/two", "https://example.com/three"],
            story_text="Line one\nLine two",
            cta_label="Buy on Bandcamp",
            destination_url="https://example.com/bandcamp",
            palette="CUSTOM",
            custom_primary="#8844CC",
            custom_accent="#DDAA33",
            contact_url="https://example.com/contact",
        ), ProjectType.CHANNEL_MASTER)
        config = values.channel_master_config
        self.assertEqual(config.primary_cta.cta_type, PrimaryCtaType.BANDCAMP)
        self.assertEqual(config.primary_cta.destination_url, "https://example.com/bandcamp")
        self.assertEqual(config.contact_url, "https://example.com/contact")
        self.assertEqual(values.additional_urls, ["https://example.com/one", "https://example.com/two", "https://example.com/three"])

        with self.assertRaises(FormValidationError) as cta_error:
            validate_project_form(ProjectFormValues(
                title="MASTER TV", channel_url="https://www.youtube.com/channel/UCmaster",
                cta_label="Shop Now", destination_url="",
            ), ProjectType.CHANNEL_MASTER)
        self.assertEqual(cta_error.exception.field, "destination_url")

        with self.assertRaises(FormValidationError) as contact_error:
            validate_project_form(ProjectFormValues(
                title="MASTER TV", channel_url="https://www.youtube.com/channel/UCmaster",
                cta_label="Shop Now", destination_url="https://example.com/shop",
                palette="MIDNIGHT", contact_url="javascript:alert(1)",
            ), ProjectType.CHANNEL_MASTER)
        self.assertEqual(contact_error.exception.field, "contact_url")

        with self.assertRaises(FormValidationError) as colour_error:
            validate_project_form(ProjectFormValues(
                title="MASTER TV", channel_url="https://www.youtube.com/channel/UCmaster",
                cta_label="Shop Now", destination_url="https://example.com/shop",
                palette="CUSTOM", custom_primary="not-a-colour", custom_accent="#DDAA33",
            ), ProjectType.CHANNEL_MASTER)
        self.assertEqual(colour_error.exception.field, "custom_primary")

    def test_reviewed_assembly_preserves_identity_and_marks_published_edit_pending(self):
        existing = master_project()
        existing.published_url = "https://example.com/crispy-bits/channel-master-fixture/"
        existing.status = "published"
        values = validate_project_form(project_to_form_values(existing), ProjectType.CHANNEL_MASTER)
        catalogue = ChannelCatalogue(existing.channel_id, existing.channel_title, existing.channel_url, existing.channel_thumbnail, existing.videos)
        revised = assemble_channel_master_project(
            values=values, catalogue=catalogue, selected_videos=existing.videos,
            reviewed_videos=existing.videos, source_results=[], slug=existing.slug, existing=existing,
        )
        self.assertEqual((revised.id, revised.slug, revised.published_url), (existing.id, existing.slug, existing.published_url))
        self.assertEqual(revised.status, "changes_pending")

        reviewed = [video(index) for index in range(60)]
        selected = reviewed[:50]
        catalogue = ChannelCatalogue(
            existing.channel_id, existing.channel_title, existing.channel_url,
            existing.channel_thumbnail, reviewed,
        )
        new_project = assemble_channel_master_project(
            values=values, catalogue=catalogue, selected_videos=selected,
            reviewed_videos=reviewed, source_results=[], slug="large-channel-review",
        )
        self.assertEqual(len(new_project.videos), 60)
        self.assertEqual(len(new_project.excluded_video_ids), 10)

    def test_public_machine_is_clean_scoped_and_contextual(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(master_project(), destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
            payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
        self.assertIn('data-project-type="channel_master"', page)
        self.assertIn("CHANNEL MASTER FIXTURE", page)
        self.assertIn("FIRST • SECOND", page)
        self.assertIn("channel-master-header-ticker", page)
        self.assertIn('class="channel-master-maker-mark" aria-hidden="true"', page)
        self.assertIn('assets/channel-master/crispy-bits-maker-mark-approved.png', page)
        self.assertIn('class="channel-master-footer-mark" aria-hidden="true"', page)
        self.assertIn('<span>✷</span>', page)
        self.assertEqual(page.count('>CRISPY BITS<'), 1)
        self.assertEqual(page.count('>© CLEARLIGHTCREATIVE2020<'), 1)
        footer = page.split('class="channel-master-footer-mark"', 1)[1].split('</footer>', 1)[0]
        self.assertNotIn("href=", footer)
        self.assertNotIn("<button", footer)
        self.assertIn('data-channel-master-title-plaque aria-hidden="true">CHANNEL MASTER FIXTURE</div>', page)
        self.assertIn("CONTACT US", page)
        for rejected in ('data-action="home"', 'data-action="sound"', 'data-shop-plaque-prompt',
                         'class="customer-story"', 'class="brand-signature"', "BANJO'S", "banjo-header-character"):
            self.assertNotIn(rejected, page)
        self.assertNotIn("POWERED BY", page)
        self.assertIn("--theme-primary:#123E52", page)
        self.assertEqual(payload["projectType"], "channel_master")
        self.assertEqual(payload["videoCount"], 1)
        self.assertEqual(payload["customerConfig"]["primaryAction"]["displayLabel"], "GET TICKETS")
        self.assertEqual(payload["channelMasterConfig"]["contact"]["url"], "https://example.com/contact")
        self.assertNotIn("customLabel", payload["channelMasterConfig"]["primaryAction"])
        self.assertNotIn("banjoConfig", payload)
        for duplicate_field in ("plaqueTitle", "plaqueText", "shortTitle", "reelTitle"):
            self.assertNotIn(duplicate_field, payload)

    def test_title_plaque_is_escaped_static_scoped_and_uses_length_fitting(self):
        for title, fit_class in (
            ("SHORT TITLE", ""),
            ("A MEDIUM LENGTH CHANNEL MASTER TITLE", "channel-master-title-plaque--long"),
            ("A VERY LONG BUT VALID CHANNEL MASTER PROJECT TITLE FOR DISPLAY", "channel-master-title-plaque--very-long"),
        ):
            with self.subTest(title=title), tempfile.TemporaryDirectory() as temporary:
                item = master_project()
                item.title = title
                destination = Path(temporary)
                build_project_site(item, destination)
                page = (destination / "index.html").read_text(encoding="utf-8")
                plaque_opening = page.split('data-channel-master-title-plaque', 1)[0].rsplit('<div', 1)[-1]
                if fit_class:
                    self.assertIn(fit_class, plaque_opening)
                else:
                    self.assertNotIn("channel-master-title-plaque--", plaque_opening)

        unsafe = master_project()
        unsafe.title = "MASTER <SCRIPT> & CO"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(unsafe, destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
        self.assertIn("MASTER &lt;SCRIPT&gt; &amp; CO", page)
        self.assertNotIn("MASTER <SCRIPT> & CO", page)
        plaque_rule = CSS.split(
            '.music-machine[data-project-type="channel_master"] .channel-master-title-plaque{', 1
        )[1].split("}", 1)[0]
        self.assertNotIn("var(--theme-", plaque_rule)
        self.assertIn("pointer-events:none", plaque_rule)
        self.assertNotIn("channel-master-title-plaque", SCRIPT)

    def test_empty_ticker_stays_title_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(master_project(ticker=""), destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("data-channel-master-header-ticker", page)

    def test_palette_css_is_scoped_and_frozen_engine_files_are_untouched_by_type(self):
        self.assertIn('[data-project-type="channel_master"]', CSS)
        self.assertIn("--theme-primary", CSS)
        self.assertIn("--theme-secondary", CSS)
        self.assertIn("--theme-accent", CSS)
        self.assertIn("white-space:normal;overflow-wrap:anywhere", CSS)
        for filename in ("single-reel-engine.js", "machine-mechanics-core.js"):
            self.assertNotIn("channel_master", (ROOT / "static" / filename).read_text(encoding="utf-8"))
        self.assertIn("activeProjectType === 'banjo' || activeProjectType === 'channel_master'", SCRIPT)
        self.assertIn("plaqueDestination = primaryActionDestination", SCRIPT)
        self.assertIn("if (activeProjectType === 'channel_master') plaqueDestination = ''", SCRIPT)
        self.assertIn("startChannelMasterHeaderTicker();", SCRIPT)
        maker_rule = CSS.split(
            '.music-machine[data-project-type="channel_master"] .channel-master-maker-mark{', 1
        )[1].split("}", 1)[0]
        self.assertNotIn("var(--theme-", maker_rule)
        self.assertIn("pointer-events:none", maker_rule)
        self.assertIn("width:clamp(72px,13vw,104px)", maker_rule)
        self.assertNotIn("channel-master-maker-mark", SCRIPT)
        footer_rule = CSS.split(
            '.music-machine[data-project-type="channel_master"] .channel-master-footer-mark{', 1
        )[1].split("}", 1)[0]
        self.assertNotIn("var(--theme-", footer_rule)
        self.assertIn("width:clamp(88px,18%,132px)", footer_rule)
        self.assertIn("pointer-events:none", footer_rule)
        self.assertNotIn("channel-master-footer-mark", SCRIPT)

    def test_approved_maker_mark_is_transparent_hash_protected_and_packaged(self):
        asset = ROOT / "static" / "channel-master" / "crispy-bits-maker-mark-approved.png"
        self.assertEqual(
            hashlib.sha256(asset.read_bytes()).hexdigest().upper(),
            "68B1EACDD4BE7F58BE0F7884226F0CF2FC398188B46CFB905F4888C10C2D5632",
        )
        with Image.open(asset) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.size, (1280, 432))
            self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_project_site(master_project(), destination)
            packaged = destination / "assets" / "channel-master" / asset.name
            self.assertTrue(packaged.is_file())
            self.assertEqual(packaged.read_bytes(), asset.read_bytes())

    def test_desktop_declares_exact_five_tabs_and_required_channel_master_controls(self):
        self.assertIn(
            "ProjectType.BUSINESS, ProjectType.MUSIC, ProjectType.TOURISM,\n            ProjectType.BANJO, ProjectType.CHANNEL_MASTER",
            DESKTOP,
        )
        for copy in (
            "Additional URL", "Ticker Text", "Primary CTA URL", "Custom CTA Label",
            "Colour Palette", "Custom Primary", "Custom Accent", "Contact URL",
        ):
            self.assertIn(copy, DESKTOP)

    def test_channel_master_form_smoke_at_supported_desktop_sizes(self):
        root = tk.Tk()
        root.withdraw()
        try:
            form = ProjectForm(root, ProjectType.CHANNEL_MASTER, lambda: None, lambda: None)
            form.pack(fill="both", expand=True)
            self.assertEqual(len(form.manual_vars), 50)
            self.assertEqual(form.ticker_limit, 1500)
            for field in (
                "title", "channel_url", "additional_urls", "story_text", "cta_type",
                "destination_url", "custom_label", "palette", "custom_primary",
                "custom_accent", "contact_url", "manual_video_urls",
            ):
                self.assertIn(field, form.field_widgets)
            self.assertNotIn("banjo_choices", form.field_widgets)
            for width, height in ((1320, 820), (1120, 720)):
                root.geometry(f"{width}x{height}")
                root.update_idletasks()
                self.assertGreater(form.winfo_reqheight(), 0)
                self.assertGreater(form.winfo_reqwidth(), 0)
        finally:
            root.destroy()

    def test_shared_publisher_delivery_and_qr_contract_accept_type(self):
        item = master_project()
        _validate_project_type(item)
        item.status = "published"
        item.published_url = "https://example.com/crispy-bits/channel-master-fixture/"
        item.publication_revision = "a" * 40
        response = mock.Mock(status_code=200)
        response.json.return_value = {"ok": True, "id": "fixture", "sentAt": "2026-09-01T00:00:00Z"}
        with mock.patch("aggits_video_factory.delivery.requests.post", return_value=response) as post:
            request_delivery(
                item, "owner@example.com", secret="secret", timestamp=1_700_000_000, nonce="1" * 32,
            )
        payload = json.loads(post.call_args.kwargs["data"].decode("utf-8"))
        self.assertEqual(payload["projectType"], "channel_master")
        self.assertEqual(payload["productName"], "CRISPY BITS CHANNEL MASTER")

        self.assertTrue(project_is_visible_in_tab(item, ProjectType.CHANNEL_MASTER))
        for other_type in (
            ProjectType.BUSINESS, ProjectType.MUSIC, ProjectType.TOURISM, ProjectType.BANJO,
        ):
            self.assertFalse(project_is_visible_in_tab(item, other_type))

        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            build_project_site(item, first)
            item.channel_master_config = ChannelMasterConfig(palette="FOREST")
            build_project_site(item, second)
            self.assertEqual((first / "qr-card.png").read_bytes(), (second / "qr-card.png").read_bytes())

    def test_publish_unpublish_republish_reuses_stable_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            item = master_project()
            store.save_project(item)
            build_project_site(item, store.project_dir(item.slug) / "site")
            workspace = Path(temporary) / "workspace"
            revisions = iter(["revision-one", "revision-two", "revision-three"])

            def fake_git(command, **_kwargs):
                if "diff" in command:
                    return f"public/crispy-bits/{item.slug}"
                if "rev-parse" in command:
                    return next(revisions)
                return ""

            publisher = Publisher(store)
            with mock.patch.object(publisher, "ensure_workspace", return_value=workspace), \
                    mock.patch.object(publisher, "_wait_for_publication"), \
                    mock.patch.object(publisher, "_wait_for_unpublication"), \
                    mock.patch("aggits_video_factory.publisher._run", side_effect=fake_git):
                first_url, _ = publisher.publish(item)
                item.status = "published"
                store.save_project(item)
                publisher.unpublish(item)
                item.status = "unpublished"
                item.published_url = None
                item.publication_revision = None
                store.save_project(item)
                build_project_site(item, store.project_dir(item.slug) / "site")
                second_url, _ = publisher.publish(item)

            self.assertEqual(first_url, second_url)
            library = json.loads(
                (workspace / "public" / "crispy-bits" / "library.json").read_text(encoding="utf-8")
            )
            self.assertEqual(library[0]["projectType"], "channel_master")

    def test_other_project_types_have_no_channel_master_public_payload(self):
        from tests.test_banjo_workflow import project as banjo_project
        from tests.test_business_shop_plaque import business_project, music_project
        from tests.test_tourism_workflow import tourism_project
        for item in (business_project("https://example.com/shop"), music_project(), tourism_project(), banjo_project()):
            with self.subTest(kind=item.project_type.value), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary)
                build_project_site(item, destination)
                payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
                page = (destination / "index.html").read_text(encoding="utf-8")
                self.assertNotIn("channelMasterConfig", payload)
                self.assertNotIn("channel-master-header-ticker", page)
                self.assertNotIn("channel-master-title-plaque", page)
                self.assertNotIn("channel-master-maker-mark", page)
                self.assertNotIn("channel-master-footer-mark", page)


if __name__ == "__main__":
    unittest.main()
