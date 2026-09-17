from __future__ import annotations

import re
import sys
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import requests
from PIL import Image, ImageOps, ImageTk


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aggits_video_factory.config import APP_NAME, MAX_TICKER_LENGTH, MAX_VIDEOS, PUBLIC_BASE_URL, resource_path
from aggits_video_factory.delivery import DeliveryError, request_delivery
from aggits_video_factory.models import Project, utc_now
from aggits_video_factory.preview import PreviewServer
from aggits_video_factory.publisher import PublishError, Publisher
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore, slugify
from aggits_video_factory.youtube_api import YouTubeClient, YouTubeError, merge_video_selections


INK = "#070605"
PANEL = "#15120e"
PANEL_2 = "#201a12"
CREAM = "#f2e4bf"
PAPER = "#fff6dc"
MUTED = "#b8a27b"
BRASS = "#b88a4f"
DEEP_BRASS = "#5f4225"
ACTIVE = "#6a522f"
SUCCESS = "#a7c58b"
ERROR = "#e19999"


class Factory(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1320x820")
        self.minsize(1120, 720)
        self.configure(bg=INK)
        self.store = ProjectStore()
        self.preview_server = PreviewServer()
        self.settings = self.store.load_settings()
        self.busy = False
        self.editing_project_slug: str | None = None
        self.projects: dict[str, Project] = {}
        self._configure_styles()
        self._build()
        self._refresh_library()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Factory.Treeview", background="#0c0a08", foreground=CREAM, fieldbackground="#0c0a08", bordercolor=DEEP_BRASS, rowheight=34, font=("Segoe UI", 9))
        style.map("Factory.Treeview", background=[("selected", "#49361f")], foreground=[("selected", PAPER)])
        style.configure("Factory.Treeview.Heading", background="#2a2015", foreground=BRASS, relief="flat", font=("Segoe UI Semibold", 8))
        style.configure("Factory.Vertical.TScrollbar", background=DEEP_BRASS, troughcolor="#0b0907", bordercolor=INK, arrowcolor=CREAM)

    def _build(self) -> None:
        header = tk.Frame(self, bg=INK, height=78)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="AGGITS", bg=INK, fg=BRASS, font=("Georgia", 27, "bold")).pack(side="left", padx=(24, 18), pady=12)
        title = tk.Frame(header, bg=INK)
        title.pack(side="left", pady=12)
        tk.Label(title, text="VIDEO JUKEBOX FACTORY", bg=INK, fg=PAPER, font=("Segoe UI Semibold", 15)).pack(anchor="w")
        tk.Label(title, text="YOUTUBE CHANNEL + VIDEO LINKS → 30-VIDEO SINGLE-REEL JUKEBOX", bg=INK, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(4, 0))
        self.settings_button = self._button(header, "SETTINGS", self._open_settings, compact=True)
        self.settings_button.pack(side="right", padx=24, pady=18)

        divider = tk.Frame(self, bg=DEEP_BRASS, height=1)
        divider.pack(fill="x")
        body = tk.PanedWindow(self, orient="horizontal", bg=INK, sashwidth=8, sashrelief="flat", bd=0)
        body.pack(fill="both", expand=True, padx=18, pady=18)
        form_panel = tk.Frame(body, bg=PANEL, highlightbackground=DEEP_BRASS, highlightthickness=1)
        library_panel = tk.Frame(body, bg=PANEL, highlightbackground=DEEP_BRASS, highlightthickness=1)
        body.add(form_panel, minsize=470, width=510)
        body.add(library_panel, minsize=590)
        self._build_form(form_panel)
        self._build_library(library_panel)

        self.status = tk.Label(self, text="READY", bg="#040302", fg=MUTED, anchor="w", padx=18, font=("Segoe UI Semibold", 8))
        self.status.pack(fill="x", side="bottom", ipady=7)

    def _build_form(self, panel: tk.Frame) -> None:
        inner = tk.Frame(panel, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=24, pady=22)
        self.form_title = tk.Label(inner, text="CREATE A VIDEO JUKEBOX", bg=PANEL, fg=BRASS, font=("Georgia", 18, "bold"))
        self.form_title.pack(anchor="w")
        self.form_subtitle = tk.Label(inner, text="Use a channel, individual videos, or both.", bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        self.form_subtitle.pack(anchor="w", pady=(5, 12))

        self.title_entry = self._entry(inner, "JUKEBOX TITLE")
        self.channel_entry = self._entry(inner, "YOUTUBE CHANNEL / MAIN PAGE LINK · OPTIONAL")

        video_heading = tk.Frame(inner, bg=PANEL)
        video_heading.pack(fill="x", pady=(14, 5))
        tk.Label(video_heading, text="INDIVIDUAL VIDEO LINKS · OPTIONAL", bg=PANEL, fg=BRASS, font=("Segoe UI Semibold", 8)).pack(side="left")
        tk.Label(video_heading, text="UP TO 15", bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(side="right")
        links_shell = tk.Frame(inner, bg="#080706", highlightbackground="#332719", highlightthickness=1, height=174)
        links_shell.pack(fill="x")
        links_shell.pack_propagate(False)
        links_canvas = tk.Canvas(links_shell, bg="#080706", bd=0, highlightthickness=0)
        links_scroll = ttk.Scrollbar(links_shell, orient="vertical", command=links_canvas.yview, style="Factory.Vertical.TScrollbar")
        links_canvas.configure(yscrollcommand=links_scroll.set)
        links_scroll.pack(side="right", fill="y")
        links_canvas.pack(side="left", fill="both", expand=True)
        links_frame = tk.Frame(links_canvas, bg="#080706")
        links_window = links_canvas.create_window((0, 0), window=links_frame, anchor="nw")
        links_frame.bind("<Configure>", lambda _event: links_canvas.configure(scrollregion=links_canvas.bbox("all")))
        links_canvas.bind("<Configure>", lambda event: links_canvas.itemconfigure(links_window, width=event.width))
        self.video_url_entries: list[tk.Entry] = []
        for index in range(15):
            row = tk.Frame(links_frame, bg="#080706")
            row.pack(fill="x", padx=9, pady=(8 if index == 0 else 2, 2))
            tk.Label(row, text=f"{index + 1:02d}", width=3, anchor="w", bg="#080706", fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left")
            entry = tk.Entry(row, bg="#100d09", fg=PAPER, insertbackground=CREAM, relief="flat", bd=0, highlightbackground="#332719", highlightthickness=1, font=("Segoe UI", 9))
            entry.pack(side="left", fill="x", expand=True, ipady=5)
            self.video_url_entries.append(entry)
        links_canvas.bind("<Enter>", lambda _event: links_canvas.bind_all("<MouseWheel>", lambda event: links_canvas.yview_scroll(int(-event.delta / 120), "units")))
        links_canvas.bind("<Leave>", lambda _event: links_canvas.unbind_all("<MouseWheel>"))

        ticker_heading = tk.Frame(inner, bg=PANEL)
        ticker_heading.pack(fill="x", pady=(18, 6))
        tk.Label(ticker_heading, text="TICKER TEXT", bg=PANEL, fg=BRASS, font=("Segoe UI Semibold", 8)).pack(side="left")
        self.ticker_count = tk.Label(ticker_heading, text=f"0 / {MAX_TICKER_LENGTH}", bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.ticker_count.pack(side="right")
        self.ticker_text = tk.Text(inner, height=4, wrap="word", bg="#080706", fg=PAPER, insertbackground=CREAM, relief="flat", bd=0, highlightbackground="#332719", highlightthickness=1, font=("Segoe UI", 10), padx=12, pady=10)
        self.ticker_text.pack(fill="x")
        self.ticker_text.bind("<KeyRelease>", self._ticker_changed)
        self.ticker_text.insert("1.0", "PULL THE LEVER. LET THE MACHINE CHOOSE WHAT YOU WATCH NEXT.")
        self._ticker_changed()

        info = tk.Frame(inner, bg="#0d0a07", highlightbackground="#3a2a19", highlightthickness=1)
        info.pack(fill="x", pady=(12, 10))
        tk.Label(info, text="AUTOMATIC BUILD", bg="#0d0a07", fg=BRASS, font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=13, pady=(11, 4))
        tk.Label(info, text=f"Manual links are included first. Duplicate videos are removed, then the channel fills the remaining spaces up to {MAX_VIDEOS}.", bg="#0d0a07", fg=MUTED, wraplength=420, justify="left", font=("Segoe UI", 8)).pack(anchor="w", padx=13, pady=(0, 12))

        form_actions = tk.Frame(inner, bg=PANEL)
        form_actions.pack(fill="x", pady=(6, 8))
        self.create_button = self._button(form_actions, "ANALYSE + REVIEW VIDEOS", self._create_jukebox, primary=True)
        self.create_button.pack(side="left", fill="x", expand=True, ipady=8)
        self.cancel_edit_button = self._button(form_actions, "CANCEL EDIT", self._cancel_edit, compact=True)
        tk.Label(inner, text="Next: review all resolved videos with thumbnails and inclusion controls. The jukebox is built only after you approve that list.", bg=PANEL, fg=MUTED, wraplength=430, justify="left", font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 0))

    def _build_library(self, panel: tk.Frame) -> None:
        heading = tk.Frame(panel, bg=PANEL)
        heading.pack(fill="x", padx=22, pady=(20, 12))
        tk.Label(heading, text="JUKEBOX LIBRARY", bg=PANEL, fg=BRASS, font=("Georgia", 18, "bold")).pack(side="left")
        self.library_count = tk.Label(heading, text="0 PROJECTS", bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 8))
        self.library_count.pack(side="right", pady=6)

        shell = tk.Frame(panel, bg=PANEL)
        shell.pack(fill="both", expand=True, padx=22)
        columns = ("title", "channel", "videos", "status", "email")
        self.library = ttk.Treeview(shell, columns=columns, show="headings", style="Factory.Treeview", selectmode="browse")
        headings = {"title": "TITLE", "channel": "YOUTUBE CHANNEL", "videos": "VIDEOS", "status": "PUBLICATION", "email": "EMAIL"}
        widths = {"title": 210, "channel": 190, "videos": 64, "status": 100, "email": 95}
        for column in columns:
            self.library.heading(column, text=headings[column])
            self.library.column(column, width=widths[column], minwidth=50, anchor="w" if column in {"title", "channel"} else "center")
        scroll = ttk.Scrollbar(shell, orient="vertical", command=self.library.yview, style="Factory.Vertical.TScrollbar")
        self.library.configure(yscrollcommand=scroll.set)
        self.library.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.library.bind("<<TreeviewSelect>>", lambda _event: self._update_actions())
        self.library.bind("<Double-1>", lambda _event: self._preview_selected())

        actions = tk.Frame(panel, bg=PANEL)
        actions.pack(fill="x", padx=22, pady=18)
        self.preview_button = self._button(actions, "PREVIEW", self._preview_selected, compact=True)
        self.edit_button = self._button(actions, "EDIT VIDEOS", self._edit_selected, compact=True)
        self.publish_button = self._button(actions, "PUBLISH", self._publish_selected, compact=True, primary=True)
        self.unpublish_button = self._button(actions, "UNPUBLISH", self._unpublish_selected, compact=True)
        self.open_button = self._button(actions, "OPEN LIVE", self._open_live, compact=True)
        self.email_button = self._button(actions, "RETRY EMAIL", self._retry_email, compact=True)
        for button in [self.preview_button, self.edit_button, self.publish_button, self.unpublish_button, self.open_button, self.email_button]:
            button.pack(side="left", padx=(0, 8))

        self.selection_note = tk.Label(panel, text="Select a jukebox to preview or publish it.", bg=PANEL, fg=MUTED, anchor="w", font=("Segoe UI", 8))
        self.selection_note.pack(fill="x", padx=22, pady=(0, 17))
        self._update_actions()

    def _entry(self, parent: tk.Misc, label: str) -> tk.Entry:
        tk.Label(parent, text=label, bg=PANEL, fg=BRASS, font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(12, 6))
        entry = tk.Entry(parent, bg="#080706", fg=PAPER, insertbackground=CREAM, relief="flat", bd=0, highlightbackground="#332719", highlightthickness=1, font=("Segoe UI", 10))
        entry.pack(fill="x", ipady=10)
        return entry

    def _button(self, parent: tk.Misc, text: str, command, *, primary: bool = False, compact: bool = False) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg="#5a4328" if primary else "#2a2117",
            fg=PAPER if primary else CREAM,
            activebackground="#7a5b34" if primary else "#3b2d1d",
            activeforeground=PAPER,
            disabledforeground="#6f6657",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 9 if compact else 10),
            padx=12 if compact else 22,
            pady=8 if compact else 12,
        )

    def _ticker_changed(self, _event=None) -> None:
        value = self.ticker_text.get("1.0", "end-1c")
        if len(value) > MAX_TICKER_LENGTH:
            value = value[:MAX_TICKER_LENGTH]
            self.ticker_text.delete("1.0", "end")
            self.ticker_text.insert("1.0", value)
        self.ticker_count.configure(text=f"{len(value)} / {MAX_TICKER_LENGTH}", fg=ERROR if len(value) >= MAX_TICKER_LENGTH else MUTED)

    def _selected_project(self) -> Project | None:
        selected = self.library.selection()
        if not selected:
            return None
        return self.projects.get(selected[0])

    def _refresh_library(self, select_slug: str | None = None) -> None:
        projects = self.store.list_projects()
        self.projects = {project.slug: project for project in projects}
        self.library.delete(*self.library.get_children())
        for project in projects:
            self.library.insert("", "end", iid=project.slug, values=(project.title, project.channel_title, len(project.videos), project.status.replace("_", " ").upper(), project.delivery_status.replace("_", " ").upper()))
        self.library_count.configure(text=f"{len(projects)} PROJECT{'S' if len(projects) != 1 else ''}")
        if select_slug and select_slug in self.projects:
            self.library.selection_set(select_slug)
            self.library.focus(select_slug)
            self.library.see(select_slug)
        self._update_actions()

    def _update_actions(self) -> None:
        project = self._selected_project()
        allowed = project is not None and not self.busy
        self.preview_button.configure(state="normal" if allowed else "disabled")
        self.edit_button.configure(state="normal" if allowed else "disabled")
        self.publish_button.configure(state="normal" if allowed and project.status != "published" else "disabled")
        self.publish_button.configure(text="UPDATE + REPUBLISH" if project and project.status == "changes_pending" else "PUBLISH")
        self.unpublish_button.configure(state="normal" if allowed and bool(project.published_url) else "disabled")
        self.open_button.configure(state="normal" if allowed and bool(project.published_url) else "disabled")
        self.email_button.configure(state="normal" if allowed and project.status == "published" and project.delivery_status != "sent" else "disabled")
        if project:
            self.selection_note.configure(text=f"{project.title} · {len(project.videos)} videos · {project.status.replace('_', ' ').upper()} · EMAIL {project.delivery_status.upper()}")
        else:
            self.selection_note.configure(text="Select a jukebox to preview or publish it.")

    def _set_busy(self, busy: bool, message: str) -> None:
        self.busy = busy
        self.status.configure(text=message, fg=BRASS if busy else MUTED)
        self.create_button.configure(state="disabled" if busy else "normal")
        self.settings_button.configure(state="disabled" if busy else "normal")
        self._update_actions()

    def _edit_selected(self) -> None:
        project = self._selected_project()
        if not project or self.busy:
            return
        self.editing_project_slug = project.slug
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, project.title)
        self.channel_entry.delete(0, "end")
        self.channel_entry.insert(0, project.source_channel_url or project.channel_url)
        for entry in self.video_url_entries:
            entry.delete(0, "end")
        for entry, url in zip(self.video_url_entries, project.manual_video_urls):
            entry.insert(0, url)
        self.ticker_text.delete("1.0", "end")
        self.ticker_text.insert("1.0", project.ticker_text)
        self._ticker_changed()
        self.form_title.configure(text="EDIT VIDEO JUKEBOX")
        self.form_subtitle.configure(text=f"Editing {project.title}. The current public version remains live until Update + Republish.")
        self.create_button.configure(text="ANALYSE + REVIEW CHANGES")
        if not self.cancel_edit_button.winfo_manager():
            self.cancel_edit_button.pack(side="right", padx=(8, 0), ipady=5)
        self.title_entry.focus_set()

    def _cancel_edit(self, *, clear: bool = True) -> None:
        self.editing_project_slug = None
        self.form_title.configure(text="CREATE A VIDEO JUKEBOX")
        self.form_subtitle.configure(text="Use a channel, individual videos, or both.")
        self.create_button.configure(text="ANALYSE + REVIEW VIDEOS")
        self.cancel_edit_button.pack_forget()
        if clear:
            self.title_entry.delete(0, "end")
            self.channel_entry.delete(0, "end")
            for entry in self.video_url_entries:
                entry.delete(0, "end")
            self.ticker_text.delete("1.0", "end")
            self.ticker_text.insert("1.0", "PULL THE LEVER. LET THE MACHINE CHOOSE WHAT YOU WATCH NEXT.")
            self._ticker_changed()

    def _run_async(self, message: str, worker, complete) -> None:
        if self.busy:
            return
        self._set_busy(True, message)

        def execute() -> None:
            try:
                result = worker()
            except Exception as error:
                self.after(0, lambda: self._async_failed(error))
            else:
                self.after(0, lambda: self._async_complete(result, complete))

        threading.Thread(target=execute, daemon=True).start()

    def _async_failed(self, error: Exception) -> None:
        self._set_busy(False, "OPERATION PAUSED")
        messagebox.showerror(APP_NAME, str(error))

    def _async_complete(self, result, complete) -> None:
        self._set_busy(False, "READY")
        complete(result)

    def _create_jukebox(self) -> None:
        title = re.sub(r"\s+", " ", self.title_entry.get()).strip()
        channel_url = self.channel_entry.get().strip()
        video_urls = [entry.get().strip() for entry in self.video_url_entries if entry.get().strip()]
        ticker = self.ticker_text.get("1.0", "end-1c").strip()
        if not title or len(title) > 120:
            messagebox.showerror(APP_NAME, "Enter a jukebox title of no more than 120 characters.")
            return
        if not channel_url and not video_urls:
            messagebox.showerror(APP_NAME, "Paste a YouTube channel link, at least one individual video link, or both.")
            return
        if len(ticker) > MAX_TICKER_LENGTH:
            messagebox.showerror(APP_NAME, f"Ticker text cannot exceed {MAX_TICKER_LENGTH} characters.")
            return
        api_key = str(self.settings.get("youtubeApiKey") or "")
        if not api_key:
            messagebox.showinfo(APP_NAME, "Save a YouTube Data API key in SETTINGS once, then press Create Jukebox again.")
            self._open_settings()
            return

        editing_slug = self.editing_project_slug
        slug = editing_slug or slugify(title)

        def worker() -> dict[str, object]:
            client = YouTubeClient(api_key)
            manual_catalogue = client.fetch_videos(video_urls) if video_urls else None
            channel_catalogue = client.fetch_catalogue(channel_url, MAX_VIDEOS) if channel_url else None
            videos = merge_video_selections(
                manual_catalogue.videos if manual_catalogue else [],
                channel_catalogue.videos if channel_catalogue else [],
                MAX_VIDEOS,
            )
            catalogue = channel_catalogue or manual_catalogue
            if catalogue is None or not videos:
                raise YouTubeError("No public, embeddable YouTube videos were found.")
            thumbnail_bytes: dict[str, bytes] = {}

            def fetch_thumbnail(video) -> tuple[str, bytes]:
                if not video.thumbnail_url:
                    return video.video_id, b""
                try:
                    response = requests.get(video.thumbnail_url, timeout=10)
                    response.raise_for_status()
                    return video.video_id, response.content
                except requests.RequestException:
                    return video.video_id, b""

            with ThreadPoolExecutor(max_workers=8) as pool:
                for video_id, content in pool.map(fetch_thumbnail, videos):
                    if content:
                        thumbnail_bytes[video_id] = content
            return {
                "slug": slug,
                "title": title,
                "ticker": ticker,
                "catalogue": catalogue,
                "videos": videos,
                "manual_ids": {video.video_id for video in (manual_catalogue.videos if manual_catalogue else [])},
                "manual_urls": video_urls,
                "source_channel_url": channel_url,
                "editing_slug": editing_slug,
                "excluded_ids": set(self.projects[editing_slug].excluded_video_ids) if editing_slug and editing_slug in self.projects else set(),
                "thumbnails": thumbnail_bytes,
            }

        self._run_async("READING YOUTUBE + PREPARING VIDEO REVIEW…", worker, self._review_video_selection)

    def _review_video_selection(self, candidate: dict[str, object]) -> None:
        videos = list(candidate["videos"])
        manual_ids = set(candidate["manual_ids"])
        excluded_ids = set(candidate.get("excluded_ids") or set())
        thumbnail_bytes = dict(candidate["thumbnails"])
        dialog = tk.Toplevel(self)
        dialog.title("Review Jukebox Videos")
        dialog.geometry("980x720")
        dialog.minsize(760, 560)
        dialog.configure(bg=INK)
        dialog.transient(self)

        heading = tk.Frame(dialog, bg=PANEL, highlightbackground=DEEP_BRASS, highlightthickness=1)
        heading.pack(fill="x", padx=18, pady=(18, 10))
        tk.Label(heading, text="REVIEW INCLUDED VIDEOS", bg=PANEL, fg=BRASS, font=("Georgia", 18, "bold")).pack(anchor="w", padx=20, pady=(15, 3))
        tk.Label(heading, text="Every video is included by default. Untick anything you do not want in this jukebox.", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=20, pady=(0, 14))

        list_shell = tk.Frame(dialog, bg="#080706", highlightbackground=DEEP_BRASS, highlightthickness=1)
        list_shell.pack(fill="both", expand=True, padx=18)
        canvas = tk.Canvas(list_shell, bg="#080706", bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_shell, orient="vertical", command=canvas.yview, style="Factory.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        rows_frame = tk.Frame(canvas, bg="#080706")
        canvas_window = canvas.create_window((0, 0), window=rows_frame, anchor="nw")
        rows_frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(canvas_window, width=event.width))

        variables: list[tk.BooleanVar] = []
        inclusion_buttons: list[tk.Checkbutton] = []
        thumbnail_images: list[ImageTk.PhotoImage] = []
        for index, video in enumerate(videos, start=1):
            row = tk.Frame(rows_frame, bg="#11100d" if index % 2 else "#0b0a08", height=84)
            row.pack(fill="x", padx=4, pady=(4 if index == 1 else 0, 2))
            row.pack_propagate(False)
            included = tk.BooleanVar(dialog, video.video_id not in excluded_ids)
            variables.append(included)
            check = tk.Checkbutton(
                row,
                text="INCLUDED ✓",
                variable=included,
                indicatoron=False,
                width=12,
                bg="#5a4328",
                activebackground="#7a5b34",
                selectcolor="#5a4328",
                fg=PAPER,
                activeforeground=PAPER,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=BRASS,
                font=("Segoe UI Semibold", 8),
                padx=5,
                pady=7,
            )
            check.pack(side="left", padx=(10, 10))
            inclusion_buttons.append(check)

            image_data = thumbnail_bytes.get(video.video_id)
            if image_data:
                try:
                    image = Image.open(BytesIO(image_data)).convert("RGB")
                    image = ImageOps.fit(image, (112, 63), method=Image.Resampling.LANCZOS)
                    thumbnail = ImageTk.PhotoImage(image, master=dialog)
                    thumbnail_images.append(thumbnail)
                    tk.Label(row, image=thumbnail, bg="#050403", bd=0).pack(side="left", padx=(0, 12))
                except OSError:
                    tk.Label(row, text="NO\nIMAGE", width=14, height=3, bg="#050403", fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=(0, 12))
            else:
                tk.Label(row, text="NO\nIMAGE", width=14, height=3, bg="#050403", fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=(0, 12))

            detail = tk.Frame(row, bg=row["bg"])
            detail.pack(side="left", fill="both", expand=True, pady=9)
            source = "MANUALLY ADDED" if video.video_id in manual_ids else "CHANNEL SELECTION"
            tk.Label(detail, text=video.title, bg=row["bg"], fg=PAPER, anchor="w", font=("Segoe UI Semibold", 10)).pack(fill="x")
            tk.Label(detail, text=f"{source}  ·  {video.channel_title}", bg=row["bg"], fg=BRASS, anchor="w", font=("Segoe UI Semibold", 8)).pack(fill="x", pady=(3, 1))
            tk.Label(detail, text=video.url, bg=row["bg"], fg=MUTED, anchor="w", font=("Segoe UI", 8)).pack(fill="x")
            tk.Label(row, text=f"{index:02d}", bg=row["bg"], fg=MUTED, font=("Georgia", 11, "bold")).pack(side="right", padx=14)

        dialog._thumbnail_images = thumbnail_images
        footer = tk.Frame(dialog, bg=INK)
        footer.pack(fill="x", padx=18, pady=(10, 18))
        count_label = tk.Label(footer, bg=INK, fg=CREAM, font=("Segoe UI Semibold", 9))
        count_label.pack(side="left", padx=(3, 14))

        def update_count() -> None:
            total = sum(variable.get() for variable in variables)
            count_label.configure(text=f"{total} OF {len(videos)} VIDEOS INCLUDED")
            for variable, button in zip(variables, inclusion_buttons):
                if variable.get():
                    button.configure(text="INCLUDED ✓", bg="#5a4328", activebackground="#7a5b34", fg=PAPER)
                else:
                    button.configure(text="EXCLUDED", bg="#241b13", activebackground="#34271b", fg=MUTED)

        def set_all(value: bool) -> None:
            for variable in variables:
                variable.set(value)
            update_count()

        for variable in variables:
            variable.trace_add("write", lambda *_args: update_count())

        def build_selected() -> None:
            selected = [video for video, variable in zip(videos, variables) if variable.get()]
            if not selected:
                messagebox.showerror(APP_NAME, "Include at least one video before building the jukebox.", parent=dialog)
                return
            canvas.unbind_all("<MouseWheel>")
            dialog.destroy()
            self._finish_jukebox(candidate, selected)

        def cancel_review() -> None:
            canvas.unbind_all("<MouseWheel>")
            dialog.destroy()

        self._button(footer, "SELECT ALL", lambda: set_all(True), compact=True).pack(side="left", padx=(0, 6))
        self._button(footer, "CLEAR ALL", lambda: set_all(False), compact=True).pack(side="left")
        build_label = "SAVE REVIEWED CHANGES" if candidate.get("editing_slug") else "BUILD JUKEBOX"
        self._button(footer, build_label, build_selected, primary=True, compact=True).pack(side="right")
        self._button(footer, "CANCEL", cancel_review, compact=True).pack(side="right", padx=8)
        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units")))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))
        dialog.protocol("WM_DELETE_WINDOW", cancel_review)
        update_count()
        dialog.update_idletasks()
        x = max(0, self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2)
        y = max(0, self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.lift()
        dialog.focus_force()
        dialog.grab_set()

    def _finish_jukebox(self, candidate: dict[str, object], videos: list) -> None:
        catalogue = candidate["catalogue"]
        slug = str(candidate["slug"])

        def worker() -> Project:
            editing_slug = str(candidate.get("editing_slug") or "")
            existing = self.projects.get(editing_slug or slug)
            selected_ids = {video.video_id for video in videos}
            reviewed_ids = {video.video_id for video in candidate["videos"]}
            excluded_ids = (set(existing.excluded_video_ids) if existing else set()) | (reviewed_ids - selected_ids)
            excluded_ids -= selected_ids
            changes_pending = bool(existing and existing.published_url)
            project = Project(
                slug=slug,
                title=str(candidate["title"]),
                ticker_text=str(candidate["ticker"]),
                channel_url=catalogue.channel_url,
                channel_id=catalogue.channel_id,
                channel_title=catalogue.channel_title,
                channel_thumbnail=catalogue.channel_thumbnail,
                source_channel_url=str(candidate.get("source_channel_url") or ""),
                manual_video_urls=[str(url) for url in candidate.get("manual_urls", [])],
                excluded_video_ids=sorted(excluded_ids),
                videos=videos,
                status="changes_pending" if changes_pending else "draft",
                created_at=existing.created_at if existing else utc_now(),
                published_at=existing.published_at if existing else None,
                published_url=existing.published_url if existing else None,
                delivery_status=existing.delivery_status if changes_pending and existing else "not_requested",
                publication_revision=existing.publication_revision if existing else None,
            )
            project_dir = self.store.project_dir(slug)
            build_project_site(project, project_dir / "site")
            self.store.save_project(project)
            return project

        self._run_async("BUILDING THE REVIEWED JUKEBOX…", worker, self._create_complete)

    def _create_complete(self, project: Project) -> None:
        self._refresh_library(project.slug)
        editing = project.status == "changes_pending"
        self._cancel_edit()
        if editing:
            messagebox.showinfo(APP_NAME, f"{project.title} now has {len(project.videos)} reviewed videos.\n\nThe existing live jukebox is unchanged. Press UPDATE + REPUBLISH in the Library when you are ready.")
        else:
            messagebox.showinfo(APP_NAME, f"{project.title} was created with {len(project.videos)} videos.\n\nIt is private until you press PUBLISH in the Library.")

    def _preview_selected(self) -> None:
        project = self._selected_project()
        if not project:
            return
        site = self.store.project_dir(project.slug) / "site"
        if not (site / "index.html").is_file():
            messagebox.showerror(APP_NAME, "The local preview files are missing. Recreate the jukebox.")
            return
        webbrowser.open(self.preview_server.start(site))

    def _publish_selected(self) -> None:
        project = self._selected_project()
        if not project:
            return
        question = f"Update and republish {project.title}?" if project.status == "changes_pending" else f"Publish {project.title} to the public AGGITS Video Jukebox library?"
        if not messagebox.askyesno("Publish jukebox", question):
            return

        def worker() -> tuple[Project, str | None]:
            public_url, revision = Publisher(self.store).publish(project)
            project.status = "published"
            project.published_url = public_url
            project.published_at = utc_now()
            project.publication_revision = revision
            project.delivery_status = "queued"
            self.store.save_project(project)
            build_project_site(project, self.store.project_dir(project.slug) / "site")
            email_error = None
            try:
                request_delivery(project, str(self.settings.get("deliveryEmail") or ""))
                project.delivery_status = "sent"
            except DeliveryError as error:
                email_error = str(error)
            self.store.save_project(project)
            return project, email_error

        self._run_async("PUBLISHING + WAITING FOR THE LIVE JUKEBOX…", worker, self._publish_complete)

    def _publish_complete(self, result: tuple[Project, str | None]) -> None:
        project, email_error = result
        self._refresh_library(project.slug)
        detail = f"{project.title} is public:\n\n{project.published_url}"
        if email_error:
            detail += f"\n\nThe link and QR email remains queued:\n{email_error}"
        else:
            detail += f"\n\nThe link and titled QR card were emailed to {self.settings.get('deliveryEmail')}."
        messagebox.showinfo(APP_NAME, detail)

    def _unpublish_selected(self) -> None:
        project = self._selected_project()
        if not project:
            return
        if not messagebox.askyesno("Unpublish jukebox", f"Remove {project.title} from the public library?\n\nThe private project and its videos will remain in this desktop application."):
            return

        def worker() -> Project:
            Publisher(self.store).unpublish(project)
            project.status = "unpublished"
            project.published_url = None
            project.published_at = None
            project.publication_revision = None
            project.delivery_status = "not_requested"
            self.store.save_project(project)
            build_project_site(project, self.store.project_dir(project.slug) / "site")
            return project

        self._run_async("UNPUBLISHING THE JUKEBOX…", worker, lambda result: self._unpublish_complete(result))

    def _unpublish_complete(self, project: Project) -> None:
        self._refresh_library(project.slug)
        messagebox.showinfo(APP_NAME, f"{project.title} is no longer public. Its private project remains in the Library.")

    def _open_live(self) -> None:
        project = self._selected_project()
        if project and project.published_url:
            webbrowser.open(project.published_url)

    def _retry_email(self) -> None:
        project = self._selected_project()
        if not project:
            return

        def worker() -> Project:
            request_delivery(project, str(self.settings.get("deliveryEmail") or ""))
            project.delivery_status = "sent"
            self.store.save_project(project)
            return project

        self._run_async("SENDING THE LINK + QR EMAIL…", worker, self._email_complete)

    def _email_complete(self, project: Project) -> None:
        self._refresh_library(project.slug)
        messagebox.showinfo(APP_NAME, f"The {project.title} link and QR card were emailed to {self.settings.get('deliveryEmail')}.")

    def _open_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Video Jukebox Factory Settings")
        dialog.geometry("650x430")
        dialog.resizable(False, False)
        dialog.configure(bg=INK)
        dialog.transient(self)
        dialog.grab_set()
        frame = tk.Frame(dialog, bg=PANEL, highlightbackground=DEEP_BRASS, highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=22, pady=22)
        tk.Label(frame, text="FACTORY SETTINGS", bg=PANEL, fg=BRASS, font=("Georgia", 18, "bold")).pack(anchor="w", padx=24, pady=(24, 8))
        tk.Label(frame, text="The YouTube key is encrypted for this Windows account and never written into a published jukebox.", bg=PANEL, fg=MUTED, wraplength=560, justify="left", font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(0, 18))
        tk.Label(frame, text="YOUTUBE DATA API KEY", bg=PANEL, fg=BRASS, font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=24)
        key_entry = tk.Entry(frame, show="•", bg="#080706", fg=PAPER, insertbackground=CREAM, relief="flat", highlightbackground="#332719", highlightthickness=1, font=("Segoe UI", 10))
        key_entry.pack(fill="x", padx=24, pady=(6, 16), ipady=9)
        key_entry.insert(0, str(self.settings.get("youtubeApiKey") or ""))
        tk.Label(frame, text="DELIVERY EMAIL", bg=PANEL, fg=BRASS, font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=24)
        email_entry = tk.Entry(frame, bg="#080706", fg=PAPER, insertbackground=CREAM, relief="flat", highlightbackground="#332719", highlightthickness=1, font=("Segoe UI", 10))
        email_entry.pack(fill="x", padx=24, pady=(6, 20), ipady=9)
        email_entry.insert(0, str(self.settings.get("deliveryEmail") or ""))

        def save() -> None:
            key = key_entry.get().strip()
            email = email_entry.get().strip().lower()
            if not key:
                messagebox.showerror(APP_NAME, "Enter the YouTube Data API key.", parent=dialog)
                return
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                messagebox.showerror(APP_NAME, "Enter a valid delivery email address.", parent=dialog)
                return
            self.store.save_settings(key, email)
            self.settings = self.store.load_settings()
            dialog.destroy()

        buttons = tk.Frame(frame, bg=PANEL)
        buttons.pack(fill="x", padx=24)
        self._button(buttons, "SAVE SETTINGS", save, primary=True, compact=True).pack(side="left")
        self._button(buttons, "CANCEL", dialog.destroy, compact=True).pack(side="left", padx=8)

    def _close(self) -> None:
        self.preview_server.stop()
        self.destroy()


def smoke_test() -> None:
    required = [
        resource_path("templates/machine.html"),
        resource_path("static/base-machine.css"),
        resource_path("static/video-machine.css"),
        resource_path("static/video-machine.js"),
        resource_path("static/music-machine/aggits-cabinet.webp"),
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing packaged resources: {missing}")
    print("Video Jukebox Factory resources OK")


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        smoke_test()
    else:
        Factory().mainloop()
