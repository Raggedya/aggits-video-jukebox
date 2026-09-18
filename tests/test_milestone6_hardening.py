from __future__ import annotations

import hashlib
import hmac
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from aggits_video_factory.delivery import (
    DeliveryError,
    canonical_delivery_request,
    delivery_intent_matches,
    mark_delivery_attempt,
    mark_delivery_failure,
    mark_delivery_result,
    request_delivery,
    sign_delivery_request,
    validate_delivery_email,
)
from aggits_video_factory.diagnostics import LOG_BACKUP_COUNT, close_logging, configure_logging
from aggits_video_factory.models import (
    BusinessConfig,
    DeliveryRecord,
    Project,
    ProjectType,
    PublicationOperation,
    Video,
)
from aggits_video_factory.publisher import (
    PublicationVerificationPending,
    PublishError,
    Publisher,
    UnpublishVerificationPending,
)
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore


REVISION_A = "a" * 40
PUBLIC_URL = "https://raggedya.github.io/aggits-video-jukebox/crispy-bits/reliable-business/"


def project_fixture() -> Project:
    return Project(
        slug="reliable-business",
        title="Reliable Business",
        ticker_text="Manual story",
        channel_url="https://youtube.com/@reliable",
        channel_id="UC-reliable",
        channel_title="Reliable Business",
        channel_thumbnail="",
        project_type=ProjectType.BUSINESS,
        business_config=BusinessConfig(shop_url="https://example.com/shop"),
        videos=[Video(
            video_id="dQw4w9WgXcQ",
            title="Video",
            display_title="Video",
            url="https://youtube.com/watch?v=dQw4w9WgXcQ",
            embed_url="https://youtube.com/embed/dQw4w9WgXcQ",
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            published_at="2026-01-01T00:00:00Z",
            duration_seconds=60,
            channel_title="Reliable Business",
        )],
    )


