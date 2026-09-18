from __future__ import annotations

import json
import os
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import application_data_root
from .credentials import protect, unprotect
from .diagnostics import configure_logging
from .migrations import CURRENT_PROJECT_SCHEMA_VERSION, LEGACY_PROJECT_SCHEMA_VERSION
from .models import Project, utc_now


def slugify(value: str) -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return normalized[:72] or "video-jukebox"


@dataclass(frozen=True, slots=True)
class ProjectLoadDiagnostic:
    path: Path
    message: str


class ProjectIdentityError(ValueError):
    pass


class ProjectStore:
    def __init__(self, root: Path | None = None) -> None:
        use_default_root = root is None
        self.root = root or application_data_root()
        self.projects_dir = self.root / "projects"
        self.workspace_dir = self.root / "publisher-workspace"
        self.archive_dir = self.root / "workspace-archive"
        self.settings_path = self.root / "settings.json"
        self.last_load_errors: list[ProjectLoadDiagnostic] = []
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.logger = configure_logging(self.root) if use_default_root else logging.getLogger("crispy_bits")

    def project_dir(self, slug: str) -> Path:
        safe = slugify(slug)
        return self.projects_dir / safe

    def allocate_slug(self, title: str) -> str:
        """Allocate a readable slug for a new local project without touching existing slugs."""
        base = slugify(title)
        candidate = base
        suffix = 2
        while self.project_dir(candidate).exists():
            suffix_text = f"-{suffix}"
            candidate = f"{base[: 72 - len(suffix_text)].rstrip('-')}{suffix_text}"
            suffix += 1
        return candidate

    @staticmethod
    def _stored_schema_version(path: Path) -> int | None:
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return int(value.get("schemaVersion", LEGACY_PROJECT_SCHEMA_VERSION)) if isinstance(value, dict) else None
        except (OSError, TypeError, ValueError):
            return None

    @staticmethod
    def _backup_legacy_project(path: Path, version: int) -> None:
        backup = path.with_name(f"project.json.v{version}.backup")
        if not backup.exists():
            shutil.copy2(path, backup)

    def save_project(self, project: Project) -> None:
        directory = self.project_dir(project.slug)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "project.json"
        stored_version = self._stored_schema_version(path)
        if path.is_file() and stored_version == CURRENT_PROJECT_SCHEMA_VERSION:
            try:
                stored_value = json.loads(path.read_text(encoding="utf-8"))
                stored_id = str(stored_value.get("id") or "")
            except (OSError, TypeError, ValueError) as error:
                raise ProjectIdentityError("The existing project identity could not be verified; its file was not changed.") from error
            if not stored_id or stored_id != project.id:
                raise ProjectIdentityError("An existing project's immutable id cannot be changed or replaced.")
        project.updated_at = utc_now()
        if stored_version is not None and stored_version < CURRENT_PROJECT_SCHEMA_VERSION:
            self._backup_legacy_project(path, stored_version)
        temporary = directory / ".project.json.tmp"
        temporary.write_text(json.dumps(project.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)

    def load_project(self, slug: str) -> Project:
        path = self.project_dir(slug) / "project.json"
        return Project.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_projects(self) -> list[Project]:
        projects: list[Project] = []
        self.last_load_errors = []
        for path in self.projects_dir.glob("*/project.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                projects.append(Project.from_dict(value))
            except (OSError, ValueError, TypeError) as error:
                self.last_load_errors.append(ProjectLoadDiagnostic(path=path, message=str(error)))
                self.logger.error("Project could not be loaded path=%s error=%s", path, error)
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def load_settings(self) -> dict[str, Any]:
        if not self.settings_path.is_file():
            return {"deliveryEmail": "andrewharris501@gmail.com", "youtubeApiKey": "", "deliverySecret": os.environ.get("CRISPY_BITS_DELIVERY_SECRET", "")}
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"deliveryEmail": "andrewharris501@gmail.com", "youtubeApiKey": "", "deliverySecret": os.environ.get("CRISPY_BITS_DELIVERY_SECRET", "")}
        encrypted = str(value.get("youtubeApiKeyProtected") or "")
        delivery_encrypted = str(value.get("deliverySecretProtected") or "")
        try:
            key = unprotect(encrypted) if encrypted else ""
        except (OSError, ValueError, RuntimeError):
            key = ""
        try:
            delivery_secret = unprotect(delivery_encrypted) if delivery_encrypted else ""
        except (OSError, ValueError, RuntimeError):
            delivery_secret = ""
        return {
            "deliveryEmail": str(value.get("deliveryEmail") or "andrewharris501@gmail.com"),
            "youtubeApiKey": key,
            "deliverySecret": os.environ.get("CRISPY_BITS_DELIVERY_SECRET", "") or delivery_secret,
        }

    def save_settings(self, youtube_api_key: str, delivery_email: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "youtubeApiKeyProtected": protect(youtube_api_key.strip()),
            "deliveryEmail": delivery_email.strip().lower(),
        }
        if self.settings_path.is_file():
            try:
                existing = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if existing.get("deliverySecretProtected"):
                    payload["deliverySecretProtected"] = existing["deliverySecretProtected"]
            except (OSError, ValueError, TypeError):
                pass
        temporary = self.root / ".settings.json.tmp"
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.settings_path)

    def save_delivery_secret(self, delivery_secret: str) -> None:
        secret = delivery_secret.strip()
        if not secret:
            raise ValueError("Delivery authentication secret cannot be empty.")
        payload: dict[str, Any] = {"schemaVersion": 1}
        if self.settings_path.is_file():
            try:
                current = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(current, dict):
                    payload.update(current)
            except (OSError, ValueError, TypeError):
                pass
        payload["deliverySecretProtected"] = protect(secret)
        temporary = self.root / ".settings.json.tmp"
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.settings_path)
