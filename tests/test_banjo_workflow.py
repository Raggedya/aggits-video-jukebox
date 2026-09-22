from __future__ import annotations

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from aggits_video_factory.banjo import (
    BANJO_CHARACTER_SHA256,
    BANJO_TITLE,
    BanjoSponsorScheduler,
    BanjoValidationError,
    import_sponsor_logo,
    import_sponsor_mp4,
    materialize_banjo_config,
    validate_sponsor_logo,
    validate_sponsor_mp4,
    verify_banjo_character,
)
from aggits_video_factory.config import (
    BANJO_SUBMISSION_ENDPOINT,
    MAX_BANJO_TICKER_LENGTH,
    MAX_BANJO_VIDEOS,
    MAX_VIDEOS,
    resource_path,
    video_limit_for_project_type,
)
from aggits_video_factory.desktop_forms import (
    FormValidationError,
    ProjectFormValues,
    project_to_form_values,
    validate_project_form,
    youtube_urls_for_project_review,
)
from aggits_video_factory.delivery import request_delivery
from aggits_video_factory.models import (
    BanjoChoice,
    BanjoConfig,
    BusinessConfig,
    Project,
    ProjectType,
    ProjectValidationError,
    SponsorConfig,
    SponsorCreative,
    Video,
)
from aggits_video_factory.migrations import CURRENT_PROJECT_SCHEMA_VERSION
from aggits_video_factory.publisher import Publisher, _validate_project_type
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.video_editor import VideoSelectionSession
from desktop.video_jukebox_factory import ProjectForm


ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "static" / "video-machine.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
DESKTOP = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")


def video(index: int) -> Video:
    video_id = f"banjo{index:06d}"[:11]
    return Video(
        video_id=video_id,
        title=f"Car story {index}",
        display_title=f"Car story {index}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        embed_url=f"https://www.youtube.com/embed/{video_id}",
        thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=120,
        channel_title="Banjo Fixture",
    )


def project(videos: list[Video] | None = None, config: BanjoConfig | None = None, ticker_text: str = "") -> Project:
    return Project(
        slug="banjos-world-of-cars",
        title=BANJO_TITLE,
        ticker_text=ticker_text,
        channel_url="",
        channel_id="",
        channel_title="Banjo Fixture",
        channel_thumbnail="",
        project_type=ProjectType.BANJO,
        videos=videos or [video(1)],
        banjo_config=config or BanjoConfig(),
    )


