from __future__ import annotations

import csv
import json
import tempfile
import unittest
import tkinter as tk
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from aggits_video_factory.campaigns import (
    BulkChannelMasterBuilder,
    BulkPublishCoordinator,
    Campaign,
    CampaignCandidate,
    CampaignCsvService,
    CampaignEmailCoordinator,
    CampaignEmailPackager,
    CampaignError,
    CampaignPackageService,
    CampaignPdfService,
    CampaignQrService,
    ProspectCardService,
    CampaignQualificationService,
    CampaignStore,
    CandidateResearchService,
    ResearchUnavailableError,
    canonical_youtube_channel_url,
)
from aggits_video_factory.models import ProjectType, Video
from aggits_video_factory.campaign_delivery import (
    CAMPAIGN_DELIVERY_PATH,
    CampaignWorkerTransport,
    canonical_campaign_request,
    sign_campaign_request,
)
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.youtube_api import ChannelCatalogue
from aggits_video_factory.diagnostics import close_logging
from desktop.video_jukebox_factory import Factory


def video(index: int) -> Video:
    video_id = f"bulk{index:07d}"
    return Video(
        video_id=video_id,
        title=f"Fixture Video {index}",
        display_title=f"Fixture Video {index}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        embed_url=f"https://www.youtube.com/embed/{video_id}",
        thumbnail_url="https://i.ytimg.com/vi/example/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=120,
        channel_title="Fixture Channel",
        channel_id="UCfixture",
    )


class FakeYouTube:
    def __init__(self, fail_handles: set[str] | None = None, count: int = 50) -> None:
        self.fail_handles = fail_handles or set()
        self.count = count
        self.calls: list[tuple[str, int]] = []

    def fetch_catalogue(self, channel_url: str, maximum: int = 50) -> ChannelCatalogue:
        self.calls.append((channel_url, maximum))
        if any(handle in channel_url for handle in self.fail_handles):
            raise RuntimeError("simulated YouTube failure")
        handle = channel_url.rstrip("/").split("/")[-1].lstrip("@")
        return ChannelCatalogue(
            channel_id=f"UC{handle}", channel_title=handle, channel_url=f"https://www.youtube.com/@{handle}",
            channel_thumbnail="", videos=[video(index) for index in range(1, min(self.count, maximum) + 1)],
        )


def candidate(number: int, *, approved: bool = True, handle: str | None = None) -> CampaignCandidate:
    handle = handle or f"Fixture{number}"
    return CampaignCandidate(
        candidate_number=number,
        organisation_name=f"Fixture Organisation {number}",
        location="Melbourne",
        website_url=f"https://example.com/{number}",
        youtube_channel_url=f"https://www.youtube.com/@{handle}",
        youtube_video_count=50,
        video_count_status="VERIFIED",
        youtube_ownership_status="VERIFIED",
        qualification_status="QUALIFIED",
        qualification_notes="Evergreen recurring fixture content.",
        research_confidence="HIGH",
        primary_cta_type="VISIT WEBSITE",
        primary_cta_url=f"https://example.com/{number}",
        primary_cta_url_status="VERIFIED",
        contact_url=f"https://example.com/{number}/contact",
        approved_for_build=approved,
    )


