"""Transient snapshot picker; no hooks, files, network or project mutations."""
import sys
import tkinter as tk

from PIL import Image, ImageGrab, ImageTk


def sample_colour(snapshot, x, y, displayed_size):
    """Map canvas-local coordinates to original pixels (independent of DPI)."""
    width, height = displayed_size
    if width <= 0 or height <= 0 or not (0 <= x < width and 0 <= y < height):
        return None
    # Match Pillow NEAREST: sample the centre of the displayed pixel, not
    # its top-left edge, so downscaled multi-monitor snapshots stay accurate.
    px = min(snapshot.width - 1, int((int(x) + .5) * snapshot.width / width))
    py = min(snapshot.height - 1, int((int(y) + .5) * snapshot.height / height))
    r, g, b = snapshot.getpixel((px, py))[:3]
    return f"#{r:02X}{g:02X}{b:02X}"


class SnapshotPicker(tk.Toplevel):
    def __init__(self, parent, snapshot):
        super().__init__(parent)
        self.withdraw()
        self.result = None
        try:
            self.snapshot = snapshot
            self.title("Pick club colour — click the snapshot / Escape to cancel")
            self.transient(parent.winfo_toplevel())
            self.resizable(False, False)
            maximum = (max(1, self.winfo_screenwidth() - 80), max(1, self.winfo_screenheight() - 160))
            scale = min(1, maximum[0] / snapshot.width, maximum[1] / snapshot.height)
            self.displayed_size = (max(1, int(snapshot.width * scale)), max(1, int(snapshot.height * scale)))
            display = snapshot.resize(self.displayed_size, Image.Resampling.NEAREST)
            self.photo = ImageTk.PhotoImage(display, master=self)
            toolbar = tk.Frame(self)
            toolbar.pack(fill="x")
            tk.Label(toolbar, text="Click a colour in the captured desktop. Escape cancels.").pack(side="left")
            tk.Button(toolbar, text="Cancel", command=self.cancel).pack(side="right")
            self.canvas = tk.Canvas(self, width=self.displayed_size[0], height=self.displayed_size[1],
                                    highlightthickness=0, bd=0, cursor="crosshair")
            self.canvas.pack()
            self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
            self.canvas.bind("<Button-1>", self.choose)
            self.bind("<Escape>", self.cancel)
            self.protocol("WM_DELETE_WINDOW", self.cancel)
            self.geometry("+20+20")
            self.deiconify()
            self.wait_visibility()
            self.grab_set()
            self.focus_force()
        except Exception:
            self.destroy()
            raise

    def choose(self, event):
        colour = sample_colour(self.snapshot, event.x, event.y, self.displayed_size)
        if colour is not None:
            self.result = colour
            self.destroy()

    def cancel(self, _event=None):
        self.result = None
        self.destroy()


def pick_screen_colour(parent):
    """Capture before opening overlay, preserving the visible editor/thumbnail."""
    parent.update_idletasks()
    snapshot = ImageGrab.grab(all_screens=sys.platform == "win32", include_layered_windows=True).convert("RGB")
    try:
        dialog = SnapshotPicker(parent, snapshot)
        try:
            parent.wait_window(dialog)
            return dialog.result
        finally:
            if dialog.winfo_exists():
                dialog.destroy()
    finally:
        snapshot.close()
        parent.winfo_toplevel().focus_set()
