from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from .config import GITHUB_OWNER, GITHUB_REMOTE, GITHUB_REPOSITORY, PUBLIC_BASE_URL, PUBLIC_PATH
from .diagnostics import get_logger
from .models import Project, ProjectType, PublicationOperation, utc_now
from .social_preview import social_preview_filename
from .store import ProjectStore, slugify


class PublishError(RuntimeError):
    pass


class PublicationVerificationPending(PublishError):
    def __init__(self, project: Project, message: str) -> None:
        super().__init__(message)
        self.project = project


class UnpublishVerificationPending(PublicationVerificationPending):
    pass


def _validate_project_type(project: Project) -> None:
    if project.project_type not in {
        ProjectType.BUSINESS, ProjectType.MUSIC, ProjectType.TOURISM,
        ProjectType.BANJO, ProjectType.CHANNEL_MASTER, ProjectType.WHITE_LABEL,
    }:
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
        f'<a class="machine" href="{item["slug"]}/"><img src="{item["slug"]}/{_escape(item.get("socialImage") or "social-card.jpg")}" alt="{_escape(item["title"])} — Crispy Bits preview"><strong>{_escape(item["title"])}</strong><span>{int(item.get("videoCount") or 0)} videos</span></a>'
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
        self.logger = get_logger()

    def _start_operation(self, project: Project, operation_type: str) -> PublicationOperation:
        operation = PublicationOperation(
            operation_id=str(uuid4()),
            operation_type=operation_type,
            project_id=project.id,
            slug=project.slug,
            target_revision=None,
            expected_url=f"{PUBLIC_BASE_URL}/{project.slug}/",
            started_at=utc_now(),
        )
        project.publication_operation = operation
        self.store.save_project(project)
        self.logger.info("Publication operation started id=%s type=%s slug=%s", operation.operation_id, operation_type, project.slug)
        return operation

    def _fail_operation(self, project: Project, error: Exception, status: str) -> None:
        operation = project.publication_operation
        if operation:
            operation.verification_status = "failed"
            operation.last_error = str(error)
        project.status = status
        self.store.save_project(project)
        self.logger.error("Publication operation failed type=%s slug=%s error=%s", operation.operation_type if operation else "unknown", project.slug, error)

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
        public_url = f"{PUBLIC_BASE_URL}/{project.slug}/"
        operation = self._start_operation(project, "publish")
        try:
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
                "url": public_url,
                "socialImage": social_preview_filename(project.title, project.project_type),
            })
            _write_library(workspace, library)
            _run([self.git, "add", "--", f"public/{PUBLIC_PATH}/{project.slug}", f"public/{PUBLIC_PATH}/library.json", f"public/{PUBLIC_PATH}/index.html"], cwd=workspace)
            staged = _run([self.git, "diff", "--cached", "--name-only"], cwd=workspace)
            if staged:
                _run([self.git, "commit", "-m", f"Publish {project.title} video jukebox"], cwd=workspace)
                _run([self.git, "push", "origin", "main"], cwd=workspace, timeout=240)
            revision = _run([self.git, "rev-parse", "HEAD"], cwd=workspace)
        except Exception as error:
            self._fail_operation(project, error, "publish_failed")
            raise
        operation.target_revision = revision
        operation.git_confirmed_at = utc_now()
        operation.verification_status = "pending"
        project.published_url = public_url
        project.publication_revision = revision
        project.status = "verification_pending"
        if not project.delivery_record or project.delivery_record.revision != revision:
            project.delivery_status = "not_requested"
        self.store.save_project(project)
        self.logger.info("Git push confirmed slug=%s revision=%s", project.slug, revision)
        try:
            self._wait_for_publication(project.slug, revision)
        except PublishError as error:
            operation.last_error = str(error)
            project.status = "verification_pending"
            self.store.save_project(project)
            self.logger.warning("Pages verification pending slug=%s revision=%s", project.slug, revision)
            raise PublicationVerificationPending(
                project,
                "The update was pushed successfully, but the live site could not yet be verified. Use CHECK LIVE STATUS before publishing again.",
            ) from error
        operation.verification_status = "verified"
        operation.verified_at = utc_now()
        operation.last_error = None
        self.store.save_project(project)
        return public_url, revision

    def unpublish(self, project: Project) -> str:
        _validate_project_type(project)
        operation = self._start_operation(project, "unpublish")
        try:
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
            revision = _run([self.git, "rev-parse", "HEAD"], cwd=workspace)
        except Exception as error:
            self._fail_operation(project, error, "unpublish_failed")
            raise
        operation.target_revision = revision
        operation.git_confirmed_at = utc_now()
        operation.verification_status = "pending"
        project.status = "unpublish_verification_pending"
        self.store.save_project(project)
        self.logger.info("Unpublish push confirmed slug=%s revision=%s", project.slug, revision)
        try:
            self._wait_for_unpublication(project.slug)
        except PublishError as error:
            operation.last_error = str(error)
            self.store.save_project(project)
            self.logger.warning("Unpublish verification pending slug=%s revision=%s", project.slug, revision)
            raise UnpublishVerificationPending(
                project,
                "The removal was pushed successfully, but the live site could not yet be confirmed absent. Use CHECK LIVE STATUS before trying again.",
            ) from error
        operation.verification_status = "verified"
        operation.verified_at = utc_now()
        operation.last_error = None
        self.store.save_project(project)
        return revision

    def reconcile(self, project: Project) -> str:
        operation = project.publication_operation
        if not operation or operation.verification_status != "pending":
            raise PublishError("This project has no publication operation waiting for verification.")
        if operation.operation_type == "publish":
            if not self._publication_ready(project.slug, operation.target_revision or ""):
                operation.last_error = "The live machine or QR is not ready yet."
                self.store.save_project(project)
                raise PublicationVerificationPending(project, "The live machine is still not verified. No new publish was attempted.")
            operation.verification_status = "verified"
            operation.verified_at = utc_now()
            operation.last_error = None
            project.status = "published"
            project.published_url = operation.expected_url
            project.publication_revision = operation.target_revision
            project.published_at = project.published_at or utc_now()
            self.store.save_project(project)
            self.logger.info("Publication reconciled slug=%s revision=%s", project.slug, operation.target_revision)
            return "published"
        if operation.operation_type == "unpublish":
            if not self._unpublication_ready(project.slug):
                operation.last_error = "The public machine is still reachable."
                self.store.save_project(project)
                raise UnpublishVerificationPending(project, "The public machine is still reachable. No new unpublish was attempted.")
            operation.verification_status = "verified"
            operation.verified_at = utc_now()
            operation.last_error = None
            project.status = "unpublished"
            project.published_url = None
            project.published_at = None
            project.publication_revision = None
            project.delivery_status = "not_requested"
            self.store.save_project(project)
            self.logger.info("Unpublish reconciled slug=%s", project.slug)
            return "unpublished"
        raise PublishError("The pending publication operation type is not supported.")

    def _wait_for_publication(self, slug: str, revision: str, timeout: int = 240) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._publication_ready(slug, revision):
                return
            time.sleep(5)
        raise PublishError("GitHub accepted the publication, but the live machine and QR did not both become ready within four minutes.")

    def _wait_for_unpublication(self, slug: str, timeout: int = 240) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._unpublication_ready(slug):
                return
            time.sleep(5)
        raise PublishError("GitHub accepted the removal, but the public machine still could not be confirmed absent within four minutes.")

    def _publication_ready(self, slug: str, revision: str) -> bool:
        cache_buster = time.time_ns()
        machine_url = f"{PUBLIC_BASE_URL}/{slug}/machine.json?revision={revision}&verification={cache_buster}"
        qr_url = f"{PUBLIC_BASE_URL}/{slug}/qr-card.png?revision={revision}&verification={cache_buster}"
        commit_base = (
            f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/"
            f"{revision}/public/{PUBLIC_PATH}/{slug}"
        )
        try:
            machine_response = requests.get(machine_url, timeout=15, headers={"cache-control": "no-cache"})
            qr_response = requests.get(qr_url, timeout=15, headers={"cache-control": "no-cache"})
            commit_machine_response = requests.get(f"{commit_base}/machine.json", timeout=15, headers={"cache-control": "no-cache"})
            commit_qr_response = requests.get(f"{commit_base}/qr-card.png", timeout=15, headers={"cache-control": "no-cache"})
            if not all(response.ok for response in (machine_response, qr_response, commit_machine_response, commit_qr_response)):
                return False
            live_machine = machine_response.json()
            commit_machine = commit_machine_response.json()
            return bool(
                live_machine.get("slug") == slug
                and commit_machine.get("slug") == slug
                and machine_response.content == commit_machine_response.content
                and qr_response.content.startswith(b"\x89PNG\r\n\x1a\n")
                and qr_response.content == commit_qr_response.content
            )
        except (requests.RequestException, AttributeError, TypeError, ValueError):
            return False

    def _unpublication_ready(self, slug: str) -> bool:
        machine_url = f"{PUBLIC_BASE_URL}/{slug}/machine.json?verification={int(time.time())}"
        try:
            response = requests.get(machine_url, timeout=15, headers={"cache-control": "no-cache"})
            return response.status_code in {404, 410}
        except requests.RequestException:
            return False