class BanjoModelTests(unittest.TestCase):
    def test_fourth_type_and_type_aware_limits(self):
        self.assertEqual(ProjectType.BANJO.value, "banjo")
        self.assertEqual(video_limit_for_project_type(ProjectType.BANJO), 40)
        self.assertEqual(MAX_BANJO_VIDEOS, 40)
        for kind in (ProjectType.BUSINESS, ProjectType.MUSIC, ProjectType.TOURISM):
            self.assertEqual(video_limit_for_project_type(kind), MAX_VIDEOS)

    def test_banjo_round_trip_preserves_identity_awards_and_sponsor(self):
        creative = SponsorCreative(asset_path="assets/sponsor-fixture.mp4", filename="fixture.mp4", size_bytes=9)
        original = project(config=BanjoConfig(
            banjos_choice=[BanjoChoice(video(1).video_id, "1978 HOLDEN HZ GTS", True)],
            sponsor=SponsorConfig(True, "TEST SPONSOR", "https://example.com/sponsor", [creative]),
        ))
        restored = Project.from_dict(original.to_dict())
        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.slug, original.slug)
        self.assertEqual(restored.banjo_config.to_dict(), original.banjo_config.to_dict())
        self.assertEqual(restored.to_dict()["schemaVersion"], CURRENT_PROJECT_SCHEMA_VERSION)

    def test_banjo_enforces_exact_title_and_cross_type_isolation(self):
        with self.assertRaises(ProjectValidationError):
            Project.from_dict({**project().to_dict(), "title": "BANJO'S CARS"})
        with self.assertRaises(ProjectValidationError):
            project().from_dict({**project().to_dict(), "business_config": BusinessConfig().to_dict()})

    def test_banjo_accepts_40_and_blocks_41_without_changing_other_limits(self):
        self.assertEqual(len(project([video(index) for index in range(40)]).videos), 40)
        with self.assertRaises(ProjectValidationError):
            project([video(index) for index in range(41)])

    def test_maximum_four_awards_and_four_creatives_are_enforced(self):
        with self.assertRaises(ProjectValidationError):
            BanjoConfig(banjos_choice=[BanjoChoice(video(index).video_id) for index in range(5)])
        with self.assertRaises(ProjectValidationError):
            SponsorConfig(creatives=[SponsorCreative(asset_path=f"assets/sponsor-{index}.mp4") for index in range(5)])

    def test_form_accepts_40_urls_and_sponsor_fields(self):
        urls = [item.url for item in [video(index) for index in range(40)]]
        values = validate_project_form(ProjectFormValues(
            manual_video_urls=urls,
            banjo_choice_urls=[urls[0]],
            banjo_choice_titles=["Award car"],
            banjo_choice_active=[True],
            sponsor_active=True,
            sponsor_title="TEST SPONSOR",
            sponsor_url="https://example.com/sponsor",
        ), ProjectType.BANJO)
        self.assertEqual(values.title, BANJO_TITLE)
        self.assertEqual(len(values.manual_video_urls), 40)
        self.assertEqual(values.sponsor_title, "TEST SPONSOR")

    def test_banjo_ticker_accepts_1500_characters_and_rejects_1501(self):
        accepted = validate_project_form(ProjectFormValues(
            manual_video_urls=[video(1).url], story_text="T" * MAX_BANJO_TICKER_LENGTH,
        ), ProjectType.BANJO)
        self.assertEqual(len(accepted.story_text), 1500)
        with self.assertRaises(FormValidationError):
            validate_project_form(ProjectFormValues(
                manual_video_urls=[video(1).url], story_text="T" * (MAX_BANJO_TICKER_LENGTH + 1),
            ), ProjectType.BANJO)

    def test_one_or_many_choice_urls_are_automatically_added_to_youtube_review(self):
        choices = [video(index) for index in range(1, 5)]
        one = validate_project_form(ProjectFormValues(
            banjo_choice_urls=["", choices[0].url, "", ""],
            banjo_choice_titles=["", "First award", "", ""],
            banjo_choice_active=[False, True, False, False],
        ), ProjectType.BANJO)
        self.assertEqual(one.manual_video_urls, [])
        self.assertEqual(one.banjo_choice_urls, [choices[0].url])
        self.assertEqual(youtube_urls_for_project_review(one, ProjectType.BANJO), [choices[0].url])

        many = validate_project_form(ProjectFormValues(
            manual_video_urls=[video(0).url],
            banjo_choice_urls=[item.url for item in choices],
            banjo_choice_titles=[f"Award {index}" for index in range(4)],
            banjo_choice_active=[True, True, True, True],
        ), ProjectType.BANJO)
        review_urls = youtube_urls_for_project_review(many, ProjectType.BANJO)
        self.assertEqual(review_urls, [video(0).url, *[item.url for item in choices]])
        with tempfile.TemporaryDirectory() as temporary:
            config = materialize_banjo_config(
                many,
                [video(0), *choices],
                {video(0).video_id, *[item.video_id for item in choices]},
                Path(temporary),
            )
        self.assertEqual([item.video_id for item in config.banjos_choice], [item.video_id for item in choices])

    def test_choice_videos_share_the_40_video_limit_without_needing_duplicate_entry(self):
        manual = [video(index).url for index in range(39)]
        accepted = validate_project_form(ProjectFormValues(
            manual_video_urls=manual,
            banjo_choice_urls=[video(38).url, video(39).url],
            banjo_choice_active=[True, True],
        ), ProjectType.BANJO)
        self.assertEqual(len(youtube_urls_for_project_review(accepted, ProjectType.BANJO)), 40)
        with self.assertRaises(FormValidationError):
            validate_project_form(ProjectFormValues(
                manual_video_urls=manual,
                banjo_choice_urls=[video(39).url, video(40).url],
                banjo_choice_active=[True, True],
            ), ProjectType.BANJO)

    def test_awards_are_metadata_and_exclusion_safely_deactivates_them(self):
        chosen = video(1)
        item = project([chosen, video(2)], BanjoConfig(banjos_choice=[BanjoChoice(chosen.video_id, "Award car", True)]))
        session = VideoSelectionSession(item)
        session.set_included(chosen.video_id, False)
        revised = session.revised_project()
        self.assertEqual(len(revised.videos), 2)
        self.assertFalse(revised.banjo_config.banjos_choice[0].active)
        self.assertEqual(revised.banjo_config.banjos_choice[0].video_id, chosen.video_id)


