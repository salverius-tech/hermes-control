from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .git_adapter import GitAdapter, GitCloneError
from .models import ProjectCreateRequest, ProjectSummary
from .workspace import HermesWorkspaceStore

MANIFEST_FILENAME = "hermes-project.yaml"


class ManifestFolder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    role: str
    primary: bool = False

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("manifest paths must be relative and contained")
        return value


class ManifestIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str
    name: str
    description: str | None = None
    workspace_id: str


class ManifestWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary_folder: str = "."
    folders: list[ManifestFolder] = Field(default_factory=list)


class ManifestRepository(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = "repo"
    remote_url: str | None = None

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("manifest paths must be relative and contained")
        return value


class ManifestLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    managed_by: str = "hermes-control"
    created_at: datetime
    native_registration: str
    repository_clone: Literal["pending", "cloned", "clone_failed"] | None = None


class ProjectManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    identity: ManifestIdentity
    workspace: ManifestWorkspace
    repository: ManifestRepository | None = None
    lifecycle: ManifestLifecycle

    @field_validator("schema_version")
    @classmethod
    def supported_schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"unsupported manifest schema version: {value}")
        return value


class ManagedWorkspaceStore:
    """Creates managed workspace-only projects and their portable manifests."""

    def __init__(self, native: HermesWorkspaceStore, root: str | Path) -> None:
        self.native = native
        self.root = Path(root).expanduser().resolve()
        self.git = GitAdapter()

    @property
    def ready(self) -> bool:
        return self.root.is_dir() and os.access(self.root, os.W_OK | os.X_OK)

    def create_workspace_project(self, request: ProjectCreateRequest) -> ProjectSummary:
        if not self.ready:
            raise ValueError("managed workspace root is unavailable or not writable")
        slug = self._slug(request.slug or request.name)
        workspace = (self.root / slug).resolve()
        if not workspace.is_relative_to(self.root):
            raise ValueError("workspace is outside the managed workspace root")
        if workspace.exists():
            manifest_path = workspace / MANIFEST_FILENAME
            if manifest_path.is_file():
                manifest = self.read_manifest(workspace)
                if manifest.identity.slug == slug and manifest.lifecycle.native_registration == "registration_failed" and self.native.get_project(slug) is None:
                    folders = [str(workspace)]
                    if manifest.lifecycle.repository_clone == "cloned" and (workspace / "repo").is_dir():
                        folders.append(str(workspace / "repo"))
                    project = self.native.create_project(request.model_copy(update={
                        "slug": slug,
                        "folders": folders,
                        "primary_folder": str(workspace),
                    }))
                    self.write_manifest(workspace, manifest.model_copy(update={
                        "lifecycle": manifest.lifecycle.model_copy(update={"native_registration": "registered"})
                    }))
                    return project
            raise ValueError(f"workspace already exists: {slug}")

        staging = self.root / f".{slug}.creating-{uuid.uuid4().hex}"
        staging.mkdir()
        (staging / "notes").mkdir()
        (staging / "artifacts").mkdir()
        (staging / "README.md").write_text(f"# {request.name.strip()}\n", encoding="utf-8")
        manifest = self._manifest(request, slug, "pending")
        self.write_manifest(staging, manifest)
        staging.replace(workspace)
        try:
            project = self.native.create_project(request.model_copy(update={
                "slug": slug,
                "folders": [str(workspace)],
                "primary_folder": str(workspace),
            }))
        except Exception:
            self.write_manifest(workspace, manifest.model_copy(update={
                "lifecycle": manifest.lifecycle.model_copy(update={"native_registration": "registration_failed"})
            }))
            raise
        self.write_manifest(workspace, manifest.model_copy(update={
            "lifecycle": manifest.lifecycle.model_copy(update={"native_registration": "registered"})
        }))
        return project

    def create_clone_project(self, request: ProjectCreateRequest) -> ProjectSummary:
        """Clone a remote before registering the native Hermes project."""
        if not self.ready:
            raise ValueError("managed workspace root is unavailable or not writable")
        remote = self._repository_url(request.repository_url)
        slug = self._slug(request.slug or request.name)
        workspace = (self.root / slug).resolve()
        if not workspace.is_relative_to(self.root):
            raise ValueError("workspace is outside the managed workspace root")
        if workspace.exists():
            return self.create_workspace_project(request)
        staging = self.root / f".{slug}.creating-{uuid.uuid4().hex}"
        staging.mkdir()
        (staging / "notes").mkdir()
        (staging / "artifacts").mkdir()
        (staging / "README.md").write_text(f"# {request.name.strip()}\n", encoding="utf-8")
        manifest = self._manifest(request, slug, "pending").model_copy(update={
            "repository": ManifestRepository(remote_url=remote),
            "lifecycle": ManifestLifecycle(
                created_at=datetime.now(timezone.utc), native_registration="pending", repository_clone="pending"
            ),
        })
        self.write_manifest(staging, manifest)
        staging.replace(workspace)
        repo = workspace / "repo"
        try:
            self.git.clone(remote, repo)
        except GitCloneError as exc:
            self.write_manifest(workspace, manifest.model_copy(update={"lifecycle": manifest.lifecycle.model_copy(update={"repository_clone": "clone_failed"})}))
            raise ValueError("repository clone failed") from exc
        manifest = manifest.model_copy(update={"lifecycle": manifest.lifecycle.model_copy(update={"repository_clone": "cloned"})})
        self.write_manifest(workspace, manifest)
        try:
            project = self.native.create_project(request.model_copy(update={"slug": slug, "folders": [str(workspace), str(repo)], "primary_folder": str(workspace)}))
        except Exception:
            self.write_manifest(workspace, manifest.model_copy(update={"lifecycle": manifest.lifecycle.model_copy(update={"native_registration": "registration_failed"})}))
            raise
        self.write_manifest(workspace, manifest.model_copy(update={"lifecycle": manifest.lifecycle.model_copy(update={"native_registration": "registered"})}))
        return project

    def discover_manifests(self) -> list[tuple[Path, ProjectManifest | None, str | None]]:
        """Read only direct managed-workspace manifests; never follows external paths."""
        if not self.root.is_dir():
            return []
        discovered = []
        for manifest_path in sorted(self.root.glob(f"*/{MANIFEST_FILENAME}")):
            workspace = manifest_path.parent.resolve()
            try:
                if not workspace.is_relative_to(self.root):
                    continue
                discovered.append((workspace, self.read_manifest(workspace), None))
            except (OSError, ValueError, ValidationError) as exc:
                discovered.append((workspace, None, str(exc)))
        return discovered

    @staticmethod
    def repository_directory(workspace: Path, manifest: ProjectManifest) -> Path | None:
        """Return a declared repository directory only when it stays in its workspace."""
        if manifest.repository is None:
            return None
        repository = (workspace / manifest.repository.path).resolve()
        if not repository.is_relative_to(workspace):
            raise ValueError("repository path is outside the managed workspace")
        return repository

    def attach_repository(self, project_id: str, repository_url: str) -> ProjectSummary:

        project = self.native.get_project(project_id)
        if project is None or not project.primary_folder:
            raise ValueError("unknown managed project")
        workspace = Path(project.primary_folder).resolve()
        manifest = self.read_manifest(workspace)
        if not workspace.is_relative_to(self.root) or manifest.repository is not None:
            raise ValueError("project cannot accept a managed repository")
        remote = self._repository_url(repository_url)
        repo = workspace / "repo"
        if repo.exists():
            raise ValueError("repository destination already exists")
        self.git.clone(remote, repo)
        try:
            project = self.native.add_folder(project_id, str(repo))
        except Exception:
            raise
        manifest = manifest.model_copy(update={"repository": ManifestRepository(remote_url=remote)})
        self.write_manifest(workspace, manifest)
        return project

    def write_manifest(self, workspace: str | Path, manifest: ProjectManifest) -> None:
        workspace_path = Path(workspace).resolve()
        if not workspace_path.is_relative_to(self.root):
            raise ValueError("workspace is outside the managed workspace root")
        destination = workspace_path / MANIFEST_FILENAME
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
        temporary.replace(destination)

    def read_manifest(self, workspace: str | Path) -> ProjectManifest:
        workspace_path = Path(workspace).resolve()
        if not workspace_path.is_relative_to(self.root):
            raise ValueError("workspace is outside the managed workspace root")
        return ProjectManifest.model_validate(yaml.safe_load((workspace_path / MANIFEST_FILENAME).read_text(encoding="utf-8")))

    def synchronize_project(self, project: ProjectSummary) -> None:
        """Mirror native changes only when a managed manifest already exists."""
        if not project.primary_folder:
            return
        workspace = Path(project.primary_folder).resolve()
        manifest_path = workspace / MANIFEST_FILENAME
        if not workspace.is_relative_to(self.root) or not manifest_path.is_file():
            return
        manifest = self.read_manifest(workspace)
        folders: list[ManifestFolder] = []
        for folder in project.folders:
            path = Path(folder).resolve()
            if not path.is_relative_to(workspace):
                return
            relative = str(path.relative_to(workspace)) or "."
            folders.append(ManifestFolder(path=relative, role="repository" if relative == "repo" else "workspace", primary=path == workspace))
        self.write_manifest(workspace, manifest.model_copy(update={
            "identity": manifest.identity.model_copy(update={"name": project.name, "description": project.description}),
            "workspace": manifest.workspace.model_copy(update={"folders": folders, "primary_folder": "."}),
            "lifecycle": manifest.lifecycle.model_copy(update={"native_registration": "archived" if project.archived else "registered"}),
        }))

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        if not slug:
            raise ValueError("project slug must contain letters or numbers")
        return slug

    @staticmethod
    def _repository_url(value: str | None) -> str:
        if not value or not value.strip() or value.startswith("-"):
            raise ValueError("repository URL is required")
        remote = value.strip()
        if not re.match(r"^(https://|ssh://|git@)[^\s]+$", remote):
            raise ValueError("repository URL must use HTTPS or SSH")
        host = remote.split("://", 1)[-1].split("/", 1)[0]
        if "@" in host and not remote.startswith("git@"):
            raise ValueError("repository URL must not include credentials")
        return remote

    @staticmethod
    def _manifest(request: ProjectCreateRequest, slug: str, registration: str) -> ProjectManifest:
        return ProjectManifest(
            identity=ManifestIdentity(slug=slug, name=request.name.strip(), description=request.description, workspace_id=str(uuid.uuid4())),
            workspace=ManifestWorkspace(folders=[ManifestFolder(path=".", role="workspace", primary=True)]),
            lifecycle=ManifestLifecycle(created_at=datetime.now(timezone.utc), native_registration=registration),
        )
