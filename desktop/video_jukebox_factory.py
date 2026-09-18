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

from aggits_video_factory.config import APP_NAME, APP_VERSION, MAX_TICKER_LENGTH, MAX_VIDEOS, resource_path
from aggits_video_factory.business_workflow import assemble_reviewed_project
from aggits_video_factory.delivery import (
    DeliveryError,
    delivery_intent_matches,
    mark_delivery_attempt,
    mark_delivery_failure,
    mark_delivery_result,
    request_delivery,
)
from aggits_video_factory.diagnostics import configure_logging, log_directory, open_log_folder
from aggits_video_factory.desktop_forms import (
    CTA_CHOICES,
    DEFAULT_CTA_LABEL,
    FormValidationError,
    ProjectFormValues,
    project_is_visible_in_tab,
    project_to_form_values,
    validate_project_form,
)
from aggits_video_factory.models import Project, ProjectType, utc_now
from aggits_video_factory.preview import PreviewServer
from aggits_video_factory.publisher import PublicationVerificationPending, PublishError, Publisher, UnpublishVerificationPending
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.supplementary_sources import retrieve_supplementary_sources
from aggits_video_factory.youtube_api import YouTubeClient, YouTubeError, merge_video_selections


INK = "#111318"
PANEL = "#191c22"
PANEL_2 = "#22262e"
CREAM = "#d9dee8"
PAPER = "#f5f7fb"
MUTED = "#9199a8"
BRASS = "#72a1ff"
DEEP_BRASS = "#343b49"
ACTIVE = "#315a9c"
SUCCESS = "#7fc6a4"
ERROR = "#ef9292"
DESKTOP_TITLE = APP_NAME