class BanjoSponsorTests(unittest.TestCase):
    def creative(self, index: int, active: bool = True) -> SponsorCreative:
        return SponsorCreative(asset_path=f"assets/sponsor-{index}.mp4", filename=f"promo-{index}.mp4", active=active)

    def test_scheduler_requires_five_normals_never_back_to_back_and_rotates(self):
        creatives = [self.creative(index) for index in range(4)]
        scheduler = BanjoSponsorScheduler()
        for _ in range(4):
            scheduler.record_normal_landing()
            self.assertIsNone(scheduler.next_sponsor(creatives, True))
        scheduler.record_normal_landing()
        first = scheduler.next_sponsor(creatives, True)
        self.assertEqual(first.asset_path, creatives[0].asset_path)
        self.assertIsNone(scheduler.next_sponsor(creatives, True))
        seen = [first.asset_path]
        for _ in range(4):
            for _ in range(5):
                scheduler.record_normal_landing()
            seen.append(scheduler.next_sponsor(creatives, True).asset_path)
        self.assertEqual(seen, [item.asset_path for item in creatives] + [creatives[0].asset_path])

    def test_scheduler_uses_only_active_creatives(self):
        creatives = [self.creative(1), self.creative(2, False), self.creative(3), self.creative(4, False)]
        scheduler = BanjoSponsorScheduler(normal_discoveries=5)
        self.assertEqual(scheduler.next_sponsor(creatives, True).asset_path, creatives[0].asset_path)
        for _ in range(5):
            scheduler.record_normal_landing()
        self.assertEqual(scheduler.next_sponsor(creatives, True).asset_path, creatives[2].asset_path)

    def test_mp4_validation_and_project_controlled_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "outside.mp4"
            source.write_bytes(b"fixture mp4")
            destination = root / "project"
            creative = import_sponsor_mp4(source, destination)
            source.unlink()
            controlled = destination / creative.asset_path
            self.assertTrue(controlled.is_file())
            self.assertTrue(creative.asset_path.startswith("assets/sponsor-"))
            self.assertNotIn(str(root), creative.asset_path)
            self.assertEqual(validate_sponsor_mp4(controlled), len(b"fixture mp4"))
            bad = root / "bad.mov"
            bad.write_bytes(b"bad")
            with self.assertRaises(BanjoValidationError):
                validate_sponsor_mp4(bad)
            oversized = root / "large.mp4"
            with oversized.open("wb") as stream:
                stream.seek(10 * 1024 * 1024)
                stream.write(b"x")
            with self.assertRaises(BanjoValidationError):
                validate_sponsor_mp4(oversized)

    def test_sponsor_logo_formats_size_and_project_controlled_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "project"
            for extension, image_format in (("png", "PNG"), ("jpg", "JPEG"), ("jpeg", "JPEG"), ("webp", "WEBP")):
                source = root / f"outside.{extension}"
                Image.new("RGB", (120, 40), "red").save(source, format=image_format)
                self.assertGreater(validate_sponsor_logo(source), 0)
                relative, original, size = import_sponsor_logo(source, destination)
                source.unlink()
                self.assertTrue((destination / relative).is_file())
                self.assertTrue(relative.startswith("assets/sponsor-logo-"))
                self.assertEqual(original, f"outside.{extension}")
                self.assertGreater(size, 0)
            unsupported = root / "logo.gif"
            Image.new("RGB", (10, 10)).save(unsupported, format="GIF")
            with self.assertRaises(BanjoValidationError):
                validate_sponsor_logo(unsupported)
            oversized = root / "huge.png"
            oversized.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
            with self.assertRaises(BanjoValidationError):
                validate_sponsor_logo(oversized)

    def test_materialized_sponsor_logo_survives_source_removal_and_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "external-logo.png"
            Image.new("RGBA", (160, 50), (255, 255, 255, 0)).save(source, "PNG")
            values = validate_project_form(ProjectFormValues(
                manual_video_urls=[video(1).url], sponsor_active=True, sponsor_title="TEST SPONSOR",
                sponsor_url="https://example.com/sponsor", sponsor_logo_path=str(source),
            ), ProjectType.BANJO)
            config = materialize_banjo_config(values, [video(1)], {video(1).video_id}, root / "project")
            source.unlink()
            controlled = root / "project" / config.sponsor.logo_asset_path
            self.assertTrue(controlled.is_file())
            restored = BanjoConfig.from_dict(config.to_dict())
            self.assertEqual(restored.sponsor.logo_asset_path, config.sponsor.logo_asset_path)
            self.assertNotIn(str(root), json.dumps(restored.to_dict()))


