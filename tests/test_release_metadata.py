from __future__ import annotations

import unittest

import aggits_video_factory
from aggits_video_factory.config import APP_NAME, APP_VERSION
from aggits_video_factory.version import (
    EXE_FILENAME,
    PRODUCT_NAME,
    RELEASE_TAG,
    WINDOWS_FILE_VERSION_STRING,
)


class ReleaseMetadataTests(unittest.TestCase):
    def test_version_metadata_has_one_consistent_release_identity(self):
        self.assertEqual(APP_NAME, PRODUCT_NAME)
        self.assertEqual(PRODUCT_NAME, "CRISPY BITS DESKTOP")
        self.assertEqual(APP_VERSION, "3.0.0")
        self.assertEqual(aggits_video_factory.__version__, APP_VERSION)
        self.assertEqual(WINDOWS_FILE_VERSION_STRING, "3.0.0.0")
        self.assertEqual(EXE_FILENAME, "CRISPY BITS DESKTOP v3.0.0.exe")
        self.assertEqual(RELEASE_TAG, "crispy-bits-desktop-v3.0.0")

    def test_legacy_localappdata_name_is_intentionally_not_versioned(self):
        from aggits_video_factory.config import application_data_root

        self.assertEqual(application_data_root().parts[-2:], ("CRISPY BITS", "Video Jukebox Factory"))


if __name__ == "__main__":
    unittest.main()
