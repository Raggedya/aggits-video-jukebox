from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from .config import GITHUB_REMOTE, PUBLIC_BASE_URL, PUBLIC_PATH
from .models import Project, ProjectType, utc_now
from .store import ProjectStore, slugify


class PublishError(RuntimeError):
    pass


def _validate_project_type(project: Project) -> None:
    if project.project_type not in {ProjectType.BUSINESS, ProjectType.MUSIC}:
        raise PublishError(f"Unsupported project type: {project.project_type!r}.")


def _executable(name: str) -> str:
    located = shutil.which(name)
    if located:
        return located
    candidates: list[Path] = []
    if name.lower().startswith("git"):
        candidates.extend([
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "cmd" / "git.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "cmd" / "git.exe",
        ])
    elif name.lower().startswith("gh"):
        candidates.extend([
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "GitHub CLI" / "gh.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHub CLI" / "gh.exe",
        ])
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise PublishError(f"{name} is required for publishing but was not found on this computer.")


def _run(command: list[str], *, cwd: Path | None = None, timeout: int = 180) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PublishError(f"Could not run {Path(command[0]).name}: {error}") from error
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "Unknown error").strip()
        raise PublishError(f"{Path(command[0]).name} could not complete the publishing operation.\n\n{detail}")
    return completed.stdout.strip()


def _valid_public_machine_path(public_root: Path, slug: str) -> Path:
    safe_slug = slugify(slug)
    candidate = (public_root / safe_slug).resolve()
    if candidate.parent != public_root.resolve() or candidate.name != safe_slug:
        raise PublishError("The requested jukebox path was not safe to publish.")
    return candidate


def _library_path(workspace: Path) -> Path:
    return workspace / "public" / PUBLIC_PATH / "library.json"


