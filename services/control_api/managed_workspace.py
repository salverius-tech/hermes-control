from __future__ import annotations

import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class ManifestLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    managed_by: str = "hermes-control"
    created_at: datetime
    native_registration: str


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

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        if not slug:
            raise ValueError("project slug must contain letters or numbers")
        return slug

    @staticmethod
    def _manifest(request: ProjectCreateRequest, slug: str, registration: str) -> ProjectManifest:
        return ProjectManifest(
            identity=ManifestIdentity(slug=slug, name=request.name.strip(), description=request.description, workspace_id=str(uuid.uuid4())),
            workspace=ManifestWorkspace(folders=[ManifestFolder(path=".", role="workspace", primary=True)]),
            lifecycle=ManifestLifecycle(created_at=datetime.now(timezone.utc), native_registration=registration),
        )
