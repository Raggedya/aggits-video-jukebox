from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import application_data_root
from .credentials import protect, unprotect
from .models import Project, utc_now


def slugify(value: str) -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return normalized[:72] or "video-jukebox"


class ProjectStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or application_data_root()
        self.projects_dir = self.root / "projects"
        self.workspace_dir = self.root / "publisher-workspace"
        self.archive_dir = self.root / "workspace-archive"
        self.settings_path = self.root / "settings.json"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def project_dir(self, slug: str) -> Path:
        safe = slugify(slug)
        return self.projects_dir / safe

    def save_project(self, project: Project) -> None:
        project.updated_at = utc_now()
        directory = self.project_dir(project.slug)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "project.json"
        temporary = directory / ".project.json.tmp"
        temporary.write_text(json.dumps(project.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)

    def load_project(self, slug: str) -> Project:
        path = self.project_dir(slug) / "project.json"
        return Project.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_projects(self) -> list[Project]:
        projects: list[Project] = []
        for path in self.projects_dir.glob("*/project.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                projects.append(Project.from_dict(value))
            except (OSError, ValueError, TypeError):
                continue
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def load_settings(self) -> dict[str, Any]:
        if not self.settings_path.is_file():
            return {"deliveryEmail": "andrewharris501@gmail.com", "youtubeApiKey": ""}
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"deliveryEmail": "andrewharris501@gmail.com", "youtubeApiKey": ""}
        encrypted = str(value.get("youtubeApiKeyProtected") or "")
        try:
            key = unprotect(encrypted) if encrypted else ""
        except (OSError, ValueError, RuntimeError):
            key = ""
        return {
            "deliveryEmail": str(value.get("deliveryEmail") or "andrewharris501@gmail.com"),
            "youtubeApiKey": key,
        }

    def save_settings(self, youtube_api_key: str, delivery_email: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "youtubeApiKeyProtected": protect(youtube_api_key.strip()),
            "deliveryEmail": delivery_email.strip().lower(),
        }
        temporary = self.root / ".settings.json.tmp"
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.settings_path)
