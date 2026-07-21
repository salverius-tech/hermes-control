from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from services.control_api.git_adapter import GitCloneError
from services.control_api.main import create_app
from services.control_api.managed_workspace import MANIFEST_FILENAME, ProjectManifest
from services.control_api.workspace import HermesWorkspaceStore

pytestmark = pytest.mark.integration


def _client(monkeypatch, tmp_path):
    home = tmp_path / "hermes"
    root = home / "workspaces"
    home.mkdir()
    root.mkdir()
    with sqlite3.connect(home / "projects.db") as db:
        db.executescript("""
            CREATE TABLE projects (id TEXT PRIMARY KEY, slug TEXT NOT NULL, name TEXT NOT NULL, description TEXT, primary_path TEXT, created_at INTEGER NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE project_folders (project_id TEXT NOT NULL, path TEXT NOT NULL, label TEXT, is_primary INTEGER NOT NULL DEFAULT 0, added_at INTEGER NOT NULL, PRIMARY KEY (project_id, path));
        """)
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    monkeypatch.setenv("CONTROL_API_HERMES_HOME", str(home))
    monkeypatch.setenv("CONTROL_API_PROJECT_ROOTS", str(root))
    monkeypatch.setenv("CONTROL_API_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("CONTROL_API_ALLOW_SYNTHETIC_PROJECTS", "0")
    return TestClient(create_app()), root


def test_workspace_origin_creates_native_project_and_recovery_manifest(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    response = client.post("/projects", headers={"Authorization": "Bearer dev-token"}, json={"name": "Garden Planner", "origin": "workspace"})

    assert response.status_code == 201
    assert response.json()["project_id"] == "garden-planner"
    workspace = root / "garden-planner"
    assert response.json()["primary_folder"] == str(workspace)
    assert (workspace / "notes").is_dir()
    assert (workspace / "artifacts").is_dir()
    manifest = (workspace / MANIFEST_FILENAME).read_text()
    assert "workspace_id:" in manifest
    assert "native_registration: registered" in manifest


def test_workspace_origin_rejects_collisions(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    assert client.post("/projects", headers=headers, json={"name": "Garden Planner", "origin": "workspace"}).status_code == 201
    duplicate = client.post("/projects", headers=headers, json={"name": "Garden Planner", "origin": "workspace"})
    assert duplicate.status_code == 400
    assert "workspace already exists" in duplicate.json()["detail"]


def test_manifest_rejects_unknown_schema_extra_fields_and_unsafe_paths():
    valid = {
        "schema_version": 1,
        "identity": {"slug": "control", "name": "Control", "workspace_id": "id"},
        "workspace": {"folders": [{"path": ".", "role": "workspace", "primary": True}]},
        "lifecycle": {"created_at": "2026-07-21T00:00:00Z", "native_registration": "registered"},
    }

    with pytest.raises(ValidationError, match="unsupported manifest schema"):
        ProjectManifest.model_validate({**valid, "schema_version": 2})
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate({**valid, "unexpected": True})
    unsafe = {**valid, "workspace": {"folders": [{"path": "../outside", "role": "workspace", "primary": True}]}}
    with pytest.raises(ValidationError, match="relative and contained"):
        ProjectManifest.model_validate(unsafe)


def test_workspace_registration_failure_preserves_repairable_workspace(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    original_create = HermesWorkspaceStore.create_project
    monkeypatch.setattr(HermesWorkspaceStore, "create_project", lambda *_: (_ for _ in ()).throw(RuntimeError("native failure")))

    response = client.post(
        "/projects",
        headers={"Authorization": "Bearer dev-token"},
        json={"name": "Recoverable", "origin": "workspace"},
    )

    assert response.status_code == 400
    workspace = root / "recoverable"
    assert workspace.is_dir()
    assert "native_registration: registration_failed" in (workspace / MANIFEST_FILENAME).read_text()
    assert not list(root.glob(".recoverable.creating-*"))

    monkeypatch.setattr(HermesWorkspaceStore, "create_project", original_create)
    repaired = client.post(
        "/projects",
        headers={"Authorization": "Bearer dev-token"},
        json={"name": "Recoverable", "origin": "workspace"},
    )
    assert repaired.status_code == 201
    assert "native_registration: registered" in (workspace / MANIFEST_FILENAME).read_text()


def test_managed_manifest_tracks_native_project_edits(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    assert client.post("/projects", headers=headers, json={"name": "Garden", "origin": "workspace"}).status_code == 201

    updated = client.patch("/projects/garden", headers=headers, json={"name": "Garden Notes", "description": "Updated"})

    assert updated.status_code == 200
    manifest = (root / "garden" / MANIFEST_FILENAME).read_text()
    assert "name: Garden Notes" in manifest
    assert "description: Updated" in manifest

    archived = client.patch("/projects/garden", headers=headers, json={"archived": True})
    assert archived.status_code == 200
    assert "native_registration: archived" in (root / "garden" / MANIFEST_FILENAME).read_text()


def test_clone_origin_clones_before_native_registration(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)

    def clone(_adapter, remote, destination):
        assert remote == "https://example.test/team/remote.git"
        (tmp_path / "marker").write_text("cloned")
        destination.mkdir()

    monkeypatch.setattr("services.control_api.managed_workspace.GitAdapter.clone", clone)
    response = client.post(
        "/projects",
        headers={"Authorization": "Bearer dev-token"},
        json={"name": "Remote", "origin": "clone", "repository_url": "https://example.test/team/remote.git"},
    )

    assert response.status_code == 201
    workspace = root / "remote"
    assert (workspace / "repo").is_dir()
    assert "remote_url: https://example.test/team/remote.git" in (workspace / MANIFEST_FILENAME).read_text()
    assert "repository_clone: cloned" in (workspace / MANIFEST_FILENAME).read_text()
    assert response.json()["folders"] == [str(workspace), str(workspace / "repo")]


def test_clone_origin_rejects_unsafe_url_without_creating_workspace(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    response = client.post(
        "/projects",
        headers={"Authorization": "Bearer dev-token"},
        json={"name": "Unsafe", "origin": "clone", "repository_url": "file:///tmp/repository.git"},
    )
    assert response.status_code == 400
    assert not (root / "unsafe").exists()


def test_clone_failure_preserves_workspace_state(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)

    def fail_clone(*_args, **_kwargs):
        raise GitCloneError("repository clone failed")

    monkeypatch.setattr("services.control_api.managed_workspace.GitAdapter.clone", fail_clone)
    response = client.post(
        "/projects",
        headers={"Authorization": "Bearer dev-token"},
        json={"name": "Broken Remote", "origin": "clone", "repository_url": "https://example.test/team/broken.git"},
    )
    assert response.status_code == 400
    manifest = (root / "broken-remote" / MANIFEST_FILENAME).read_text()
    assert "repository_clone: clone_failed" in manifest
    assert "native_registration: pending" in manifest


def test_clone_registration_failure_repair_preserves_repo(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)

    def clone(_adapter, _remote, destination):
        destination.mkdir()

    original_create = HermesWorkspaceStore.create_project
    monkeypatch.setattr("services.control_api.managed_workspace.GitAdapter.clone", clone)
    monkeypatch.setattr(HermesWorkspaceStore, "create_project", lambda *_: (_ for _ in ()).throw(RuntimeError("native failure")))
    headers = {"Authorization": "Bearer dev-token"}
    body = {"name": "Clone Repair", "origin": "clone", "repository_url": "https://example.test/team/repair.git"}
    assert client.post("/projects", headers=headers, json=body).status_code == 400

    monkeypatch.setattr(HermesWorkspaceStore, "create_project", original_create)
    repaired = client.post("/projects", headers=headers, json=body)
    assert repaired.status_code == 201
    workspace = root / "clone-repair"
    assert repaired.json()["folders"] == [str(workspace), str(workspace / "repo")]


def test_attach_repository_to_workspace_project(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    assert client.post("/projects", headers=headers, json={"name": "Attach", "origin": "workspace"}).status_code == 201

    def clone(_adapter, _remote, destination):
        destination.mkdir()

    monkeypatch.setattr("services.control_api.managed_workspace.GitAdapter.clone", clone)
    response = client.post(
        "/projects/attach/repository",
        headers=headers,
        json={"repository_url": "https://example.test/team/attach.git"},
    )
    assert response.status_code == 200
    workspace = root / "attach"
    assert response.json()["folders"] == [str(workspace), str(workspace / "repo")]
    assert "remote_url: https://example.test/team/attach.git" in (workspace / MANIFEST_FILENAME).read_text()
