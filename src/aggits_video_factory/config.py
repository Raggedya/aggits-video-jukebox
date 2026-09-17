from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "CRISPY BITS Video Jukebox Factory"
APP_VERSION = "1.0.0"
BRAND_NAME = "CRISPY BITS"
GITHUB_OWNER = "Raggedya"
GITHUB_REPOSITORY = "aggits-video-jukebox"
GITHUB_REMOTE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPOSITORY}.git"
PUBLIC_PATH = "crispy-bits"
PUBLIC_BASE_URL = f"https://{GITHUB_OWNER.lower()}.github.io/{GITHUB_REPOSITORY}/{PUBLIC_PATH}"
DELIVERY_ENDPOINT = "https://aggits-video-jukebox.andrewharris501.workers.dev/api/deliveries"
MAX_VIDEOS = 30
MAX_TICKER_LENGTH = 1000


def bundled_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[2]


def application_data_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / "CRISPY BITS" / "Video Jukebox Factory"


def resource_path(relative: str) -> Path:
    return bundled_root() / relative
