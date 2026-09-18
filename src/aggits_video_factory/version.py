from __future__ import annotations


PRODUCT_NAME = "CRISPY BITS DESKTOP"
VERSION = (3, 1, 0)
APP_VERSION = ".".join(str(part) for part in VERSION)
WINDOWS_FILE_VERSION = (*VERSION, 0)
WINDOWS_FILE_VERSION_STRING = ".".join(str(part) for part in WINDOWS_FILE_VERSION)
EXE_STEM = f"{PRODUCT_NAME} v{APP_VERSION}"
EXE_FILENAME = f"{EXE_STEM}.exe"
RELEASE_TAG = f"crispy-bits-desktop-v{APP_VERSION}"
