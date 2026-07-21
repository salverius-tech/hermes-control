from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from services.control_api.main import create_app


pytestmark = pytest.mark.integration


def _initialize_native_projects(home, workspace):
    with sqlite3.connect(home / "projects.db") as db:
        db.executescript(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                primary_path TEXT,
                created_at INTEGER NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE project_folders (
                project_id TEXT NOT NULL,
                path TEXT NOT NULL,
                label TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                added_at INTEGER NOT NULL,
                PRIMARY KEY (project_id, path)
            );
            """
        )
        db.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("p_control", "control", "Control", None, str(workspace), 1, 0),
        )
        db.execute(
            "INSERT INTO project_folders VALUES (?, ?, ?, ?, ?)",
            ("p_control", str(workspace), "control", 1, 1),
        )


def _client(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    home.mkdir()
    workspace = tmp_path / "workspaces" / "control"
    workspace.mkdir(parents=True)
    _initialize_native_projects(home, workspace)
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    monkeypatch.setenv("CONTROL_API_HERMES_HOME", str(home))
    monkeypatch.setenv("CONTROL_API_PROJECT_ROOTS", str(tmp_path / "workspaces"))
    monkeypatch.setenv("CONTROL_API_ALLOW_SYNTHETIC_PROJECTS", "0")
    return TestClient(create_app()), workspace


def test_native_project_list_detail_and_task_context_are_authoritative(monkeypatch, tmp_path):
    client, workspace = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}

    projects = client.get("/projects", headers=headers)
    detail = client.get("/projects/control", headers=headers)
    task = client.post("/tasks", headers=headers, json={"prompt": "Inspect project", "project_id": "control"})

    assert projects.status_code == 200
    assert [project["project_id"] for project in projects.json()] == ["control"]
    assert detail.status_code == 200
    assert detail.json()["primary_folder"] == str(workspace)
    assert task.status_code == 201
    assert task.json()["execution_folder"] == str(workspace)


def test_strict_native_mode_rejects_missing_or_unknown_project_integration(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    monkeypatch.setenv("CONTROL_API_ALLOW_SYNTHETIC_PROJECTS", "0")
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev-token"}

    unavailable = client.get("/projects", headers=headers)
    task = client.post("/tasks", headers=headers, json={"prompt": "Do not invent project", "project_id": "missing"})

    assert unavailable.status_code == 503
    assert task.status_code == 503


def test_strict_native_mode_rejects_unknown_project_and_outside_execution_folder(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer dev-token"}

    unknown = client.post("/tasks", headers=headers, json={"prompt": "Unknown", "project_id": "missing"})
    outside = client.post(
        "/tasks",
        headers=headers,
        json={"prompt": "Outside", "project_id": "control", "execution_folder": str(tmp_path)},
    )

    assert unknown.status_code == 400
    assert outside.status_code == 400
