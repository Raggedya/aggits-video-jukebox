from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
import tkinter as tk

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
        self.assertEqual(APP_VERSION, "3.5.2")
        self.assertEqual(aggits_video_factory.__version__, APP_VERSION)
        self.assertEqual(WINDOWS_FILE_VERSION_STRING, "3.5.2.0")
        self.assertEqual(EXE_FILENAME, "CRISPY BITS DESKTOP v3.5.2.exe")
        self.assertEqual(RELEASE_TAG, "crispy-bits-desktop-v3.5.2")

    def test_legacy_localappdata_name_is_intentionally_not_versioned(self):
        from aggits_video_factory.config import application_data_root

        self.assertEqual(application_data_root().parts[-2:], ("CRISPY BITS", "Video Jukebox Factory"))

    def test_library_actions_fit_the_supported_minimum_width(self):
        desktop_path = Path(__file__).parents[1] / "desktop" / "video_jukebox_factory.py"
        spec = importlib.util.spec_from_file_location("release_desktop", desktop_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Owner:
            _edit_selected = _preview_selected = _publish_selected = lambda self: None
            _edit_videos_selected = lambda self: None
            _unpublish_selected = _open_live = _retry_email = lambda self: None
            _check_live_status = lambda self: None

            def _button(self, parent, text, command, *, primary=False, compact=False):
                return module.Factory._button(self, parent, text, command, primary=primary, compact=compact)

            def _update_actions(self):
                return None

        root = tk.Tk()
        root.withdraw()
        try:
            panel = module.LibraryPanel(root, module.ProjectType.BUSINESS, Owner())
            panel.pack()
            root.update_idletasks()
            minimum_inner_width = 520 - 36
            buttons = list(panel.buttons.values())
            for row in (buttons[:3], buttons[3:6], buttons[6:]):
                requested_width = sum(button.winfo_reqwidth() + 7 for button in row)
                self.assertLessEqual(requested_width, minimum_inner_width)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
