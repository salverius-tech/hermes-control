from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from services.control_api.git_adapter import GitCloneError
from services.control_api.main import create_app
from services.control_api.managed_workspace import MANIFEST_FILENAME, ProjectManifest
from services.control_api.models import ProjectCreateRequest
from services.control_api.recovery_audit import RecoveryAuditStore
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
    monkeypatch.setenv("CONTROL_API_DB_PATH", str(tmp_path / "control-api.db"))
    return TestClient(create_app()), root


def _write_recovery_manifest(workspace: Path, slug: str, *, repository_path: str | None = None) -> None:
    manifest = {
        "schema_version": 1,
        "identity": {"slug": slug, "name": slug.title(), "workspace_id": f"workspace-{slug}"},
        "workspace": {"folders": [{"path": ".", "role": "workspace", "primary": True}]},
        "lifecycle": {"created_at": "2026-07-21T00:00:00Z", "native_registration": "registered"},
    }
    if repository_path is not None:
        manifest["repository"] = {"path": repository_path}
    (workspace / MANIFEST_FILENAME).write_text(yaml.safe_dump(manifest), encoding="utf-8")


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


def test_recovery_plan_discovery_classifies_missing_malformed_and_traversal(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    (root / "missing").mkdir()
    malformed = root / "malformed"
    malformed.mkdir()
    (malformed / MANIFEST_FILENAME).write_text("schema_version: 2\n", encoding="utf-8")
    traversal = root / "traversal"
    traversal.mkdir()
    _write_recovery_manifest(traversal, "traversal", repository_path="../outside")

    response = client.get("/recovery-plan", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 200
    entries = {entry["workspace"]: entry for entry in response.json()["entries"]}
    assert entries[str(root / "missing")]["status"] == "blocked"
    assert "manifest is missing" in entries[str(root / "missing")]["detail"]
    assert entries[str(malformed)]["status"] == "blocked"
    assert "unsupported manifest schema version" in entries[str(malformed)]["detail"]
    assert entries[str(traversal)]["status"] == "blocked"
    assert "relative and contained" in entries[str(traversal)]["detail"]


def test_recovery_plan_classifies_duplicate_slugs_and_native_primary_conflicts(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    for name in ("Duplicate One", "Duplicate Two"):
        workspace = root / name.lower().replace(" ", "-")
        workspace.mkdir()
        _write_recovery_manifest(workspace, "duplicate")
    assert client.post("/projects", headers=headers, json={"name": "Conflict", "origin": "workspace"}).status_code == 201
    alternate = root / "alternate"
    alternate.mkdir()
    with sqlite3.connect(tmp_path / "hermes" / "projects.db") as db:
        db.execute("UPDATE projects SET primary_path = ? WHERE slug = ?", (str(alternate), "conflict"))

    response = client.get("/recovery-plan", headers=headers)

    entries = response.json()["entries"]
    duplicates = [entry for entry in entries if entry.get("slug") == "duplicate"]
    assert len(duplicates) == 2
    assert {entry["status"] for entry in duplicates} == {"conflict"}
    assert next(entry for entry in entries if entry.get("slug") == "conflict")["status"] == "conflict"


def test_recovery_plan_is_read_only_and_reports_registered_workspace(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    assert client.post("/projects", headers=headers, json={"name": "Recovered", "origin": "workspace"}).status_code == 201
    database = tmp_path / "hermes" / "projects.db"
    manifest = root / "recovered" / MANIFEST_FILENAME
    before_database = database.read_bytes()
    before_manifest = manifest.read_bytes()
    response = client.get("/recovery-plan", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"entries": [{"workspace": str(root / "recovered"), "slug": "recovered", "status": "already_registered"}]}
    assert database.read_bytes() == before_database
    assert manifest.read_bytes() == before_manifest


def test_recovery_plan_reports_malformed_manifest_as_blocked(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    workspace = root / "invalid"
    workspace.mkdir()
    (workspace / MANIFEST_FILENAME).write_text("schema_version: 2\n", encoding="utf-8")

    response = client.get("/recovery-plan", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 200
    entry = response.json()["entries"]
    assert entry[0]["workspace"] == str(workspace)
    assert entry[0]["status"] == "blocked"
    assert "unsupported manifest schema version" in entry[0]["detail"]


def test_recovery_plan_reports_declared_repository_missing_directory(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}

    def clone(_adapter, _remote, destination):
        destination.mkdir()

    monkeypatch.setattr("services.control_api.managed_workspace.GitAdapter.clone", clone)
    assert client.post(
        "/projects",
        headers=headers,
        json={"name": "Missing Repository", "origin": "clone", "repository_url": "https://example.test/team/missing.git"},
    ).status_code == 201
    (root / "missing-repository" / "repo").rmdir()

    response = client.get("/recovery-plan", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"entries": [{
        "workspace": str(root / "missing-repository"),
        "slug": "missing-repository",
        "status": "missing_repository",
    }]}


@pytest.mark.parametrize("payload", [
    {"slugs": ["confirmation"]},
    {"slugs": ["confirmation"], "confirm": False},
    {"slugs": ["confirmation"], "confirm": 1},
    {"slugs": ["confirmation"], "confirm": "true"},
])
def test_recovery_apply_requires_literal_true_confirmation_and_rejects_cancel(monkeypatch, tmp_path, payload):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    assert client.post("/projects", headers=headers, json={"name": "Confirmation", "origin": "workspace"}).status_code == 201
    with sqlite3.connect(tmp_path / "hermes" / "projects.db") as db:
        db.execute("DELETE FROM project_folders WHERE project_id IN (SELECT id FROM projects WHERE slug = ?)", ("confirmation",))
        db.execute("DELETE FROM projects WHERE slug = ?", ("confirmation",))

    response = client.post("/recovery-plan/apply", headers=headers, json=payload)

    assert response.status_code == 422
    assert HermesWorkspaceStore(tmp_path / "hermes").get_project("confirmation") is None
    assert (root / "confirmation").is_dir()


def test_recovery_apply_revalidates_changed_manifest_before_creating(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    assert client.post("/projects", headers=headers, json={"name": "Changed", "origin": "workspace"}).status_code == 201
    with sqlite3.connect(tmp_path / "hermes" / "projects.db") as db:
        db.execute("DELETE FROM project_folders WHERE project_id IN (SELECT id FROM projects WHERE slug = ?)", ("changed",))
        db.execute("DELETE FROM projects WHERE slug = ?", ("changed",))
    assert client.get("/recovery-plan", headers=headers).json()["entries"][0]["status"] == "ready"
    manifest_path = root / "changed" / MANIFEST_FILENAME
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["repository"] = {"path": "../outside"}
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    response = client.post("/recovery-plan/apply", headers=headers, json={"slugs": ["changed"], "confirm": True})

    assert response.json() == {"results": [{"slug": "changed", "status": "blocked"}]}
    assert HermesWorkspaceStore(tmp_path / "hermes").get_project("changed") is None


def test_recovery_apply_revalidates_native_registration_before_creating(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    assert client.post("/projects", headers=headers, json={"name": "Race", "origin": "workspace"}).status_code == 201
    with sqlite3.connect(tmp_path / "hermes" / "projects.db") as db:
        db.execute("DELETE FROM project_folders WHERE project_id IN (SELECT id FROM projects WHERE slug = ?)", ("race",))
        db.execute("DELETE FROM projects WHERE slug = ?", ("race",))
    assert client.get("/recovery-plan", headers=headers).json()["entries"][0]["status"] == "ready"

    HermesWorkspaceStore(tmp_path / "hermes").create_project(ProjectCreateRequest(
        name="Externally Restored",
        slug="race",
        folders=[str(root / "race")],
        primary_folder=str(root / "race"),
    ))
    response = client.post("/recovery-plan/apply", headers=headers, json={"slugs": ["race"], "confirm": True})

    assert response.json() == {"results": [{"slug": "race", "status": "blocked"}]}
    project = HermesWorkspaceStore(tmp_path / "hermes").get_project("race")
    assert project is not None
    assert project.name == "Externally Restored"


def test_recovery_apply_restores_clean_profile_with_workspace_primary_and_declared_repo(monkeypatch, tmp_path):
    client, root = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}

    def clone(_adapter, _remote, destination):
        destination.mkdir()

    monkeypatch.setattr("services.control_api.managed_workspace.GitAdapter.clone", clone)
    assert client.post(
        "/projects",
        headers=headers,
        json={"name": "Restored Repository", "origin": "clone", "repository_url": "https://example.test/team/restored.git"},
    ).status_code == 201
    workspace = root / "restored-repository"
    (workspace / "repo").rename(workspace / "source")
    manifest_path = workspace / MANIFEST_FILENAME
    manifest_path.write_text(manifest_path.read_text(encoding="utf-8").replace("path: repo", "path: source"), encoding="utf-8")
    with sqlite3.connect(tmp_path / "hermes" / "projects.db") as db:
        db.execute("DELETE FROM project_folders")
        db.execute("DELETE FROM projects")

    response = client.post(
        "/recovery-plan/apply",
        headers=headers,
        json={"slugs": ["restored-repository"], "confirm": True},
    )

    assert response.json() == {"results": [{"slug": "restored-repository", "status": "restored"}]}
    restored = HermesWorkspaceStore(tmp_path / "hermes").get_project("restored-repository")
    assert restored is not None
    assert restored.project_id == "restored-repository"
    assert restored.primary_folder == str(workspace)
    assert restored.folders == [str(workspace), str(workspace / "source")]


def test_recovery_audit_store_persists_timeline_after_reload(tmp_path):
    database = tmp_path / "control-api.db"
    audit = RecoveryAuditStore(database)
    audit.record("garden", "blocked")
    audit.record("garden", "restored")
    audit.record("other", "blocked")

    entries = RecoveryAuditStore(database).list_entries(slug="garden")

    assert [entry["status"] for entry in entries] == ["blocked", "restored"]
    assert [entry["slug"] for entry in entries] == ["garden", "garden"]
    assert all(entry["created_at"] for entry in entries)


def test_recovery_audit_timeline_is_authenticated_and_reports_apply_results(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}
    assert client.get("/recovery-audit").status_code == 401
    assert client.post("/projects", headers=headers, json={"name": "Audit Garden", "origin": "workspace"}).status_code == 201
    with sqlite3.connect(tmp_path / "hermes" / "projects.db") as db:
        db.execute("DELETE FROM project_folders WHERE project_id IN (SELECT id FROM projects WHERE slug = ?)", ("audit-garden",))
        db.execute("DELETE FROM projects WHERE slug = ?", ("audit-garden",))

    applied = client.post("/recovery-plan/apply", headers=headers, json={"slugs": ["audit-garden"], "confirm": True})
    timeline = client.get("/recovery-audit?slug=audit-garden", headers=headers)

    assert applied.json() == {"results": [{"slug": "audit-garden", "status": "restored"}]}
    assert timeline.status_code == 200
    entries = timeline.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["slug"] == "audit-garden"
    assert entries[0]["status"] == "restored"
    assert entries[0]["created_at"]
