from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

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


def test_managed_manifest_tracks_native_project_edits(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    assert client.post("/projects", headers=headers, json={"name": "Garden", "origin": "workspace"}).status_code == 201

    updated = client.patch("/projects/garden", headers=headers, json={"name": "Garden Notes", "description": "Updated"})

    assert updated.status_code == 200
    manifest = (root / "garden" / MANIFEST_FILENAME).read_text()
    assert "name: Garden Notes" in manifest
    assert "description: Updated" in manifest