class BulkCampaignTests(unittest.TestCase):
    def test_six_tab_desktop_smoke_and_bulk_controls_at_supported_sizes(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            with patch("desktop.video_jukebox_factory.ProjectStore", return_value=store):
                app = Factory()
            app.withdraw()
            try:
                self.assertEqual([app.notebook.tab(index, "text") for index in range(app.notebook.index("end"))], ["BUSINESS", "MUSIC", "TOURISM", "BANJO", "CHANNEL MASTER", "BULK UPLOAD"])
                app.notebook.select(5)
                for width, height in ((1320, 820), (1120, 720)):
                    app.geometry(f"{width}x{height}")
                    app.update_idletasks()
                    self.assertGreater(app.bulk_upload.winfo_reqwidth(), 0)
                    self.assertGreater(app.bulk_upload.winfo_reqheight(), 0)
                self.assertEqual(tuple(app.bulk_upload.candidates["columns"]), ("approve", "number", "organisation", "videos", "ownership", "cta", "confidence", "status"))
            finally:
                app.preview_server.stop()
                app.destroy()
                close_logging(store.root)

    def test_research_boundary_is_explicitly_unavailable_without_authorised_provider(self):
        service = CandidateResearchService()
        self.assertFalse(service.available)
        with self.assertRaises(ResearchUnavailableError):
            service.find_candidates(theme="Dance", location="Melbourne", limit=20)
        class MockResearch(CandidateResearchService):
            available = True
            provider_name = "TEST FIXTURE"
            def find_candidates(self, *, theme, location, limit):
                return [candidate(1, approved=False)]
        self.assertEqual(len(MockResearch().find_candidates(theme="Dance", location="Melbourne", limit=20)), 1)

    def test_campaign_store_roundtrip_restart_and_archive_do_not_touch_projects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = CampaignStore(root)
            campaign = Campaign("Dance - Melbourne", "Dance", "Melbourne", candidates=[candidate(1)])
            store.save(campaign)
            restored = CampaignStore(root).load(campaign.campaign_id)
            self.assertEqual(restored.candidates[0].organisation_name, "Fixture Organisation 1")
            store.archive(restored)
            self.assertEqual(store.list(), [])
            self.assertEqual(len(store.list(include_archived=True)), 1)
            self.assertFalse((root / "projects").exists())

    def test_csv_template_reimports_and_unicode_commas_and_apostrophes_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = CampaignCsvService.template(root / "template.csv")
            imported = CampaignCsvService.import_file(template)
            self.assertEqual(len(imported.candidates), 1)
            campaign = Campaign("Chefs, cafés & cooks", "Cooking", "Bendigo", candidates=[candidate(1)])
            campaign.candidates[0].organisation_name = "O'Brien’s Café, Bendigo"
            destination = CampaignCsvService.export(campaign, root / "campaign.csv")
            restored = CampaignCsvService.import_file(destination)
            self.assertEqual(restored.candidates[0].organisation_name, "O'Brien’s Café, Bendigo")

    def test_csv_rejects_missing_columns_formula_injection_and_duplicate_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "missing.csv"
            missing.write_text("campaign_id,organisation_name\nabc,Example\n", encoding="utf-8")
            with self.assertRaises(CampaignError):
                CampaignCsvService.import_file(missing)
            campaign = Campaign("Fixture", "Dance", "Melbourne", candidates=[candidate(1)])
            unsafe = CampaignCsvService.export(campaign, root / "unsafe.csv")
            rows = list(csv.DictReader(unsafe.open(encoding="utf-8-sig")))
            rows[0]["organisation_name"] = "=HYPERLINK(\"bad\")"
            with unsafe.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=CampaignCsvService.FIELDS)
                writer.writeheader(); writer.writerows(rows)
            with self.assertRaises(CampaignError):
                CampaignCsvService.import_file(unsafe)
            with self.assertRaises(CampaignError):
                Campaign("Duplicate", "Dance", "Melbourne", candidates=[candidate(1), candidate(1, handle="Other")])

    def test_validation_handles_limits_urls_cta_palette_and_video_count_policy(self):
        campaign = Campaign("Twenty one", "Dance", "Melbourne", candidates=[candidate(index) for index in range(1, 22)])
        validation = CampaignCsvService.validate(campaign)
        self.assertGreaterEqual(validation.blocked, 1)
        campaign = Campaign("Counts", "Dance", "Melbourne", candidates=[])
        for index, count in enumerate((29, 30, 50, 200, 500, 501, 1000), start=1):
            item = candidate(index)
            item.youtube_video_count = count
            campaign.candidates.append(item)
        validation = CampaignCsvService.validate(campaign)
        self.assertTrue(any(issue.candidate_number == 1 and issue.severity == "WARNING" for issue in validation.issues))
        self.assertFalse(any(issue.candidate_number > 1 and issue.field == "youtube_video_count" and issue.severity == "BLOCKED" for issue in validation.issues))
        broken = candidate(1)
        broken.primary_cta_url = "javascript:alert(1)"
        broken.palette_mode = "CUSTOM"
        broken.palette_primary = "red"
        broken.palette_accent = "#FFFFFF"
        validation = CampaignCsvService.validate(Campaign("Broken", "Dance", "Melbourne", candidates=[broken]))
        self.assertGreaterEqual(validation.blocked, 1)

    def test_canonical_channel_and_qualification_are_transparent(self):
        self.assertEqual(canonical_youtube_channel_url("https://youtube.com/@Fixture/videos"), "https://www.youtube.com/@Fixture")
        with self.assertRaises(CampaignError):
            canonical_youtube_channel_url("https://example.com/@Fixture")
        low = candidate(1)
        low.youtube_video_count = 29
        status, notes = CampaignQualificationService.assess(low)
        self.assertEqual(status, "REVIEW REQUIRED")
        self.assertTrue(any("30-video" in note for note in notes))
        high = candidate(2)
        high.youtube_video_count = 1000
        status, notes = CampaignQualificationService.assess(high)
        self.assertEqual(status, "QUALIFIED")
        self.assertTrue(any("no upper ceiling" in note for note in notes))
        cta, destination, status = CampaignQualificationService.recommend_cta("Dance performance")
        self.assertEqual(cta.value, "tickets")
        self.assertEqual(destination, "")
        self.assertEqual(status, "REVIEW REQUIRED")
        cta, destination, status = CampaignQualificationService.recommend_cta("Tourism", "https://example.com/visit")
        self.assertEqual(cta.value, "plan_your_visit")
        self.assertEqual(status, "VERIFIED")

    def test_bulk_build_creates_normal_channel_master_projects_caps_50_and_keeps_metadata_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_store = ProjectStore(root)
            campaign_store = CampaignStore(root)
            campaign = Campaign("Build", "Dance", "Melbourne", candidates=[candidate(1), candidate(2)])
            campaign_store.save(campaign)
            builder = BulkChannelMasterBuilder(project_store, campaign_store, FakeYouTube(count=75))
            projects = builder.build_approved(campaign)
            self.assertEqual(len(projects), 2)
            self.assertEqual(len({item.id for item in projects}), 2)
            self.assertEqual(len({item.slug for item in projects}), 2)
            for project in projects:
                self.assertIs(project.project_type, ProjectType.CHANNEL_MASTER)
                self.assertEqual(len(project.videos), 50)
                public_files = list((project_store.project_dir(project.slug) / "site").rglob("*"))
                public_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in public_files if path.is_file() and path.suffix in {".html", ".json", ".js", ".css"})
                self.assertNotIn(campaign.campaign_id, public_text)
                self.assertNotIn("bulk_upload", public_text)
            self.assertEqual({item.extra_fields["candidate_number"] for item in projects}, {1, 2})

    def test_build_failure_is_isolated_and_resume_does_not_duplicate_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_store, campaign_store = ProjectStore(root), CampaignStore(root)
            campaign = Campaign("Partial", "Dance", "Melbourne", candidates=[candidate(1), candidate(2, handle="FailMe")])
            campaign_store.save(campaign)
            first = BulkChannelMasterBuilder(project_store, campaign_store, FakeYouTube({"FailMe"}))
            self.assertEqual(len(first.build_approved(campaign)), 1)
            first_id = campaign.candidates[0].project_uuid
            self.assertEqual(campaign.candidates[1].build_status, "FAILED")
            second = BulkChannelMasterBuilder(project_store, campaign_store, FakeYouTube())
            self.assertEqual(len(second.build_approved(campaign)), 2)
            self.assertEqual(campaign.candidates[0].project_uuid, first_id)
            self.assertEqual(len(project_store.list_projects()), 2)

    def test_twenty_approved_builds_have_distinct_normal_channel_master_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_store, campaign_store = ProjectStore(root), CampaignStore(root)
            campaign = Campaign("Twenty", "Dance", "Melbourne", candidates=[candidate(index) for index in range(1, 21)])
            campaign_store.save(campaign)
            def tiny_site(project, destination):
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "index.html").write_text(project.title, encoding="utf-8")
                return destination
            with patch("aggits_video_factory.campaigns.build_project_site", side_effect=tiny_site):
                projects = BulkChannelMasterBuilder(project_store, campaign_store, FakeYouTube(count=1)).build_approved(campaign)
            self.assertEqual(len(projects), 20)
            self.assertEqual(len({project.id for project in projects}), 20)
            self.assertEqual(len({project.slug for project in projects}), 20)
            self.assertEqual({project.project_type for project in projects}, {ProjectType.CHANNEL_MASTER})

    def test_existing_project_detection_blocks_silent_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_store, campaign_store = ProjectStore(root), CampaignStore(root)
            first = Campaign("First", "Dance", "Melbourne", candidates=[candidate(1, handle="Same")])
            campaign_store.save(first)
            BulkChannelMasterBuilder(project_store, campaign_store, FakeYouTube()).build_approved(first)
            second = Campaign("Second", "Dance", "Melbourne", candidates=[candidate(1, handle="Same")])
            result = CampaignCsvService.validate(second, project_store.list_projects())
            self.assertTrue(any("Existing Channel Master" in issue.message for issue in result.issues))

    def test_publish_requires_explicit_review_approval_and_resumes_partial_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_store, campaign_store = ProjectStore(root), CampaignStore(root)
            campaign = Campaign("Publish", "Dance", "Melbourne", candidates=[candidate(1), candidate(2)])
            campaign_store.save(campaign)
            BulkChannelMasterBuilder(project_store, campaign_store, FakeYouTube()).build_approved(campaign)
            publisher = Mock()
            coordinator = BulkPublishCoordinator(project_store, campaign_store, publisher)
            with self.assertRaises(CampaignError):
                coordinator.publish_approved(campaign)
            for item in campaign.candidates:
                item.review_status = "APPROVED TO PUBLISH"
            calls = 0
            def publish(project):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("simulated publish failure")
                project.published_url = f"https://example.test/crispy-bits/{project.slug}/"
                project.status = "published"
                project_store.save_project(project)
                return project.published_url, "a" * 40
            publisher.publish.side_effect = publish
            self.assertEqual(len(coordinator.publish_approved(campaign)), 1)
            self.assertEqual(campaign.status, "PARTIAL_FAILURE")
            publisher.publish.side_effect = lambda project: (f"https://example.test/crispy-bits/{project.slug}/", "b" * 40)
            published = coordinator.publish_approved(campaign)
            self.assertEqual(len(published), 2)
            self.assertEqual(publisher.publish.call_count, 3)

    def test_qr_pdf_package_uses_original_numbers_and_one_a4_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = CampaignStore(root)
            campaign = Campaign("Dance - Melbourne", "Dance", "Melbourne", candidates=[candidate(1), candidate(3), candidate(20)])
            for item in campaign.candidates:
                item.publish_status = "PUBLISHED"
                item.public_url = f"https://example.test/crispy-bits/{item.candidate_number}/"
                item.project_uuid = "00000000-0000-4000-8000-000000000001"
                item.project_slug = str(item.candidate_number)
            store.save(campaign)
            output = CampaignPackageService(store, verify_publications=False).generate(campaign)
            self.assertTrue((output / "qr-sheet.pdf").is_file())
            self.assertEqual(len(list((output / "qr").glob("*.png"))), 3)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([item["candidate_number"] for item in manifest["machines"]], [1, 3, 20])
            self.assertEqual(manifest["counts"]["published"], 3)
            self.assertTrue((output / "qr-codes.zip").is_file())
            self.assertTrue((output / "prospect-cards.zip").is_file())
            cards = sorted((output / "prospect-cards").glob("*.png"))
            self.assertEqual(len(cards), 3)
            self.assertTrue(cards[0].name.startswith("01-"))
            with Image.open(cards[0]) as card:
                self.assertEqual(card.size, (1080, 1350))
                self.assertEqual(card.format, "PNG")
            with Image.open(output / "qr" / next(path.name for path in (output / "qr").glob("qr-01-*.png"))) as qr:
                self.assertGreaterEqual(qr.width, 200)

    def test_internal_a4_pdf_is_one_page_for_1_17_and_20_successes(self):
        import re
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for count in (1, 17, 20):
                campaign = Campaign(f"PDF {count}", "Dance", "Melbourne", candidates=[candidate(index) for index in range(1, count + 1)])
                output = root / str(count)
                for item in campaign.candidates:
                    item.publish_status = "PUBLISHED"
                    item.public_url = f"https://example.test/crispy-bits/{item.candidate_number}/"
                CampaignQrService.generate(campaign, output)
                pdf = CampaignPdfService.generate(campaign, output)
                data = pdf.read_bytes()
                self.assertTrue(data.startswith(b"%PDF"))
                self.assertEqual(len(re.findall(rb"/Type\s*/Page(?!s)\b", data)), 1)

    def test_package_requires_exact_saved_published_project_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_store, campaign_store = ProjectStore(root), CampaignStore(root)
            campaign = Campaign("Verified", "Dance", "Melbourne", candidates=[candidate(1)])
            campaign_store.save(campaign)
            def tiny_site(project, destination):
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "index.html").write_text(project.title, encoding="utf-8")
                return destination
            with patch("aggits_video_factory.campaigns.build_project_site", side_effect=tiny_site):
                project = BulkChannelMasterBuilder(project_store, campaign_store, FakeYouTube(count=1)).build_approved(campaign)[0]
            project.status = "published"
            project.published_url = "https://example.test/crispy-bits/verified/"
            project_store.save_project(project)
            item = campaign.candidates[0]
            item.publish_status = "PUBLISHED"
            item.public_url = project.published_url
            campaign_store.save(campaign)
            self.assertTrue(CampaignPackageService(campaign_store, project_store).generate(campaign).is_dir())
            item.public_url = "https://example.test/crispy-bits/wrong/"
            with self.assertRaises(CampaignError):
                CampaignPackageService(campaign_store, project_store).generate(campaign)

    def test_email_package_has_one_operator_summary_and_idempotent_retry_without_prospect_email(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = CampaignStore(root)
            campaign = Campaign("Email Fixture", "Dance", "Melbourne", candidates=[candidate(1)])
            item = campaign.candidates[0]
            item.publish_status = "PUBLISHED"
            item.public_url = "https://example.test/crispy-bits/fixture/"
            store.save(campaign)
            package = CampaignPackageService(store, verify_publications=False).generate(campaign)
            email = CampaignEmailPackager.prepare(campaign, package)
            self.assertEqual(email.subject, "CRISPY BITS — Email Fixture — 1 MACHINES")
            self.assertEqual({path.name for path in email.attachments}, {"campaign.csv", "qr-sheet.pdf", "prospect-cards.zip", "qr-codes.zip"})
            self.assertNotIn("recipient", email.to_worker_payload())
            transport = Mock()
            transport.send.return_value = "provider-1"
            coordinator = CampaignEmailCoordinator(store, transport)
            self.assertEqual(coordinator.send(campaign), "provider-1")
            self.assertEqual(coordinator.send(campaign), "already_sent")
            transport.send.assert_called_once()

    def test_authenticated_campaign_transport_has_route_specific_hmac_and_no_recipient_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = CampaignStore(root)
            campaign = Campaign("Transport", "Dance", "Melbourne", candidates=[candidate(1)])
            campaign.candidates[0].publish_status = "PUBLISHED"
            campaign.candidates[0].public_url = "https://raggedya.github.io/aggits-video-jukebox/crispy-bits/fixture/"
            store.save(campaign)
            package = CampaignPackageService(store, verify_publications=False).generate(campaign)
            email = CampaignEmailPackager.prepare(campaign, package)
            response = Mock(ok=True, status_code=201)
            response.json.return_value = {"ok": True, "id": "campaign-provider-id"}
            with patch("aggits_video_factory.campaign_delivery.requests.post", return_value=response) as post:
                result = CampaignWorkerTransport("secret").send(email)
            self.assertEqual(result, "campaign-provider-id")
            body = post.call_args.kwargs["data"]
            payload = json.loads(body.decode("utf-8"))
            self.assertNotIn("recipient", payload)
            self.assertNotIn("subject", payload)
            self.assertEqual(payload["campaignName"], "Transport")
            self.assertEqual(len(payload["machines"]), 1)
            self.assertIn("x-crispy-signature", post.call_args.kwargs["headers"])
            canonical = canonical_campaign_request("1", "2" * 32, b"{}")
            self.assertIn(CAMPAIGN_DELIVERY_PATH.encode("utf-8"), canonical)
            self.assertEqual(len(sign_campaign_request("secret", "1", "2" * 32, b"{}")), 64)

    def test_prospect_card_is_deterministic_personal_and_contains_no_campaign_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            item = candidate(7)
            item.organisation_name = "O'Brien’s Dance & Performing Arts Academy of Melbourne"
            item.publish_status = "PUBLISHED"
            item.public_url = "https://example.test/crispy-bits/obrien-dance/"
            first = ProspectCardService.generate_candidate(item, root / "07-obrien-crispy-bits.png")
            first_bytes = first.read_bytes()
            second = ProspectCardService.generate_candidate(item, root / "07-obrien-crispy-bits-2.png")
            self.assertEqual(first_bytes, second.read_bytes())
            self.assertEqual(item.prospect_card_status, "READY")
            self.assertEqual(item.prospect_card_template_version, "prospect-card-v1")
            self.assertEqual(ProspectCardService.MESSAGE, "I MADE THIS FOR YOU.")
            self.assertEqual(ProspectCardService.INSTRUCTION, "SCAN IT. PULL THE LEVER.")
            self.assertNotIn(b"Dance - Melbourne", first_bytes)
            self.assertNotIn(b"candidate", first_bytes.lower())

    def test_prospect_card_failure_is_isolated_from_other_cards(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            campaign = Campaign("Cards", "Dance", "Melbourne", candidates=[candidate(1), candidate(2)])
            for item in campaign.candidates:
                item.publish_status = "PUBLISHED"
                item.public_url = f"https://example.test/crispy-bits/{item.candidate_number}/"
            original = ProspectCardService.generate_candidate
            def sometimes_fail(item, destination):
                if item.candidate_number == 1:
                    raise RuntimeError("simulated card failure")
                return original(item, destination)
            with patch.object(ProspectCardService, "generate_candidate", side_effect=sometimes_fail):
                cards, failures = ProspectCardService.generate_campaign(campaign, root)
            self.assertEqual(len(cards), 1)
            self.assertEqual(failures[0][0], 1)
            self.assertEqual(campaign.candidates[0].prospect_card_status, "FAILED")
            self.assertEqual(campaign.candidates[1].prospect_card_status, "READY")


if __name__ == "__main__":
    unittest.main()
