from __future__ import annotations

import os
import sys
from pathlib import Path

from .version import APP_VERSION, PRODUCT_NAME


APP_NAME = PRODUCT_NAME
BRAND_NAME = "CRISPY BITS"
GITHUB_OWNER = "Raggedya"
GITHUB_REPOSITORY = "aggits-video-jukebox"
GITHUB_REMOTE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPOSITORY}.git"
PUBLIC_PATH = "crispy-bits"
PUBLIC_BASE_URL = f"https://{GITHUB_OWNER.lower()}.github.io/{GITHUB_REPOSITORY}/{PUBLIC_PATH}"
DELIVERY_ENDPOINT = "https://aggits-video-jukebox.andrewharris501.workers.dev/api/deliveries"
MAX_VIDEOS = 30
MAX_BANJO_VIDEOS = 40
MAX_SPONSOR_CREATIVES = 4
MAX_SPONSOR_MP4_BYTES = 10 * 1024 * 1024
MAX_TICKER_LENGTH = 1000


def video_limit_for_project_type(project_type: object) -> int:
    """Return the included-video limit without changing existing project policy."""
    value = getattr(project_type, "value", project_type)
    return MAX_BANJO_VIDEOS if str(value).lower() == "banjo" else MAX_VIDEOS


def bundled_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[2]


def application_data_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / "CRISPY BITS" / "Video Jukebox Factory"


def resource_path(relative: str) -> Path:
    return bundled_root() / relative
