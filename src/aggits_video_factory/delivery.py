from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any
from urllib.parse import urlparse

import requests

from .config import DELIVERY_ENDPOINT
from .diagnostics import get_logger
from .models import DeliveryRecord, Project, ProjectType, utc_now


DELIVERY_PATH = "/api/deliveries"
EMAIL_PATTERN = re.compile(r"^[^\s@<>,;:\"()\[\]\\]+@[^\s@<>,;:\"()\[\]\\]+\.[^\s@<>,;:\"()\[\]\\]+$")


class DeliveryError(RuntimeError):
    def __init__(self, message: str, *, code: str = "delivery_failed", uncertain: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain


def validate_delivery_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not email or len(email) > 254 or "\r" in email or "\n" in email or not EMAIL_PATTERN.fullmatch(email):
        raise DeliveryError("Enter a valid single Delivery Email before sending.", code="invalid_recipient")
    return email


def canonical_delivery_request(timestamp: str, nonce: str, body: bytes) -> bytes:
    return f"{timestamp}\n{nonce}\nPOST\n{DELIVERY_PATH}\n".encode("utf-8") + body


def sign_delivery_request(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    if not secret:
        raise DeliveryError(
            "Delivery authentication is not configured. Provision the desktop delivery secret and try again.",
            code="missing_delivery_secret",
        )
    return hmac.new(secret.encode("utf-8"), canonical_delivery_request(timestamp, nonce, body), hashlib.sha256).hexdigest()


def delivery_intent_matches(project: Project, recipient: str) -> bool:
    record = project.delivery_record
    return bool(
        record
        and record.recipient == validate_delivery_email(recipient)
        and record.revision == (project.publication_revision or "")
        and record.status in {"sent", "already_delivered"}
    )


def mark_delivery_attempt(project: Project, recipient: str) -> DeliveryRecord:
    normalized = validate_delivery_email(recipient)
    project.delivery_status = "attempting"
    project.delivery_record = DeliveryRecord(
        recipient=normalized,
        revision=project.publication_revision or "",
        status="attempting",
        last_attempt_at=utc_now(),
    )
    return project.delivery_record


def mark_delivery_result(project: Project, recipient: str, result: dict[str, Any]) -> None:
    normalized = validate_delivery_email(recipient)
    status = "already_delivered" if result.get("duplicate") else "sent"
    now = utc_now()
    project.delivery_status = status
    project.delivery_record = DeliveryRecord(
        recipient=normalized,
        revision=project.publication_revision or "",
        status=status,
        sent_at=str(result.get("sentAt") or now),
        last_attempt_at=now,
    )


def mark_delivery_failure(project: Project, recipient: str, error: DeliveryError) -> None:
    normalized = validate_delivery_email(recipient)
    status = "unknown" if error.uncertain else "failed"
    project.delivery_status = status
    project.delivery_record = DeliveryRecord(
        recipient=normalized,
        revision=project.publication_revision or "",
        status=status,
        last_attempt_at=utc_now(),
        error_summary=str(error),
    )


def request_delivery(
    project: Project,
    email: str,
    timeout: float = 30.0,
    *,
    secret: str | None = None,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    if project.project_type not in {ProjectType.BUSINESS, ProjectType.MUSIC, ProjectType.TOURISM, ProjectType.BANJO}:
        raise DeliveryError(f"Unsupported project type: {project.project_type!r}.", code="unsupported_project_type")
    if project.status != "published" or not project.published_url or not project.publication_revision:
        raise DeliveryError("The jukebox must be verified as published before its email can be sent.", code="publication_not_verified")
    recipient = validate_delivery_email(email)
    payload = {
        "slug": project.slug,
        "title": project.title,
        "email": recipient,
        "publicUrl": project.published_url,
        "qrUrl": f"{project.published_url.rstrip('/')}/qr-card.png",
        "revision": project.publication_revision,
        "brand": "CRISPY BITS",
        "projectType": project.project_type.value,
        "productName": {
            ProjectType.BUSINESS: "CRISPY BITS BUSINESS",
            ProjectType.MUSIC: "CRISPY BITS MUSIC",
            ProjectType.TOURISM: "CRISPY BITS TOURISM",
            ProjectType.BANJO: "BANJO'S WORLD OF CARS",
        }[project.project_type],
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    stamp = str(int(time.time() if timestamp is None else timestamp))
    request_nonce = nonce or secrets.token_hex(16)
    signature = sign_delivery_request(str(secret or ""), stamp, request_nonce, body)
    if urlparse(DELIVERY_ENDPOINT).path != DELIVERY_PATH:
        raise DeliveryError("The configured delivery endpoint is invalid.", code="invalid_delivery_endpoint")
    headers = {
        "content-type": "application/json",
        "x-crispy-timestamp": stamp,
        "x-crispy-nonce": request_nonce,
        "x-crispy-signature": signature,
    }
    logger = get_logger()
    logger.info("Delivery request slug=%s revision=%s recipient=%s", project.slug, project.publication_revision, _redact_email(recipient))
    try:
        response = requests.post(DELIVERY_ENDPOINT, data=body, headers=headers, timeout=timeout)
    except requests.RequestException as error:
        logger.warning("Delivery response unknown slug=%s error=%s", project.slug, type(error).__name__)
        raise DeliveryError(
            "The delivery service response was not received. Delivery status is unknown; Retry Email is safe.",
            code="delivery_response_unknown",
            uncertain=True,
        ) from error
    try:
        response_body = response.json()
    except ValueError:
        response_body = {}
    if response.status_code == 401:
        logger.warning("Delivery authentication failed slug=%s", project.slug)
        raise DeliveryError("Delivery authentication failed.", code="delivery_authentication_failed")
    if response.status_code == 409 and isinstance(response_body, dict) and response_body.get("error") == "delivery_in_progress":
        raise DeliveryError(
            "Delivery is still being confirmed. Retry Email is safe if the status does not update.",
            code="delivery_in_progress",
            uncertain=True,
        )
    if response.status_code == 429:
        raise DeliveryError("Email delivery is temporarily rate limited. Retry later.", code="delivery_rate_limited")
    if not response.ok:
        message = str(response_body.get("error") or f"HTTP {response.status_code}") if isinstance(response_body, dict) else f"HTTP {response.status_code}"
        logger.warning("Delivery failed slug=%s status=%s error=%s", project.slug, response.status_code, message)
        raise DeliveryError(f"The delivery service did not send the email ({message}).", code=message)
    result = response_body if isinstance(response_body, dict) else {"ok": True}
    logger.info("Delivery confirmed slug=%s duplicate=%s", project.slug, bool(result.get("duplicate")))
    return result


def _redact_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "[invalid]"