class Milestone6HardeningTests(unittest.TestCase):
    def test_delivery_signature_is_deterministic_and_covers_body_timestamp_nonce_recipient(self):
        secret = "local-test-secret"
        timestamp = "1700000000"
        nonce = "0123456789abcdef" * 2
        body = b'{"email":"a@example.com"}'
        expected = hmac.new(secret.encode(), canonical_delivery_request(timestamp, nonce, body), hashlib.sha256).hexdigest()
        self.assertEqual(sign_delivery_request(secret, timestamp, nonce, body), expected)
        self.assertNotEqual(expected, sign_delivery_request(secret, timestamp, nonce, b'{"email":"b@example.com"}'))
        self.assertNotEqual(expected, sign_delivery_request(secret, "1700000001", nonce, body))
        self.assertNotEqual(expected, sign_delivery_request(secret, timestamp, "f" * 32, body))
        self.assertNotIn(secret.encode(), canonical_delivery_request(timestamp, nonce, body))
        with self.assertRaisesRegex(DeliveryError, "not configured"):
            sign_delivery_request("", timestamp, nonce, body)

    def test_delivery_request_signs_exact_body_and_secret_never_enters_payload(self):
        project = project_fixture()
        project.status = "published"
        project.published_url = PUBLIC_URL
        project.publication_revision = REVISION_A
        response = Mock(ok=True, status_code=201)
        response.json.return_value = {"ok": True, "id": "email-id"}
        with patch("aggits_video_factory.delivery.requests.post", return_value=response) as post:
            request_delivery(project, "Recipient@Example.com", secret="super-secret", timestamp=1_700_000_000, nonce="c" * 32)
        body = post.call_args.kwargs["data"]
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(json.loads(body)["email"], "recipient@example.com")
        self.assertNotIn(b"super-secret", body)
        self.assertEqual(
            headers["x-crispy-signature"],
            sign_delivery_request("super-secret", headers["x-crispy-timestamp"], headers["x-crispy-nonce"], body),
        )

    def test_delivery_recipient_validation_rejects_multiple_or_injected_addresses(self):
        for value in ("", "a@example.com\nb@example.com", "a@example.com,b@example.com", "Name <a@example.com>", "not-an-email"):
            with self.subTest(value=value), self.assertRaises(DeliveryError):
                validate_delivery_email(value)
        self.assertEqual(validate_delivery_email(" A@Example.com "), "a@example.com")

    def test_delivery_history_preserves_actual_recipient_and_changed_recipient_is_distinct(self):
        project = project_fixture()
        project.status = "published"
        project.published_url = PUBLIC_URL
        project.publication_revision = REVISION_A
        mark_delivery_attempt(project, "old@example.com")
        mark_delivery_result(project, "old@example.com", {"ok": True, "sentAt": "2026-09-18T00:00:00Z"})
        self.assertTrue(delivery_intent_matches(project, "old@example.com"))
        self.assertFalse(delivery_intent_matches(project, "new@example.com"))
        self.assertEqual(project.delivery_record.recipient, "old@example.com")
        mark_delivery_attempt(project, "new@example.com")
        mark_delivery_result(project, "new@example.com", {"ok": True, "duplicate": True, "sentAt": "2026-09-18T01:00:00Z"})
        self.assertEqual(project.delivery_status, "already_delivered")
        self.assertEqual(project.delivery_record.recipient, "new@example.com")

    def test_delivery_timeout_is_unknown_not_false_failure(self):
        project = project_fixture()
        project.status = "published"
        project.published_url = PUBLIC_URL
        project.publication_revision = REVISION_A
        with patch("aggits_video_factory.delivery.requests.post", side_effect=requests.Timeout("lost response")):
            with self.assertRaises(DeliveryError) as caught:
                request_delivery(project, "owner@example.com", secret="secret")
        self.assertTrue(caught.exception.uncertain)
        mark_delivery_failure(project, "owner@example.com", caught.exception)
        self.assertEqual(project.delivery_status, "unknown")

    def test_delivery_waits_for_verified_publication_and_missing_secret_fails_safely(self):
        project = project_fixture()
        project.status = "verification_pending"
        project.published_url = PUBLIC_URL
        project.publication_revision = REVISION_A
        with self.assertRaisesRegex(DeliveryError, "verified as published"):
            request_delivery(project, "owner@example.com", secret="secret")
        project.status = "published"
        with self.assertRaisesRegex(DeliveryError, "not configured"):
            request_delivery(project, "owner@example.com", secret="")

    def test_schema3_round_trip_preserves_optional_reliability_records(self):
        project = project_fixture()
        project.delivery_record = DeliveryRecord("owner@example.com", REVISION_A, "sent", "2026-09-18T00:00:00Z")
        project.publication_operation = PublicationOperation(
            operation_id="operation-1",
            operation_type="publish",
            project_id=project.id,
            slug=project.slug,
            target_revision=REVISION_A,
            expected_url=PUBLIC_URL,
            started_at="2026-09-18T00:00:00Z",
            git_confirmed_at="2026-09-18T00:00:01Z",
            verification_status="pending",
        )
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.to_dict()["schemaVersion"], 3)
        self.assertEqual(restored.delivery_record.recipient, "owner@example.com")
        self.assertEqual(restored.publication_operation.target_revision, REVISION_A)

    def test_push_failure_is_definitive_and_does_not_claim_pending_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            project = project_fixture()
            store.save_project(project)
            build_project_site(project, store.project_dir(project.slug) / "site")
            publisher = Publisher(store)
            workspace = Path(temporary) / "workspace"
            with patch.object(publisher, "ensure_workspace", return_value=workspace), \
                    patch("aggits_video_factory.publisher._run", side_effect=PublishError("Git push failed")):
                with self.assertRaisesRegex(PublishError, "Git push failed"):
                    publisher.publish(project)
            restored = store.load_project(project.slug)
            self.assertEqual(restored.status, "publish_failed")
            self.assertEqual(restored.publication_operation.verification_status, "failed")
            self.assertIsNone(restored.publication_operation.git_confirmed_at)

    def test_publish_timeout_survives_reload_and_reconciles_without_another_push(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            project = project_fixture()
            original_id = project.id
            store.save_project(project)
            build_project_site(project, store.project_dir(project.slug) / "site")
            publisher = Publisher(store)
            workspace = Path(temporary) / "workspace"

            def fake_git(command, **_kwargs):
                if "diff" in command:
                    return "staged"
                if "rev-parse" in command:
                    return REVISION_A
                return ""

            with patch.object(publisher, "ensure_workspace", return_value=workspace), \
                    patch.object(publisher, "_wait_for_publication", side_effect=PublishError("Pages timeout")), \
                    patch("aggits_video_factory.publisher._run", side_effect=fake_git):
                with self.assertRaises(PublicationVerificationPending):
                    publisher.publish(project)
            pending = store.load_project(project.slug)
            self.assertEqual(pending.status, "verification_pending")
            self.assertEqual(pending.publication_revision, REVISION_A)
            self.assertEqual(pending.publication_operation.verification_status, "pending")
            with patch.object(publisher, "_publication_ready", return_value=True):
                self.assertEqual(publisher.reconcile(pending), "published")
            reconciled = store.load_project(project.slug)
            self.assertEqual(reconciled.status, "published")
            self.assertEqual(reconciled.id, original_id)
            self.assertEqual(reconciled.slug, "reliable-business")
            self.assertEqual(reconciled.published_url, PUBLIC_URL)

    def test_recheck_timeout_remains_pending_and_never_pushes(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            project = project_fixture()
            project.status = "verification_pending"
            project.published_url = PUBLIC_URL
            project.publication_revision = REVISION_A
            project.publication_operation = PublicationOperation(
                "operation", "publish", project.id, project.slug, REVISION_A, PUBLIC_URL,
                "2026-09-18T00:00:00Z", "2026-09-18T00:00:01Z", "pending",
            )
            store.save_project(project)
            publisher = Publisher(store)
            with patch.object(publisher, "_publication_ready", return_value=False):
                with self.assertRaises(PublicationVerificationPending):
                    publisher.reconcile(project)
            self.assertEqual(store.load_project(project.slug).status, "verification_pending")

    def test_unpublish_timeout_survives_reload_then_reconciles_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            project = project_fixture()
            project.status = "published"
            project.published_url = PUBLIC_URL
            project.publication_revision = REVISION_A
            original_id = project.id
            store.save_project(project)
            publisher = Publisher(store)
            workspace = Path(temporary) / "workspace"

            def fake_git(command, **_kwargs):
                if "diff" in command:
                    return "staged"
                if "rev-parse" in command:
                    return "b" * 40
                return ""

            with patch.object(publisher, "ensure_workspace", return_value=workspace), \
                    patch.object(publisher, "_wait_for_unpublication", side_effect=PublishError("removal timeout")), \
                    patch("aggits_video_factory.publisher._run", side_effect=fake_git):
                with self.assertRaises(UnpublishVerificationPending):
                    publisher.unpublish(project)
            pending = store.load_project(project.slug)
            self.assertEqual(pending.status, "unpublish_verification_pending")
            with patch.object(publisher, "_unpublication_ready", return_value=True):
                self.assertEqual(publisher.reconcile(pending), "unpublished")
            restored = store.load_project(project.slug)
            self.assertEqual(restored.status, "unpublished")
            self.assertEqual(restored.id, original_id)
            self.assertEqual(restored.slug, "reliable-business")
            self.assertIsNone(restored.published_url)

    def test_unpublish_push_failure_is_definitive_and_preserves_live_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            project = project_fixture()
            project.status = "published"
            project.published_url = PUBLIC_URL
            project.publication_revision = REVISION_A
            original_id = project.id
            store.save_project(project)
            publisher = Publisher(store)
            with patch.object(publisher, "ensure_workspace", return_value=Path(temporary) / "workspace"), \
                    patch("aggits_video_factory.publisher._run", side_effect=PublishError("remote removal failed")):
                with self.assertRaisesRegex(PublishError, "remote removal failed"):
                    publisher.unpublish(project)
            restored = store.load_project(project.slug)
            self.assertEqual(restored.status, "unpublish_failed")
            self.assertEqual(restored.id, original_id)
            self.assertEqual(restored.published_url, PUBLIC_URL)
            self.assertEqual(restored.publication_revision, REVISION_A)

    def test_corrupt_project_is_visible_as_diagnostic_and_source_is_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary) / "store")
            path = store.projects_dir / "broken" / "project.json"
            path.parent.mkdir(parents=True)
            content = b'{"broken": '
            path.write_bytes(content)
            self.assertEqual(store.list_projects(), [])
            self.assertEqual(len(store.last_load_errors), 1)
            self.assertEqual(store.last_load_errors[0].path, path)
            self.assertEqual(path.read_bytes(), content)

    def test_persistent_log_rotates_and_redacts_sensitive_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logger = configure_logging(root)
            logger.warning("secret=topsecret authorization=Bearer-credential signature=abcdef")
            for _ in range(1200):
                logger.info("bounded diagnostic %s", "x" * 1000)
            close_logging(root)
            files = list((root / "logs").glob("crispy-bits-desktop.log*"))
            self.assertLessEqual(len(files), LOG_BACKUP_COUNT + 1)
            combined = "".join(path.read_text(encoding="utf-8") for path in files)
            self.assertNotIn("topsecret", combined)
            self.assertNotIn("Bearer-credential", combined)
            self.assertIn("[REDACTED]", combined)


if __name__ == "__main__":
    unittest.main()