class ProjectForm(tk.Frame):
    def __init__(self, parent: tk.Misc, project_type: ProjectType, submit, new_project) -> None:
        super().__init__(parent, bg=PANEL)
        self.project_type = project_type
        self.submit_callback = submit
        self.new_callback = new_project
        self.editing_project_id: str | None = None
        self._baseline = ProjectFormValues().comparable()
        self._manual_open = False
        self._build()
        self.clear_new()

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        heading = tk.Frame(self, bg=PANEL)
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", padx=22, pady=(18, 14))
        self.mode_label = tk.Label(heading, text="NEW BUSINESS PROJECT", bg=PANEL, fg=PAPER, font=("Segoe UI Semibold", 15))
        self.mode_label.pack(side="left")
        tk.Button(
            heading, text="NEW PROJECT", command=self.new_callback, bg=PANEL_2, fg=CREAM,
            activebackground="#303641", activeforeground=PAPER, relief="flat", bd=0,
            font=("Segoe UI Semibold", 9), padx=12, pady=7, cursor="hand2",
        ).pack(side="right")

        self.title_var = tk.StringVar()
        self.channel_var = tk.StringVar()
        self.additional_vars = [tk.StringVar() for _ in range(3)]
        self.shop_var = tk.StringVar()
        self.cta_var = tk.StringVar(value=DEFAULT_CTA_LABEL)
        self.destination_var = tk.StringVar()
        self.custom_label_var = tk.StringVar()
        self.field_widgets: dict[str, tk.Widget] = {}
        row = 1
        row = self._entry_row(row, "Title", self.title_var, "title")
        row = self._entry_row(row, "YouTube Channel URL", self.channel_var, "channel_url")
        for index, variable in enumerate(self.additional_vars, start=1):
            row = self._entry_row(row, f"Additional URL {index}", variable, "additional_urls")

        if self.project_type is ProjectType.BUSINESS:
            row = self._entry_row(row, "Shop URL", self.shop_var, "shop_url")
        else:
            tk.Label(self, text="Primary Call to Action", bg=PANEL, fg=CREAM, anchor="e", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=(22, 12), pady=5)
            self.cta_combo = ttk.Combobox(self, textvariable=self.cta_var, values=[label for label, _ in CTA_CHOICES], state="readonly", font=("Segoe UI", 10))
            self.cta_combo.grid(row=row, column=1, sticky="ew", padx=(0, 22), pady=5, ipady=3)
            self.cta_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_custom_visibility())
            self.field_widgets["cta_type"] = self.cta_combo
            row += 1
            row = self._entry_row(row, "Destination URL", self.destination_var, "destination_url")
            self.custom_row = row
            row = self._entry_row(row, "Button Label", self.custom_label_var, "custom_label")

        tk.Label(self, text="Bio / Story Information", bg=PANEL, fg=CREAM, anchor="ne", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="ne", padx=(22, 12), pady=(8, 5))
        story_shell = tk.Frame(self, bg=PANEL)
        story_shell.grid(row=row, column=1, sticky="ew", padx=(0, 22), pady=(5, 3))
        story_shell.columnconfigure(0, weight=1)
        self.story_text = tk.Text(story_shell, height=4, wrap="word", bg="#101217", fg=PAPER, insertbackground=PAPER, relief="flat", bd=0, highlightbackground=DEEP_BRASS, highlightthickness=1, font=("Segoe UI", 10), padx=9, pady=7)
        self.story_text.grid(row=0, column=0, sticky="ew")
        self.story_text.bind("<KeyRelease>", self._story_changed)
        self.story_count = tk.Label(story_shell, text=f"0 / {MAX_TICKER_LENGTH}", bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.story_count.grid(row=1, column=0, sticky="e", pady=(3, 0))
        self.field_widgets["story_text"] = self.story_text
        row += 1

        self.manual_toggle = tk.Button(
            self, text="▸  Individual YouTube Videos (Optional)", command=self._toggle_manual,
            bg=PANEL_2, fg=CREAM, activebackground="#303641", activeforeground=PAPER,
            relief="flat", bd=0, anchor="w", font=("Segoe UI Semibold", 9), padx=11, pady=8, cursor="hand2",
        )
        self.manual_toggle.grid(row=row, column=0, columnspan=2, sticky="ew", padx=22, pady=(10, 4))
        row += 1
        self.manual_shell = tk.Frame(self, bg="#12151a", highlightbackground=DEEP_BRASS, highlightthickness=1, height=132)
        self.manual_shell.grid(row=row, column=0, columnspan=2, sticky="ew", padx=22, pady=(0, 6))
        self.manual_shell.pack_propagate(False)
        canvas = tk.Canvas(self.manual_shell, bg="#12151a", bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.manual_shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        rows = tk.Frame(canvas, bg="#12151a")
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        rows.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        self.manual_vars = [tk.StringVar() for _ in range(15)]
        self.manual_entries: list[tk.Entry] = []
        for index, variable in enumerate(self.manual_vars, start=1):
            item = tk.Frame(rows, bg="#12151a")
            item.pack(fill="x", padx=8, pady=(7 if index == 1 else 2, 2))
            tk.Label(item, text=f"{index:02d}", width=3, bg="#12151a", fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
            entry = tk.Entry(item, textvariable=variable, bg="#0d0f13", fg=PAPER, insertbackground=PAPER, relief="flat", bd=0, highlightbackground=DEEP_BRASS, highlightthickness=1, font=("Segoe UI", 9))
            entry.pack(side="left", fill="x", expand=True, ipady=5)
            self.manual_entries.append(entry)
        self.field_widgets["manual_video_urls"] = self.manual_entries[0]
        row += 1

        self.validation_label = tk.Label(self, text="", bg=PANEL, fg=ERROR, anchor="w", justify="left", font=("Segoe UI Semibold", 8))
        self.validation_label.grid(row=row, column=0, columnspan=2, sticky="ew", padx=22, pady=(3, 1))
        row += 1
        actions = tk.Frame(self, bg=PANEL)
        actions.grid(row=row, column=0, columnspan=2, sticky="ew", padx=22, pady=(7, 18))
        self.submit_button = tk.Button(
            actions, command=self.submit_callback, bg=ACTIVE, fg=PAPER, activebackground="#3e6cb5",
            activeforeground=PAPER, relief="flat", bd=0, font=("Segoe UI Semibold", 10), padx=18, pady=10, cursor="hand2",
        )
        self.submit_button.pack(side="left")
        self.stage_note = tk.Label(actions, bg=PANEL, fg=MUTED, anchor="w", justify="left", font=("Segoe UI", 8))
        self.stage_note.pack(side="left", padx=14)
        self._toggle_manual(force=False)
        self._update_custom_visibility()

    def _entry_row(self, row: int, label: str, variable: tk.StringVar, field_name: str) -> int:
        tk.Label(self, text=label, bg=PANEL, fg=CREAM, anchor="e", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=(22, 12), pady=5)
        entry = tk.Entry(self, textvariable=variable, bg="#101217", fg=PAPER, insertbackground=PAPER, relief="flat", bd=0, highlightbackground=DEEP_BRASS, highlightthickness=1, font=("Segoe UI", 10))
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 22), pady=5, ipady=7)
        self.field_widgets[field_name] = entry
        return row + 1

    def _story_changed(self, _event=None) -> None:
        value = self.story_text.get("1.0", "end-1c")
        if len(value) > MAX_TICKER_LENGTH:
            value = value[:MAX_TICKER_LENGTH]
            self.story_text.delete("1.0", "end")
            self.story_text.insert("1.0", value)
        self.story_count.configure(text=f"{len(value)} / {MAX_TICKER_LENGTH}", fg=ERROR if len(value) >= MAX_TICKER_LENGTH else MUTED)

    def _toggle_manual(self, force: bool | None = None) -> None:
        self._manual_open = (not self._manual_open) if force is None else force
        if self._manual_open:
            self.manual_shell.grid()
            self.manual_toggle.configure(text="▾  Individual YouTube Videos (Optional)")
        else:
            self.manual_shell.grid_remove()
            self.manual_toggle.configure(text="▸  Individual YouTube Videos (Optional)")

    def _update_custom_visibility(self) -> None:
        if self.project_type is not ProjectType.MUSIC:
            return
        label = self.cta_var.get()
        widget = self.field_widgets["custom_label"]
        if label == "Custom":
            widget.grid()
            for child in self.grid_slaves(row=self.custom_row, column=0):
                child.grid()
        else:
            widget.grid_remove()
            for child in self.grid_slaves(row=self.custom_row, column=0):
                child.grid_remove()
            self.custom_label_var.set("")

    def values(self) -> ProjectFormValues:
        return ProjectFormValues(
            title=self.title_var.get(),
            channel_url=self.channel_var.get(),
            additional_urls=[variable.get() for variable in self.additional_vars],
            story_text=self.story_text.get("1.0", "end-1c"),
            manual_video_urls=[variable.get() for variable in self.manual_vars],
            shop_url=self.shop_var.get() if self.project_type is ProjectType.BUSINESS else "",
            cta_label=self.cta_var.get() if self.project_type is ProjectType.MUSIC else DEFAULT_CTA_LABEL,
            destination_url=self.destination_var.get() if self.project_type is ProjectType.MUSIC else "",
            custom_label=self.custom_label_var.get() if self.project_type is ProjectType.MUSIC else "",
        )

    def set_values(self, values: ProjectFormValues) -> None:
        self.title_var.set(values.title)
        self.channel_var.set(values.channel_url)
        for variable, value in zip(self.additional_vars, [*values.additional_urls, "", "", ""][:3]):
            variable.set(value)
        self.shop_var.set(values.shop_url)
        self.cta_var.set(values.cta_label or DEFAULT_CTA_LABEL)
        self.destination_var.set(values.destination_url)
        self.custom_label_var.set(values.custom_label)
        for variable, value in zip(self.manual_vars, [*values.manual_video_urls, *("" for _ in range(15))][:15]):
            variable.set(value)
        self.story_text.delete("1.0", "end")
        self.story_text.insert("1.0", values.story_text)
        self._story_changed()
        self._toggle_manual(force=bool([url for url in values.manual_video_urls if url]))
        self._update_custom_visibility()
        self.clear_validation()

    def clear_new(self) -> None:
        self.editing_project_id = None
        self.set_values(ProjectFormValues())
        name = "BUSINESS" if self.project_type is ProjectType.BUSINESS else "MUSIC"
        self.mode_label.configure(text=f"NEW {name} PROJECT")
        if self.project_type is ProjectType.BUSINESS:
            self.submit_button.configure(text="CREATE CRISPY BITS")
            self.stage_note.configure(text="Analyse and review videos, then build locally.")
        else:
            self.submit_button.configure(text="CREATE CRISPY BITS")
            self.stage_note.configure(text="Analyse and review videos, then build locally.")
        self.mark_clean()

    def load_project(self, project: Project) -> None:
        self.editing_project_id = project.id
        self.set_values(project_to_form_values(project))
        self.mode_label.configure(text=f"EDIT {project.project_type.value.upper()} PROJECT")
        self.submit_button.configure(text="SAVE CHANGES")
        self.stage_note.configure(text="Reviewed changes remain private until Update + Republish.")
        self.mark_clean()

    def mark_clean(self) -> None:
        self._baseline = self.values().comparable()

    def is_dirty(self) -> bool:
        return self.values().comparable() != self._baseline

    def restore_baseline(self) -> None:
        values = ProjectFormValues(
            title=str(self._baseline[0]), channel_url=str(self._baseline[1]), additional_urls=list(self._baseline[2]),
            story_text=str(self._baseline[3]), manual_video_urls=list(self._baseline[4]), shop_url=str(self._baseline[5]),
            cta_label=str(self._baseline[6]), destination_url=str(self._baseline[7]), custom_label=str(self._baseline[8]),
        )
        self.set_values(values)
        self.mark_clean()

    def show_validation(self, error: FormValidationError) -> None:
        self.validation_label.configure(text=error.args[0])
        widget = self.field_widgets.get(error.field)
        if error.field == "manual_video_urls":
            self._toggle_manual(force=True)
        if widget:
            widget.focus_set()

    def clear_validation(self) -> None:
        self.validation_label.configure(text="")


class LibraryPanel(tk.Frame):
    def __init__(self, parent: tk.Misc, project_type: ProjectType, owner: "Factory") -> None:
        super().__init__(parent, bg=PANEL)
        self.project_type = project_type
        self.owner = owner
        heading = tk.Frame(self, bg=PANEL)
        heading.pack(fill="x", padx=18, pady=(18, 10))
        tk.Label(heading, text="LIBRARY", bg=PANEL, fg=PAPER, font=("Segoe UI Semibold", 15)).pack(side="left")
        self.count = tk.Label(heading, text="0 PROJECTS", bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.count.pack(side="right", pady=5)
        shell = tk.Frame(self, bg=PANEL)
        shell.pack(fill="both", expand=True, padx=18)
        columns = ("title", "status", "updated", "url")
        self.tree = ttk.Treeview(shell, columns=columns, show="headings", style="Factory.Treeview", selectmode="browse")
        for name, label, width in (("title", "TITLE", 205), ("status", "STATUS", 105), ("updated", "UPDATED", 135), ("url", "PUBLIC URL", 185)):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, minwidth=70, anchor="w")
        scroll = ttk.Scrollbar(shell, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: owner._update_actions())
        self.tree.bind("<Double-1>", lambda _event: owner._edit_selected())
        actions = tk.Frame(self, bg=PANEL)
        actions.pack(fill="x", padx=18, pady=(13, 8))
        self.buttons: dict[str, tk.Button] = {}
        action_specs = [
            ("edit", "EDIT", owner._edit_selected),
            ("preview", "PREVIEW", owner._preview_selected),
            ("publish", "PUBLISH", owner._publish_selected),
            ("unpublish", "UNPUBLISH", owner._unpublish_selected),
            ("open", "OPEN LIVE", owner._open_live),
            ("email", "RETRY EMAIL", owner._retry_email),
            ("verify", "CHECK LIVE STATUS", owner._check_live_status),
        ]
        for key, label, callback in action_specs:
            button = owner._button(actions, label, callback, compact=True, primary=key == "publish")
            button.pack(side="left", padx=(0, 7))
            self.buttons[key] = button
        self.note = tk.Label(self, text="Select a project to edit it.", bg=PANEL, fg=MUTED, anchor="w", font=("Segoe UI", 8))
        self.note.pack(fill="x", padx=18, pady=(0, 14))

    def selected_id(self) -> str | None:
        selected = self.tree.selection()
        return selected[0] if selected else None


class Factory(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(DESKTOP_TITLE)
        self.geometry("1320x820")
        self.minsize(1120, 720)
        self.configure(bg=INK)
        self.store = ProjectStore()
        self.logger = configure_logging(self.store.root)
        self.logger.info("Application startup")
        self.preview_server = PreviewServer()
        self.settings = self.store.load_settings()
        self.busy = False
        self.projects: dict[str, Project] = {}
        self.forms: dict[ProjectType, ProjectForm] = {}
        self.libraries: dict[ProjectType, LibraryPanel] = {}
        self.active_project_type = ProjectType.BUSINESS
        self._tab_change_guard = False
        self._reported_project_load_errors: tuple[tuple[str, str], ...] = ()
        self._configure_styles()
        self._build()
        self._refresh_library()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Factory.Treeview", background="#12151a", foreground=CREAM, fieldbackground="#12151a", bordercolor=DEEP_BRASS, rowheight=32, font=("Segoe UI", 9))
        style.map("Factory.Treeview", background=[("selected", "#294d86")], foreground=[("selected", PAPER)])
        style.configure("Factory.Treeview.Heading", background=PANEL_2, foreground=CREAM, relief="flat", font=("Segoe UI Semibold", 8))
        style.configure("Factory.Vertical.TScrollbar", background=DEEP_BRASS, troughcolor=INK, bordercolor=INK, arrowcolor=CREAM)
        style.configure("Desktop.TNotebook", background=INK, borderwidth=0, tabmargins=(18, 6, 0, 0))
        style.configure("Desktop.TNotebook.Tab", background=PANEL_2, foreground=MUTED, padding=(22, 10), font=("Segoe UI Semibold", 10), borderwidth=0)
        style.map("Desktop.TNotebook.Tab", background=[("selected", ACTIVE)], foreground=[("selected", PAPER)])
        style.configure("TCombobox", fieldbackground="#101217", background=PANEL_2, foreground=PAPER, arrowcolor=CREAM)

    def _build(self) -> None:
        header = tk.Frame(self, bg=INK, height=66)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="CRISPY BITS", bg=INK, fg=PAPER, font=("Segoe UI Semibold", 18)).pack(side="left", padx=(22, 12), pady=14)
        title = tk.Frame(header, bg=INK)
        title.pack(side="left", pady=14)
        tk.Label(title, text="DESKTOP", bg=INK, fg=BRASS, font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Label(title, text="Project management", bg=INK, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))
        self.settings_button = self._button(header, "SETTINGS", self._open_settings, compact=True)
        self.settings_button.pack(side="right", padx=22, pady=15)

        self.notebook = ttk.Notebook(self, style="Desktop.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.tab_types: list[ProjectType] = [ProjectType.BUSINESS, ProjectType.MUSIC]
        for project_type in self.tab_types:
            page = tk.Frame(self.notebook, bg=INK)
            self.notebook.add(page, text=project_type.value.upper())
            body = tk.PanedWindow(page, orient="horizontal", bg=INK, sashwidth=7, sashrelief="flat", bd=0)
            body.pack(fill="both", expand=True, padx=7, pady=10)
            form_shell = tk.Frame(body, bg=PANEL, highlightbackground=DEEP_BRASS, highlightthickness=1)
            library_shell = tk.Frame(body, bg=PANEL, highlightbackground=DEEP_BRASS, highlightthickness=1)
            body.add(form_shell, minsize=510, width=610)
            body.add(library_shell, minsize=520)
            form_canvas = tk.Canvas(form_shell, bg=PANEL, bd=0, highlightthickness=0)
            form_scrollbar = ttk.Scrollbar(form_shell, orient="vertical", command=form_canvas.yview)
            form_canvas.configure(yscrollcommand=form_scrollbar.set)
            form_scrollbar.pack(side="right", fill="y")
            form_canvas.pack(side="left", fill="both", expand=True)
            form = ProjectForm(
                form_canvas,
                project_type,
                submit=lambda kind=project_type: self._submit_project(kind),
                new_project=lambda kind=project_type: self._new_project(kind),
            )
            form_window = form_canvas.create_window((0, 0), window=form, anchor="nw")
            form.bind("<Configure>", lambda _event, canvas=form_canvas: canvas.configure(scrollregion=canvas.bbox("all")))
            form_canvas.bind("<Configure>", lambda event, canvas=form_canvas, window=form_window: canvas.itemconfigure(window, width=event.width))
            form_canvas.bind("<Enter>", lambda _event, canvas=form_canvas: canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units")))
            form_canvas.bind("<Leave>", lambda _event, canvas=form_canvas: canvas.unbind_all("<MouseWheel>"))
            library = LibraryPanel(library_shell, project_type, self)
            library.pack(fill="both", expand=True)
            self.forms[project_type] = form
            self.libraries[project_type] = library
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.status = tk.Label(self, text="READY", bg="#0b0d11", fg=MUTED, anchor="w", padx=18, font=("Segoe UI Semibold", 8))
        self.status.pack(fill="x", side="bottom", ipady=7)

    def _button(self, parent: tk.Misc, text: str, command, *, primary: bool = False, compact: bool = False) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACTIVE if primary else PANEL_2,
            fg=PAPER if primary else CREAM,
            activebackground="#3e6cb5" if primary else "#303641",
            activeforeground=PAPER,
            disabledforeground="#626978",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 9 if compact else 10),
            padx=12 if compact else 22,
            pady=8 if compact else 12,
        )

    def _selected_project(self) -> Project | None:
        selected_id = self.libraries[self.active_project_type].selected_id()
        return self.projects.get(selected_id) if selected_id else None

    def _refresh_library(self, select_id: str | None = None) -> None:
        projects = self.store.list_projects()
        errors = tuple((str(issue.path), issue.message) for issue in self.store.last_load_errors)
        if errors and errors != self._reported_project_load_errors:
            self._reported_project_load_errors = errors
            detail = "\n\n".join(f"{path}\n{message}" for path, message in errors)
            self.logger.warning("Project load warnings count=%s", len(errors))
            self.after_idle(lambda: messagebox.showwarning(
                DESKTOP_TITLE,
                "One or more saved projects could not be loaded. Their source files were left unchanged.\n\n" + detail,
            ))
        self.projects = {project.id: project for project in projects}
        for project_type, panel in self.libraries.items():
            panel.tree.delete(*panel.tree.get_children())
            visible = [project for project in projects if project_is_visible_in_tab(project, project_type)]
            for project in visible:
                updated = project.updated_at.replace("T", " ").replace("Z", "")[:16]
                public_url = project.published_url or "—"
                panel.tree.insert("", "end", iid=project.id, values=(project.title, project.status.replace("_", " ").title(), updated, public_url))
            panel.count.configure(text=f"{len(visible)} PROJECT{'S' if len(visible) != 1 else ''}")
        if select_id and select_id in self.projects:
            project = self.projects[select_id]
            panel = self.libraries[project.project_type]
            panel.tree.selection_set(select_id)
            panel.tree.focus(select_id)
            panel.tree.see(select_id)
        self._update_actions()

    def _update_actions(self) -> None:
        for project_type, panel in self.libraries.items():
            selected_id = panel.selected_id()
            project = self.projects.get(selected_id) if selected_id else None
            allowed = project is not None and not self.busy
            pending = bool(
                project
                and (
                    project.status in {"verification_pending", "unpublish_verification_pending"}
                    or (project.publication_operation and project.publication_operation.verification_status == "pending")
                )
            )
            panel.buttons["edit"].configure(state="normal" if allowed and not pending else "disabled")
            panel.buttons["preview"].configure(state="normal" if allowed else "disabled")
            panel.buttons["publish"].configure(state="normal" if allowed and project.status != "published" and not pending else "disabled")
            panel.buttons["publish"].configure(text="UPDATE + REPUBLISH" if project and project.status == "changes_pending" else "PUBLISH")
            panel.buttons["unpublish"].configure(state="normal" if allowed and bool(project.published_url) and not pending else "disabled")
            panel.buttons["open"].configure(state="normal" if allowed and bool(project.published_url) else "disabled")
            recipient = str(self.settings.get("deliveryEmail") or "")
            delivered_to_current = False
            if project and project.status == "published":
                try:
                    delivered_to_current = delivery_intent_matches(project, recipient)
                except DeliveryError:
                    pass
            panel.buttons["email"].configure(state="normal" if allowed and project.status == "published" and not delivered_to_current else "disabled")
            panel.buttons["verify"].configure(state="normal" if allowed and pending else "disabled")
            if project:
                status_label = {
                    "verification_pending": "Publication Verification Pending",
                    "unpublish_verification_pending": "Removal Verification Pending",
                }.get(project.status, project.status.replace("_", " ").title())
                delivery_label = {
                    "sent": "Delivered",
                    "already_delivered": "Delivered",
                    "unknown": "Delivery Pending",
                    "attempting": "Delivery Pending",
                    "failed": "Delivery Failed",
                }.get(project.delivery_status, project.delivery_status.replace("_", " ").title())
                recipient_detail = (
                    f" to {project.delivery_record.recipient}"
                    if project.delivery_record and project.delivery_record.recipient and project.delivery_record.revision == (project.publication_revision or "")
                    else ""
                )
                panel.note.configure(text=f"{project.title} · {len(project.videos)} videos · {status_label} · {delivery_label}{recipient_detail}")
            else:
                panel.note.configure(text=f"Select a {project_type.value.title()} project to edit, preview or publish it.")

    def _set_busy(self, busy: bool, message: str) -> None:
        self.busy = busy
        self.status.configure(text=message, fg=BRASS if busy else MUTED)
        for form in self.forms.values():
            form.submit_button.configure(state="disabled" if busy else "normal")
        self.settings_button.configure(state="disabled" if busy else "normal")
        self._update_actions()

    def _edit_selected(self) -> None:
        project = self._selected_project()
        if not project or self.busy:
            return
        form = self.forms[project.project_type]
        if form.is_dirty() and not self._resolve_unsaved(form, "open another project"):
            return
        form.load_project(project)
        form.field_widgets["title"].focus_set()

    def _new_project(self, project_type: ProjectType) -> None:
        form = self.forms[project_type]
        if self.busy:
            return
        if form.is_dirty() and not self._resolve_unsaved(form, "start a new project"):
            return
        form.clear_new()
        form.field_widgets["title"].focus_set()

    def _submit_project(self, project_type: ProjectType) -> bool:
        if self.busy:
            return False
        return self._create_jukebox(project_type)

    def _resolve_unsaved(self, form: ProjectForm, action: str) -> bool:
        choice = messagebox.askyesnocancel(
            "Unsaved changes",
            f"Save the current {form.project_type.value.title()} project changes before you {action}?\n\nYes = Save    No = Discard    Cancel = Stay here",
        )
        if choice is None:
            return False
        if choice:
            return self._submit_project(form.project_type)
        form.restore_baseline()
        return True

    def _on_tab_changed(self, _event=None) -> None:
        if self._tab_change_guard or not hasattr(self, "notebook"):
            return
        target = self.tab_types[self.notebook.index(self.notebook.select())]
        previous = self.active_project_type
        if target is previous:
            return
        form = self.forms[previous]
        if form.is_dirty() and not self._resolve_unsaved(form, "switch tabs"):
            self._tab_change_guard = True
            self.notebook.select(self.tab_types.index(previous))
            self._tab_change_guard = False
            return
        self.active_project_type = target
        self._update_actions()

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
        self.logger.error("Operation paused type=%s error=%s", type(error).__name__, error)
        if isinstance(error, (PublicationVerificationPending, UnpublishVerificationPending)):
            self._refresh_library(error.project.id)
            messagebox.showwarning(DESKTOP_TITLE, f"{error}\n\nNo second Git operation was attempted. Use CHECK LIVE STATUS to reconcile it.\n\nDiagnostics: {log_directory(self.store.root)}")
            return
        if isinstance(error, (PublishError, DeliveryError)):
            self._refresh_library()
        messagebox.showerror(DESKTOP_TITLE, f"{error}\n\nDiagnostics: {log_directory(self.store.root)}")

    def _async_complete(self, result, complete) -> None:
        self._set_busy(False, "READY")
        complete(result)

    def _create_jukebox(self, project_type: ProjectType) -> bool:
        form = self.forms[project_type]
        form.clear_validation()
        try:
            values = validate_project_form(form.values(), project_type)
        except FormValidationError as error:
            form.show_validation(error)
            return False
        api_key = str(self.settings.get("youtubeApiKey") or "")
        if not api_key:
            messagebox.showinfo(DESKTOP_TITLE, "Save a YouTube Data API key in SETTINGS once, then press Create Jukebox again.")
            self._open_settings()
            return False

        editing_project_id = form.editing_project_id
        existing = self.projects.get(editing_project_id) if editing_project_id else None
        if existing and existing.project_type is not project_type:
            messagebox.showerror(DESKTOP_TITLE, "A saved project cannot be changed to a different project type.")
            return False
        slug = existing.slug if existing else self.store.allocate_slug(values.title)

        def worker() -> dict[str, object]:
            client = YouTubeClient(api_key)
            manual_catalogue = client.fetch_videos(values.manual_video_urls) if values.manual_video_urls else None
            channel_catalogue = client.fetch_catalogue(values.channel_url, MAX_VIDEOS) if values.channel_url else None
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
            source_results = retrieve_supplementary_sources(values.additional_urls)
            return {
                "slug": slug,
                "project_type": project_type,
                "values": values,
                "catalogue": catalogue,
                "videos": videos,
                "manual_ids": {video.video_id for video in (manual_catalogue.videos if manual_catalogue else [])},
                "editing_project_id": editing_project_id,
                "excluded_ids": set(existing.excluded_video_ids) if existing else set(),
                "source_results": source_results,
                "thumbnails": thumbnail_bytes,
            }

        self._run_async("READING YOUTUBE + PREPARING VIDEO REVIEW…", worker, self._review_video_selection)
        return False

    def _review_video_selection(self, candidate: dict[str, object]) -> None:
        videos = list(candidate["videos"])
        manual_ids = set(candidate["manual_ids"])
        excluded_ids = set(candidate.get("excluded_ids") or set())
        thumbnail_bytes = dict(candidate["thumbnails"])
        source_failures = [result for result in candidate.get("source_results", []) if not result.succeeded]
        if source_failures:
            project_type = ProjectType(candidate.get("project_type", ProjectType.BUSINESS))
            detail = "\n".join(f"• {result.url}\n  {result.error}" for result in source_failures)
            messagebox.showwarning(
                DESKTOP_TITLE,
                f"One or more optional Additional URLs could not be read. You can still review and build this {project_type.value.title()} project.\n\n" + detail,
                parent=self,
            )
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
                messagebox.showerror(DESKTOP_TITLE, "Include at least one video before building the jukebox.", parent=dialog)
                return
            canvas.unbind_all("<MouseWheel>")
            dialog.destroy()
            self._finish_jukebox(candidate, selected)

        def cancel_review() -> None:
            canvas.unbind_all("<MouseWheel>")
            dialog.destroy()

        self._button(footer, "SELECT ALL", lambda: set_all(True), compact=True).pack(side="left", padx=(0, 6))
        self._button(footer, "CLEAR ALL", lambda: set_all(False), compact=True).pack(side="left")
        build_label = "SAVE REVIEWED CHANGES" if candidate.get("editing_project_id") else "BUILD JUKEBOX"
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
        values = candidate["values"]
        project_type = ProjectType(candidate.get("project_type", ProjectType.BUSINESS))

        def worker() -> Project:
            self.logger.info("Build started slug=%s type=%s", slug, project_type.value)
            editing_project_id = str(candidate.get("editing_project_id") or "")
            existing = self.projects.get(editing_project_id) if editing_project_id else None
            project = assemble_reviewed_project(
                project_type=project_type,
                values=values,
                catalogue=catalogue,
                selected_videos=videos,
                reviewed_videos=list(candidate["videos"]),
                source_results=list(candidate.get("source_results", [])),
                slug=slug,
                existing=existing,
            )
            project_dir = self.store.project_dir(slug)
            build_project_site(project, project_dir / "site")
            self.store.save_project(project)
            self.logger.info("Build completed slug=%s videos=%s", project.slug, len(project.videos))
            return project

        self._run_async("BUILDING THE REVIEWED JUKEBOX…", worker, self._create_complete)

    def _create_complete(self, project: Project) -> None:
        self._refresh_library(project.id)
        editing = project.status == "changes_pending"
        self.forms[project.project_type].load_project(project)
        self._open_project_preview(project)
        if editing:
            messagebox.showinfo(DESKTOP_TITLE, f"{project.title} now has {len(project.videos)} reviewed videos and its local preview has opened.\n\nThe existing live jukebox is unchanged. Press UPDATE + REPUBLISH in the Library when you are ready.")
        else:
            messagebox.showinfo(DESKTOP_TITLE, f"{project.title} was created with {len(project.videos)} videos and its local preview has opened.\n\nIt is private until you press PUBLISH in the Library.")

    def _open_project_preview(self, project: Project) -> bool:
        site = self.store.project_dir(project.slug) / "site"
        if not (site / "index.html").is_file():
            messagebox.showerror(DESKTOP_TITLE, "The local preview files are missing. Recreate the jukebox.")
            return False
        webbrowser.open(self.preview_server.start(site))
        return True

    def _preview_selected(self) -> None:
        project = self._selected_project()
        if not project:
            return
        self._open_project_preview(project)

    def _publish_selected(self) -> None:
        project = self._selected_project()
        if not project:
            return
        question = f"Update and republish {project.title}?" if project.status == "changes_pending" else f"Publish {project.title} to the public CRISPY BITS Video Jukebox library?"
        if not messagebox.askyesno("Publish jukebox", question):
            return

        def worker() -> tuple[Project, str | None]:
            public_url, revision = Publisher(self.store).publish(project)
            project.status = "published"
            project.published_url = public_url
            project.published_at = utc_now()
            project.publication_revision = revision
            project.delivery_status = "not_requested"
            self.store.save_project(project)
            build_project_site(project, self.store.project_dir(project.slug) / "site")
            email_error = None
            recipient = str(self.settings.get("deliveryEmail") or "")
            try:
                mark_delivery_attempt(project, recipient)
                self.store.save_project(project)
                result = request_delivery(project, recipient, secret=str(self.settings.get("deliverySecret") or ""))
                mark_delivery_result(project, recipient, result)
            except DeliveryError as error:
                try:
                    mark_delivery_failure(project, recipient, error)
                except DeliveryError:
                    project.delivery_status = "failed"
                email_error = str(error)
            self.store.save_project(project)
            return project, email_error

        self._run_async("PUBLISHING + WAITING FOR THE LIVE JUKEBOX…", worker, self._publish_complete)

    def _publish_complete(self, result: tuple[Project, str | None]) -> None:
        project, email_error = result
        self._refresh_library(project.id)
        detail = f"{project.title} is public:\n\n{project.published_url}"
        if email_error:
            detail += f"\n\nThe link and QR email remains queued:\n{email_error}"
        else:
            detail += f"\n\nThe link and titled QR card were emailed to {self.settings.get('deliveryEmail')}."
        messagebox.showinfo(DESKTOP_TITLE, detail)

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
        self._refresh_library(project.id)
        messagebox.showinfo(DESKTOP_TITLE, f"{project.title} is no longer public. Its private project remains in the Library.")

    def _open_live(self) -> None:
        project = self._selected_project()
        if project and project.published_url:
            webbrowser.open(project.published_url)

    def _retry_email(self) -> None:
        project = self._selected_project()
        if not project:
            return

        def worker() -> Project:
            recipient = str(self.settings.get("deliveryEmail") or "")
            try:
                mark_delivery_attempt(project, recipient)
                self.store.save_project(project)
                result = request_delivery(project, recipient, secret=str(self.settings.get("deliverySecret") or ""))
                mark_delivery_result(project, recipient, result)
            except DeliveryError as error:
                try:
                    mark_delivery_failure(project, recipient, error)
                finally:
                    self.store.save_project(project)
                raise
            self.store.save_project(project)
            return project

        self._run_async("SENDING THE LINK + QR EMAIL…", worker, self._email_complete)

    def _email_complete(self, project: Project) -> None:
        self._refresh_library(project.id)
        messagebox.showinfo(DESKTOP_TITLE, f"The {project.title} link and QR card were emailed to {self.settings.get('deliveryEmail')}.")

    def _check_live_status(self) -> None:
        project = self._selected_project()
        if not project:
            return

        def worker() -> tuple[Project, str | None]:
            state = Publisher(self.store).reconcile(project)
            delivery_error = None
            if state == "published":
                recipient = str(self.settings.get("deliveryEmail") or "")
                try:
                    if not delivery_intent_matches(project, recipient):
                        mark_delivery_attempt(project, recipient)
                        self.store.save_project(project)
                        result = request_delivery(project, recipient, secret=str(self.settings.get("deliverySecret") or ""))
                        mark_delivery_result(project, recipient, result)
                except DeliveryError as error:
                    try:
                        mark_delivery_failure(project, recipient, error)
                    except DeliveryError:
                        project.delivery_status = "failed"
                    delivery_error = str(error)
                self.store.save_project(project)
            return project, delivery_error

        self._run_async("CHECKING LIVE PUBLICATION STATUS…", worker, self._reconcile_complete)

    def _reconcile_complete(self, result: tuple[Project, str | None]) -> None:
        project, delivery_error = result
        self._refresh_library(project.id)
        if project.status == "published":
            detail = f"{project.title} is verified as published."
            if delivery_error:
                detail += f"\n\nDelivery still needs attention:\n{delivery_error}"
        else:
            detail = f"{project.title} is verified as unpublished. Its private project remains in the Library."
        messagebox.showinfo(DESKTOP_TITLE, detail)

    def _open_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(f"{DESKTOP_TITLE} — Settings")
        dialog.geometry("650x430")
        dialog.resizable(False, False)
        dialog.configure(bg=INK)
        dialog.transient(self)
        dialog.grab_set()
        frame = tk.Frame(dialog, bg=PANEL, highlightbackground=DEEP_BRASS, highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=22, pady=22)
        tk.Label(frame, text="SETTINGS", bg=PANEL, fg=PAPER, font=("Segoe UI Semibold", 16)).pack(anchor="w", padx=24, pady=(24, 8))
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
                messagebox.showerror(DESKTOP_TITLE, "Enter the YouTube Data API key.", parent=dialog)
                return
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                messagebox.showerror(DESKTOP_TITLE, "Enter a valid delivery email address.", parent=dialog)
                return
            self.store.save_settings(key, email)
            self.settings = self.store.load_settings()
            dialog.destroy()

        buttons = tk.Frame(frame, bg=PANEL)
        buttons.pack(fill="x", padx=24)
        self._button(buttons, "SAVE SETTINGS", save, primary=True, compact=True).pack(side="left")
        self._button(buttons, "CANCEL", dialog.destroy, compact=True).pack(side="left", padx=8)
        self._button(buttons, "OPEN LOG FOLDER", lambda: open_log_folder(self.store.root), compact=True).pack(side="right")

    def _close(self) -> None:
        if self.busy:
            messagebox.showinfo(DESKTOP_TITLE, "Please wait for the current operation to finish before closing CRISPY BITS DESKTOP.")
            return
        for form in self.forms.values():
            if form.is_dirty() and not self._resolve_unsaved(form, "close the application"):
                return
        self.preview_server.stop()
        self.destroy()


def smoke_test() -> None:
    required = [
        resource_path("templates/machine.html"),
        resource_path("static/base-machine.css"),
        resource_path("static/video-machine.css"),
        resource_path("static/video-machine.js"),
        resource_path("static/music-machine/aggits-cabinet.webp"),
        resource_path("static/music-machine/crispy-bits-logo-cutout-v2.png"),
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing packaged resources: {missing}")
    print(f"{APP_NAME} v{APP_VERSION} resources OK")


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        smoke_test()
    else:
        Factory().mainloop()
