import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from aggits_video_factory.screen_colour import sample_colour, SnapshotPicker, pick_screen_colour
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.models import ProjectType
from aggits_video_factory.football import club_records
from aggits_video_factory.diagnostics import close_logging
from desktop.video_jukebox_factory import Factory


class PixelTests(unittest.TestCase):
    def test_original_pixels_and_scaled_virtual_desktop(self):
        image = Image.new("RGB", (400, 200), "black")
        image.putpixel((300, 100), (18, 52, 86))
        image.putpixel((301, 101), (18, 52, 86))
        self.assertEqual(sample_colour(image, 300, 100, image.size), "#123456")
        self.assertEqual(sample_colour(image, 150, 50, (200, 100)), "#123456")
        self.assertEqual(sample_colour(image, 600, 200, (800, 400)), "#123456")
        for point in ((-1, 0), (200, 0), (0, 100)):
            self.assertIsNone(sample_colour(image, *point, (200, 100)))
        self.assertIsNone(sample_colour(image, 0, 0, (0, 0)))
        scaled = image.resize((200, 100), Image.Resampling.NEAREST)
        self.assertEqual(sample_colour(image, 150, 50, scaled.size), sample_colour(scaled, 150, 50, scaled.size))

    def test_overlay_click_cancel_and_escape(self):
        root = tk.Tk()
        try:
            for action in ("click", "cancel", "escape", "close"):
                dialog = SnapshotPicker(root, Image.new("RGB", (40, 20), (1, 2, 3)))
                root.update()
                if action == "click":
                    dialog.canvas.event_generate("<Button-1>", x=3, y=4)
                elif action == "cancel":
                    dialog.cancel()
                elif action == "escape":
                    dialog.event_generate("<Escape>")
                else:
                    dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
                root.update()
                self.assertEqual(dialog.result, "#010203" if action == "click" else None)
                self.assertFalse(dialog.winfo_exists())
        finally:
            root.destroy()

    def test_capture_order_all_monitors_and_display_failure(self):
        root = tk.Tk()
        try:
            screenshot = Image.new("RGB", (20, 10))
            with patch("aggits_video_factory.screen_colour.ImageGrab.grab", return_value=screenshot) as grab, \
                 patch("aggits_video_factory.screen_colour.SnapshotPicker", side_effect=RuntimeError("display")) as overlay:
                with self.assertRaisesRegex(RuntimeError, "display"):
                    pick_screen_colour(root)
                grab.assert_called_once_with(all_screens=True, include_layered_windows=True)
                overlay.assert_called_once()
            with patch("aggits_video_factory.screen_colour.ImageGrab.grab", side_effect=OSError("capture")), \
                 patch("aggits_video_factory.screen_colour.SnapshotPicker") as overlay:
                with self.assertRaisesRegex(OSError, "capture"):
                    pick_screen_colour(root)
                overlay.assert_not_called()
        finally:
            root.destroy()

    def test_mocked_capture_selection_and_cancel_end_to_end(self):
        root = tk.Tk()
        try:
            for cancel in (False, True):
                def finish():
                    picker = next(w for w in root.winfo_children() if isinstance(w, SnapshotPicker))
                    if cancel:
                        picker.cancel()
                    else:
                        picker.canvas.event_generate("<Button-1>", x=5, y=5)
                root.after(150, finish)
                with patch("aggits_video_factory.screen_colour.ImageGrab.grab", return_value=Image.new("RGB", (20, 20), (90, 100, 110))):
                    self.assertEqual(pick_screen_colour(root), None if cancel else "#5A646E")
                self.assertFalse(root.winfo_children())
        finally:
            root.destroy()

    def test_photo_display_failure_cleans_up_overlay(self):
        root = tk.Tk()
        try:
            with patch("aggits_video_factory.screen_colour.ImageTk.PhotoImage", side_effect=tk.TclError("display")):
                with self.assertRaises(tk.TclError):
                    SnapshotPicker(root, Image.new("RGB", (20, 20)))
            self.assertFalse(root.winfo_children())
        finally:
            root.destroy()


class EditorTests(unittest.TestCase):
    def test_thumbnail_eyedropper_isolation_save_reload_and_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            with patch("desktop.video_jukebox_factory.ProjectStore", return_value=store):
                app = Factory()
            app.withdraw()
            try:
                form = app.forms[ProjectType.FOOTBALL]
                self.assertEqual(form.football_logo_preview.cget("text"), "NO CLUB LOGO")
                logo = Path(directory) / "transparent.png"
                Image.new("RGBA", (400, 100), (20, 40, 60, 128)).save(logo)
                form.football_vars["logo_asset"].set(str(logo))
                self.assertEqual((form._football_logo_image.width(), form._football_logo_image.height()), (160, 40))
                replacement = Path(directory) / "portrait.png"
                Image.new("RGBA", (40, 80)).save(replacement)
                form.football_vars["logo_asset"].set(str(replacement))
                self.assertEqual((form._football_logo_image.width(), form._football_logo_image.height()), (40, 80))
                form.football_vars["logo_asset"].set("")
                self.assertIsNone(form._football_logo_image)
                self.assertEqual(form.football_logo_preview.cget("text"), "NO CLUB LOGO")
                form.football_vars["logo_asset"].set(str(logo))
                original = form.football_vars["base_colour"].get()
                form._football_add()
                form.title_var.set("TEST ONLY SECOND CLUB")
                self.assertIsNone(form._football_logo_image)
                for key, colour in (("base_colour", "#123456"), ("primary_colour", "#654321"), ("highlight_colour", "#AABBCC")):
                    with patch("desktop.video_jukebox_factory.pick_screen_colour", return_value=colour):
                        form._football_screen_colour(key)
                    self.assertEqual(form.football_swatches[key].cget("background"), colour)
                self.assertEqual(form.football_records[0]["settings"]["base_colour"], original)
                with patch("desktop.video_jukebox_factory.pick_screen_colour", return_value=None):
                    form._football_screen_colour("base_colour")
                with patch("desktop.video_jukebox_factory.pick_screen_colour", side_effect=OSError("capture failed")), \
                     patch("desktop.video_jukebox_factory.messagebox.showerror") as error:
                    form._football_screen_colour("base_colour")
                    error.assert_called_once()
                self.assertEqual(form.football_vars["base_colour"].get(), "#123456")
                with patch.object(app, "_open_project_preview"), patch("desktop.video_jukebox_factory.messagebox.showinfo"):
                    self.assertTrue(app._save_football())
                project = next(iter(app.projects.values()))
                restored = store.load_project(project.slug)
                form.load_project(restored)
                self.assertEqual(form.football_vars["base_colour"].get(), "#123456")
                payload = json.loads((store.project_dir(project.slug) / "site/machine.json").read_text())
                self.assertEqual(payload["footballConfig"]["clubs"][1]["highlightColour"], "#AABBCC")
                form._football_show(club_records(restored)[0])
                self.assertEqual(form.football_vars["base_colour"].get(), original)
                self.assertEqual(form._football_logo_image.width(), 160)
                self.assertFalse(Path(form.football_vars["logo_asset"].get()).is_absolute())
            finally:
                app.preview_server.stop()
                if app._async_poll_id:
                    app.after_cancel(app._async_poll_id)
                app.destroy()
                close_logging(store.root)