def _load_library(workspace: Path) -> list[dict[str, Any]]:
    path = _library_path(workspace)
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _write_library(workspace: Path, projects: list[dict[str, Any]]) -> None:
    public = workspace / "public" / PUBLIC_PATH
    public.mkdir(parents=True, exist_ok=True)
    projects = sorted(projects, key=lambda item: str(item.get("title") or "").lower())
    _library_path(workspace).write_text(json.dumps(projects, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cards = "\n".join(
        f'<a class="machine" href="{item["slug"]}/"><img src="{item["slug"]}/social-card.jpg" alt=""><strong>{_escape(item["title"])}</strong><span>{int(item.get("videoCount") or 0)} videos</span></a>'
        for item in projects
    ) or '<p class="empty">No video jukeboxes are currently published.</p>'
    index = f'''<!doctype html>
<html lang="en-AU"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#080706"><title>CRISPY BITS Video Jukeboxes</title><style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at 50% 10%,#2a2114,#070605 55%);color:#f2e4bf;font-family:Arial,sans-serif}}main{{width:min(1100px,92vw);margin:auto;padding:70px 0}}h1{{margin:0;color:#c09155;font:700 clamp(36px,7vw,82px)/.9 Georgia,serif;letter-spacing:.05em}}p{{color:#bda77c}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px;margin-top:42px}}.machine{{display:flex;overflow:hidden;min-height:260px;flex-direction:column;border:1px solid #765027;border-radius:16px;background:#0d0a07;color:#f2e4bf;text-decoration:none;box-shadow:0 16px 34px #000}}.machine img{{width:100%;aspect-ratio:1200/630;object-fit:cover}}.machine strong{{padding:18px 18px 4px;font:700 22px Georgia,serif}}.machine span{{padding:0 18px 20px;color:#b89058;text-transform:uppercase;font-size:12px;letter-spacing:.12em}}.empty{{padding:30px;border:1px solid #50371e}}
</style></head><body><main><h1>CRISPY BITS</h1><p>VIDEO DISCOVERY JUKEBOXES</p><section class="grid">{cards}</section></main></body></html>'''
    (public / "index.html").write_text(index, encoding="utf-8")


def _escape(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class Publisher:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.git = _executable("git")

    def _archive_workspace(self, workspace: Path) -> None:
        resolved = workspace.resolve()
        root = self.store.root.resolve()
        if resolved.parent != root:
            raise PublishError(f"Refusing to archive an unexpected workspace: {resolved}")
        self.store.archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = self.store.archive_dir / f"publisher-workspace-{stamp}"
        suffix = 1
        while destination.exists():
            destination = self.store.archive_dir / f"publisher-workspace-{stamp}-{suffix}"
            suffix += 1
        workspace.replace(destination)

    def ensure_workspace(self) -> Path:
        workspace = self.store.workspace_dir
        if workspace.exists() and not (workspace / ".git").is_dir():
            self._archive_workspace(workspace)
        if workspace.exists():
            dirty = _run([self.git, "status", "--porcelain"], cwd=workspace)
            if dirty:
                self._archive_workspace(workspace)
        if not workspace.exists():
            workspace.parent.mkdir(parents=True, exist_ok=True)
            _run([self.git, "clone", GITHUB_REMOTE, str(workspace)], timeout=240)
        _run([self.git, "fetch", "origin", "main"], cwd=workspace)
        _run([self.git, "checkout", "main"], cwd=workspace)
        _run([self.git, "pull", "--ff-only", "origin", "main"], cwd=workspace)
        _run([self.git, "config", "user.name", "CRISPY BITS Video Jukebox Factory"], cwd=workspace)
        _run([self.git, "config", "user.email", "crispy-bits-video-jukebox@users.noreply.github.com"], cwd=workspace)
        return workspace

    def publish(self, project: Project) -> tuple[str, str]:
        _validate_project_type(project)
        workspace = self.ensure_workspace()
        public_root = workspace / "public" / PUBLIC_PATH
        public_root.mkdir(parents=True, exist_ok=True)
        target = _valid_public_machine_path(public_root, project.slug)
        source = self.store.project_dir(project.slug) / "site"
        if not source.is_dir():
            raise PublishError("The generated jukebox files are missing. Recreate the jukebox and try again.")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)

        library = [item for item in _load_library(workspace) if str(item.get("slug")) != project.slug]
        library.append({
            "slug": project.slug,
            "title": project.title,
            "projectType": project.project_type.value,
            "channelId": project.channel_id,
            "channelTitle": project.channel_title,
            "videoCount": len(project.videos),
            "publishedAt": utc_now(),
            "url": f"{PUBLIC_BASE_URL}/{project.slug}/",
        })
        _write_library(workspace, library)
        _run([self.git, "add", "--", f"public/{PUBLIC_PATH}/{project.slug}", f"public/{PUBLIC_PATH}/library.json", f"public/{PUBLIC_PATH}/index.html"], cwd=workspace)
        staged = _run([self.git, "diff", "--cached", "--name-only"], cwd=workspace)
        if staged:
            _run([self.git, "commit", "-m", f"Publish {project.title} video jukebox"], cwd=workspace)
            _run([self.git, "push", "origin", "main"], cwd=workspace, timeout=240)
        revision = _run([self.git, "rev-parse", "HEAD"], cwd=workspace)
        public_url = f"{PUBLIC_BASE_URL}/{project.slug}/"
        self._wait_for_publication(project.slug, revision)
        return public_url, revision

    def unpublish(self, project: Project) -> str:
        _validate_project_type(project)
        workspace = self.ensure_workspace()
        public_root = workspace / "public" / PUBLIC_PATH
        target = _valid_public_machine_path(public_root, project.slug)
        if target.exists():
            shutil.rmtree(target)
        library = [item for item in _load_library(workspace) if str(item.get("slug")) != project.slug]
        _write_library(workspace, library)
        _run([self.git, "add", "-A", "--", f"public/{PUBLIC_PATH}/{project.slug}", f"public/{PUBLIC_PATH}/library.json", f"public/{PUBLIC_PATH}/index.html"], cwd=workspace)
        staged = _run([self.git, "diff", "--cached", "--name-only"], cwd=workspace)
        if staged:
            _run([self.git, "commit", "-m", f"Unpublish {project.title} video jukebox"], cwd=workspace)
            _run([self.git, "push", "origin", "main"], cwd=workspace, timeout=240)
        return _run([self.git, "rev-parse", "HEAD"], cwd=workspace)

    def _wait_for_publication(self, slug: str, revision: str, timeout: int = 240) -> None:
        machine_url = f"{PUBLIC_BASE_URL}/{slug}/machine.json?revision={revision}"
        qr_url = f"{PUBLIC_BASE_URL}/{slug}/qr-card.png?revision={revision}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                machine_response = requests.get(machine_url, timeout=15, headers={"cache-control": "no-cache"})
                machine_ready = machine_response.ok and machine_response.json().get("slug") == slug
                qr_response = requests.get(qr_url, timeout=15, headers={"cache-control": "no-cache"}) if machine_ready else None
                qr_ready = bool(qr_response and qr_response.ok and qr_response.content.startswith(b"\x89PNG\r\n\x1a\n"))
                if machine_ready and qr_ready:
                    return
            except (requests.RequestException, AttributeError, TypeError, ValueError):
                pass
            time.sleep(5)
        raise PublishError("GitHub accepted the publication, but the live machine and QR did not both become ready within four minutes. The library can retry the email later.")