class BanjoPublicOutputTests(unittest.TestCase):
    def test_canonical_character_hash_and_transparency_are_protected(self):
        asset = resource_path("static/banjo/banjo-approved-header.png")
        verify_banjo_character(asset)
        self.assertEqual(__import__("hashlib").sha256(asset.read_bytes()).hexdigest(), BANJO_CHARACTER_SHA256)
        with Image.open(asset) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getextrema()[3], (0, 255))

    def test_banjo_build_contains_scoped_identity_and_no_local_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary) / "project"
            source_asset = project_dir / "assets" / "sponsor-fixture.mp4"
            source_asset.parent.mkdir(parents=True)
            source_asset.write_bytes(b"fixture mp4")
            creative = SponsorCreative(asset_path="assets/sponsor-fixture.mp4", filename="operator-file.mp4", active=True, size_bytes=11)
            item = project(config=BanjoConfig(
                banjos_choice=[BanjoChoice(video(1).video_id, "Award car", True)],
                sponsor=SponsorConfig(True, "TEST SPONSOR", "https://example.com/sponsor", [creative]),
            ))
            output = project_dir / "site"
            build_project_site(item, output)
            page = (output / "index.html").read_text(encoding="utf-8")
            payload_text = (output / "machine.json").read_text(encoding="utf-8")
            payload = json.loads(payload_text)
            self.assertIn("banjo-header-character", page)
            self.assertIn("banjo-choice-overlay", page)
            self.assertNotIn("CARS • PEOPLE • STORIES • GOOD TIMES", page)
            self.assertEqual(payload["title"], BANJO_TITLE)
            self.assertEqual(payload["banjoConfig"]["sponsor"]["url"], "https://example.com/sponsor")
            self.assertTrue((output / "assets" / "banjo-sponsor" / f"sponsor-{creative.creative_id}.mp4").is_file())
            self.assertNotIn("C:\\", payload_text)
            self.assertNotIn(str(project_dir), payload_text)

    def test_banjo_top_controls_are_omitted_but_business_controls_remain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            banjo_output = root / "banjo"
            build_project_site(project(), banjo_output)
            banjo_page = (banjo_output / "index.html").read_text(encoding="utf-8")
            self.assertNotIn('data-action="home"', banjo_page)
            self.assertNotIn('data-action="sound"', banjo_page)

            business = Project(
                slug="business-controls", title="TEST BUSINESS", ticker_text="Story", channel_url="",
                channel_id="", channel_title="Fixture", channel_thumbnail="", project_type=ProjectType.BUSINESS,
                videos=[video(1)], business_config=BusinessConfig(),
            )
            business_output = root / "business"
            build_project_site(business, business_output)
            business_page = (business_output / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-action="home"', business_page)
            self.assertIn('data-action="sound"', business_page)

    def test_banjo_header_ticker_is_plain_escaped_continuous_and_header_has_no_sponsor(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            item = project(ticker_text="FIRST <b>LINE</b>\nSECOND LINE")
            build_project_site(item, output)
            page = (output / "index.html").read_text(encoding="utf-8")
            payload = json.loads((output / "machine.json").read_text(encoding="utf-8"))
            self.assertIn("FIRST &lt;b&gt;LINE&lt;/b&gt; • SECOND LINE", page)
            self.assertNotIn("FIRST <b>LINE</b>", page)
            self.assertEqual(payload["banjoConfig"]["tickerText"], "FIRST <b>LINE</b> • SECOND LINE")
            self.assertIn("const BANJO_TICKER_DELAY = 10000", SCRIPT)
            self.assertEqual(SCRIPT.count("startBanjoHeaderTicker();"), 1)
            self.assertIn("banjoHeaderTicker", CSS)
            self.assertIn("translateX(-100%)", CSS)
            self.assertNotIn("sponsor_header_", SCRIPT)

            empty_output = output / "empty"
            build_project_site(project(ticker_text=""), empty_output)
            empty_page = (empty_output / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("data-banjo-header-ticker", empty_page)

    def test_dedicated_sponsor_area_logo_and_stable_show_banjo_button(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_dir = Path(temporary) / "project"
            logo = project_dir / "assets" / "sponsor-logo-fixture.png"
            logo.parent.mkdir(parents=True)
            Image.new("RGBA", (180, 60), (255, 0, 0, 128)).save(logo, "PNG")
            sponsor = SponsorConfig(
                active=True, title="TEST SPONSOR", url="https://example.com/sponsor", creatives=[],
                logo_asset_path="assets/sponsor-logo-fixture.png", logo_filename="fixture.png",
                logo_size_bytes=logo.stat().st_size,
            )
            output = project_dir / "site"
            build_project_site(project(config=BanjoConfig(sponsor=sponsor)), output)
            page = (output / "index.html").read_text(encoding="utf-8")
            payload_text = (output / "machine.json").read_text(encoding="utf-8")
            self.assertIn(">VISIT OUR SPONSOR</a>", page)
            self.assertEqual(page.count('href="https://example.com/sponsor"'), 2)
            self.assertIn("assets/banjo-sponsor/sponsor-logo-fixture.png", page)
            self.assertIn("object-fit:contain", CSS)
            self.assertNotIn(str(project_dir), payload_text)
            self.assertNotIn("VISIT SPONSOR", SCRIPT)
            self.assertIn("if (activeProjectType === 'banjo') {\n      openBanjoSubmission();", SCRIPT)

            inactive_output = project_dir / "inactive"
            build_project_site(project(config=BanjoConfig(sponsor=SponsorConfig(
                active=False, title="TEST SPONSOR", url="https://example.com/sponsor",
                logo_asset_path="assets/sponsor-logo-fixture.png", logo_filename="fixture.png",
                logo_size_bytes=logo.stat().st_size,
            ))), inactive_output)
            inactive_page = (inactive_output / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("VISIT OUR SPONSOR", inactive_page)

    def test_show_banjo_modal_is_banjo_only_and_contains_exact_public_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            build_project_site(project(), output)
            page = (output / "index.html").read_text(encoding="utf-8")
            script = (output / "assets" / "video-machine.js").read_text(encoding="utf-8")
            payload_text = (output / "machine.json").read_text(encoding="utf-8")
            payload = json.loads(payload_text)
            for value in (
                "SHOW BANJO", "SHOW BANJO YOUR CAR", "FIRST NAME", "EMAIL ADDRESS",
                "YOUTUBE VIDEO LINK", "SEND TO BANJO",
                "We'll only use your email to contact you about your submission.",
                "THANKS — BANJO'S GOT IT.", "If Banjo adds your car, we'll let you know.",
            ):
                self.assertIn(value, page)
            self.assertNotIn(">CONTEXT<", page)
            self.assertNotIn("'CONTEXT'", script)
            self.assertEqual(payload["banjoConfig"]["submission"], {
                "endpoint": BANJO_SUBMISSION_ENDPOINT,
                "projectSlug": "banjos-world-of-cars",
                "projectType": "banjo",
            })
            public_files = page + script + payload_text
            self.assertNotIn("andrewharris501@gmail.com", public_files)
            self.assertNotIn("DELIVERY_HMAC_SECRET", public_files)
            self.assertNotIn('recipient:', script)
            self.assertIn("if (activeProjectType === 'banjo')", script)
            self.assertNotIn("VISIT SPONSOR", script)
            self.assertIn("sponsor_button_click", script)
            self.assertIn("show_banjo_submit_success", script)
            self.assertIn("localPreview", script)

    def test_show_banjo_modal_accessibility_and_failure_preservation_hooks(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            build_project_site(project(), output)
            page = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn('role="dialog"', page)
            self.assertIn('aria-modal="true"', page)
            self.assertIn('aria-labelledby="banjo-submission-title"', page)
            self.assertIn('data-banjo-submission-close', page)
            self.assertEqual(page.count('name="first_name"'), 1)
            self.assertEqual(page.count('name="email"'), 1)
            self.assertEqual(page.count('name="youtube_url"'), 1)
            self.assertIn("event.key === 'Escape'", SCRIPT)
            self.assertIn("banjoSubmissionReturnFocus", SCRIPT)
            open_block = SCRIPT.split("  function openBanjoSubmission() {", 1)[1].split("  function closeBanjoSubmission()", 1)[0]
            self.assertIn("banjoSubmissionSend.disabled = false", open_block)
            submit_block = SCRIPT.split("  async function submitBanjoForm(event) {", 1)[1]
            failure_block = submit_block.split("  } catch (error) {", 1)[1].split("  } finally {", 1)[0]
            self.assertNotIn("reset()", failure_block)
            self.assertIn("banjoSubmissionFailureMessage", failure_block)

    def test_business_output_has_no_banjo_markup_or_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            item = Project(
                slug="business", title="TEST BUSINESS", ticker_text="Bio", channel_url="", channel_id="",
                channel_title="Fixture", channel_thumbnail="", project_type=ProjectType.BUSINESS,
                videos=[video(1)], business_config=BusinessConfig(),
            )
            output = Path(temporary)
            build_project_site(item, output)
            page = (output / "index.html").read_text(encoding="utf-8")
            payload = json.loads((output / "machine.json").read_text(encoding="utf-8"))
            self.assertNotIn("banjo-header-character", page)
            self.assertNotIn("banjo-choice-overlay", page)
            self.assertNotIn("banjo-submission-modal", page)
            self.assertNotIn("banjoConfig", payload)
            self.assertNotIn("isBanjosChoice", payload["videos"][0])

    def test_runtime_has_required_hooks_without_changing_spin_engine_files(self):
        for expected in (
            "normalDiscoveries", "nextCreativeIndex", "lastWasSponsor", "sessionStorage",
            "sponsor_button_impression", "sponsor_button_click", "sponsor_logo_impression", "sponsor_logo_click",
            "sponsor_play_start", "sponsor_25_percent", "sponsor_50_percent", "sponsor_75_percent", "sponsor_complete",
            "banjos_choice_award_display", "banjos_choice_audio_request",
        ):
            self.assertIn(expected, SCRIPT)
        self.assertNotIn("sponsor_header_impression", SCRIPT)
        self.assertNotIn("sponsor_header_click", SCRIPT)
        self.assertIn('[data-project-type="banjo"]', CSS)
        self.assertIn("const sponsorWinner = activeProjectType === 'banjo' ? nextSponsorPresentation() : null;", SCRIPT)
        self.assertNotIn("banjo", (ROOT / "static" / "single-reel-engine.js").read_text(encoding="utf-8").lower())
        self.assertNotIn("banjo", (ROOT / "static" / "machine-mechanics-core.js").read_text(encoding="utf-8").lower())

    def test_banjos_choice_is_post_landing_sound_aware_and_non_disruptive(self):
        spin_block = SCRIPT.split("  async function spin() {", 1)[1].split("  function resetLever", 1)[0]
        award_block = SCRIPT.split("  function showBanjoChoiceAward(video) {", 1)[1].split("  function cancelPendingReveal", 1)[0]
        self.assertLess(spin_block.index("current = winner;"), spin_block.index("showBanjoChoiceAward(winner);"))
        self.assertIn("if (soundEnabled)", award_block)
        self.assertIn("banjos_choice_audio_request", award_block)
        self.assertIn("banjoChoiceOverlay.classList.remove('is-visible')", award_block)
        self.assertIn("2200", award_block)
        self.assertNotIn("spin()", award_block)

    def test_desktop_publisher_and_store_accept_banjo(self):
        self.assertIn("ProjectType.BANJO", DESKTOP)
        _validate_project_type(project())
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            original = project()
            store.save_project(original)
            restored = store.load_project(original.slug)
            self.assertEqual(restored.id, original.id)
            self.assertEqual(restored.project_type, ProjectType.BANJO)
            self.assertEqual(project_to_form_values(restored).title, BANJO_TITLE)

    def test_banjo_delivery_reuses_authenticated_shared_contract(self):
        item = project()
        item.status = "published"
        item.published_url = "https://example.com/crispy-bits/banjos-world-of-cars/"
        item.publication_revision = "a" * 40
        response = Mock(status_code=201, ok=True)
        response.json.return_value = {"ok": True}
        with patch("aggits_video_factory.delivery.requests.post", return_value=response) as post:
            request_delivery(item, "owner@example.com", secret="test-secret", timestamp=1, nonce="b" * 32)
        payload = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(payload["projectType"], "banjo")
        self.assertEqual(payload["productName"], BANJO_TITLE)
        self.assertEqual(payload["email"], "owner@example.com")

    def test_banjo_publish_unpublish_republish_reuses_stable_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            item = project()
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
            with patch.object(publisher, "ensure_workspace", return_value=workspace), \
                    patch.object(publisher, "_wait_for_publication"), \
                    patch.object(publisher, "_wait_for_unpublication"), \
                    patch("aggits_video_factory.publisher._run", side_effect=fake_git):
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
            library = json.loads((workspace / "public" / "crispy-bits" / "library.json").read_text(encoding="utf-8"))
            self.assertEqual(library[0]["projectType"], "banjo")

    def test_banjo_desktop_form_exposes_required_controls_at_supported_sizes(self):
        root = tk.Tk()
        root.withdraw()
        try:
            form = ProjectForm(root, ProjectType.BANJO, lambda: None, lambda: None)
            form.pack(fill="both", expand=True)
            self.assertEqual(len(form.manual_vars), 40)
            self.assertEqual(len(form.banjo_choice_url_vars), 4)
            self.assertEqual(len(form.sponsor_path_vars), 4)
            for field in ("channel_url", "story_text", "banjo_choices", "sponsor_title", "sponsor_url", "sponsor_logo", "sponsor_creatives"):
                self.assertIn(field, form.field_widgets)
            self.assertNotIn("cta_type", form.field_widgets)
            self.assertEqual(form.ticker_limit, 1500)
            for width, height in ((1320, 820), (1120, 720)):
                root.geometry(f"{width}x{height}")
                root.update_idletasks()
                self.assertGreater(form.winfo_reqheight(), 0)
                self.assertGreater(form.winfo_reqwidth(), 0)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
    validate_sponsor_logo,
