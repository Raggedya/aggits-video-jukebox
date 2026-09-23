from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlparse

import requests

from .campaigns import CampaignEmail
from .config import CAMPAIGN_DELIVERY_ENDPOINT


CAMPAIGN_DELIVERY_PATH = "/api/campaign-deliveries"


class CampaignDeliveryError(RuntimeError):
    pass


def canonical_campaign_request(timestamp: str, nonce: str, body: bytes) -> bytes:
    return f"{timestamp}\n{nonce}\nPOST\n{CAMPAIGN_DELIVERY_PATH}\n".encode("utf-8") + body


def sign_campaign_request(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    if not secret:
        raise CampaignDeliveryError("Campaign email authentication is not configured.")
    return hmac.new(secret.encode("utf-8"), canonical_campaign_request(timestamp, nonce, body), hashlib.sha256).hexdigest()


class CampaignWorkerTransport:
    """Trusted Desktop-to-Worker transport; the Worker owns the one recipient."""

    def __init__(self, secret: str, *, endpoint: str = CAMPAIGN_DELIVERY_ENDPOINT, timeout: float = 45.0) -> None:
        self.secret = str(secret or "")
        self.endpoint = endpoint
        self.timeout = timeout

    def send(self, email: CampaignEmail) -> str:
        if urlparse(self.endpoint).path != CAMPAIGN_DELIVERY_PATH:
            raise CampaignDeliveryError("The configured campaign delivery endpoint is invalid.")
        payload = email.to_worker_payload()
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        signature = sign_campaign_request(self.secret, timestamp, nonce, body)
        try:
            response = requests.post(
                self.endpoint,
                data=body,
                headers={
                    "content-type": "application/json",
                    "x-crispy-timestamp": timestamp,
                    "x-crispy-nonce": nonce,
                    "x-crispy-signature": signature,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise CampaignDeliveryError("The campaign email service response was not received. Retry Email is safe.") from error
        try:
            result = response.json()
        except ValueError:
            result = {}
        if not response.ok:
            code = str(result.get("error") or f"HTTP {response.status_code}") if isinstance(result, dict) else f"HTTP {response.status_code}"
            raise CampaignDeliveryError(f"The campaign email was not sent ({code}).")
        return str(result.get("id") or "already_sent") if isinstance(result, dict) else "sent"

