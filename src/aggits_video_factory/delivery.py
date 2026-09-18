from __future__ import annotations

from typing import Any

import requests

from .config import DELIVERY_ENDPOINT
from .models import Project, ProjectType


class DeliveryError(RuntimeError):
    pass


def request_delivery(project: Project, email: str, timeout: float = 30.0) -> dict[str, Any]:
    if project.project_type not in {ProjectType.BUSINESS, ProjectType.MUSIC}:
        raise DeliveryError(f"Unsupported project type: {project.project_type!r}.")
    if not project.published_url or not project.publication_revision:
        raise DeliveryError("The jukebox must be published before its email can be sent.")
    payload = {
        "slug": project.slug,
        "title": project.title,
        "email": email.strip().lower(),
        "publicUrl": project.published_url,
        "qrUrl": f"{project.published_url.rstrip('/')}/qr-card.png",
        "revision": project.publication_revision,
        "brand": "CRISPY BITS",
        "projectType": project.project_type.value,
        "productName": "CRISPY BITS MUSIC" if project.project_type is ProjectType.MUSIC else "CRISPY BITS BUSINESS",
    }
    try:
        response = requests.post(DELIVERY_ENDPOINT, json=payload, timeout=timeout)
    except requests.RequestException as error:
        raise DeliveryError("The delivery service could not be reached. The email remains queued for retry.") from error
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code == 429:
        raise DeliveryError("Email delivery is temporarily rate limited. The email remains queued for retry.")
    if not response.ok:
        message = str(body.get("error") or f"HTTP {response.status_code}") if isinstance(body, dict) else f"HTTP {response.status_code}"
        raise DeliveryError(f"The delivery service did not send the email ({message}). It remains queued for retry.")
    return body if isinstance(body, dict) else {"ok": True}
