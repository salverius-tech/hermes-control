import sqlite3

import pytest

from services.control_api.models import ProjectCreateRequest
from services.control_api.workspace import HermesWorkspaceStore


pytestmark = pytest.mark.unit


def initialize_projects(path):
    with sqlite3.connect(path) as db:
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


def initialize_sessions(path):
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                started_at REAL NOT NULL,
                ended_at REAL,
                cwd TEXT,
                parent_session_id TEXT,
                title TEXT,
                archived INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def test_first_added_folder_becomes_primary_and_non_member_cannot_be_removed(monkeypatch, tmp_path):
    projects_path = tmp_path / "projects.db"
    initialize_projects(projects_path)
    folder = tmp_path / "repo"
    folder.mkdir()
    monkeypatch.setenv("CONTROL_API_PROJECT_ROOTS", str(tmp_path))
    store = HermesWorkspaceStore(tmp_path)
    store.projects_path = projects_path

    created = store.create_project(ProjectCreateRequest(name="Control", folders=[str(folder)]))
    assert created.primary_folder == str(folder)
    assert created.folders == [str(folder)]

    with pytest.raises(ValueError, match="at least one folder"):
        store.remove_folder(created.project_id, str(folder))

    second = tmp_path / "second"
    second.mkdir()
    store.add_folder(created.project_id, str(second))
    with pytest.raises(KeyError):
        store.remove_folder(created.project_id, str(tmp_path / "missing"))


def test_session_filtering_applies_project_containment_before_limit(monkeypatch, tmp_path):
    projects_path = tmp_path / "projects.db"
    state_path = tmp_path / "state.db"
    initialize_projects(projects_path)
    initialize_sessions(state_path)
    folder = tmp_path / "repo"
    child = folder / "nested"
    unrelated = tmp_path / "other"
    child.mkdir(parents=True)
    unrelated.mkdir()
    monkeypatch.setenv("CONTROL_API_PROJECT_ROOTS", str(tmp_path))
    store = HermesWorkspaceStore(tmp_path)
    store.projects_path = projects_path
    store.state_path = state_path
    project = store.create_project(ProjectCreateRequest(name="Control", folders=[str(folder)]))
    with sqlite3.connect(state_path) as db:
        db.executemany(
            "INSERT INTO sessions (id, source, started_at, cwd, title) VALUES (?, ?, ?, ?, ?)",
            [
                ("new-unrelated", "cli", 30, str(unrelated), "Other"),
                ("older-matching", "cli", 20, str(child), "Nested"),
            ],
        )

    sessions = store.list_sessions(project_id=project.project_id, limit=1)

    assert [session.session_id for session in sessions] == ["older-matching"]
    assert sessions[0].project_id == project.project_id
