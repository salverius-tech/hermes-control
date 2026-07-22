from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from scripts.device_sandbox import (
    ACTIVE_ROOT_TASK_ID,
    ATTENTION_ROOT_TASK_ID,
    PROJECT_ID,
    RECENT_ROOT_TASK_ID,
    RECOVERY_SLUG,
    create_sandbox,
    destroy_sandbox,
)
from services.control_api.projection import TaskProjection
from services.control_api.storage import SQLiteTaskStore
from services.control_api.workspace import HermesWorkspaceStore


def test_create_sandbox_is_disposable_and_seeds_deterministic_populated_device_state(tmp_path):
    root = tmp_path / "device-sandbox"

    fixture = create_sandbox(root)

    assert fixture.root == root.resolve()
    assert (root / ".hermes-control-device-sandbox").read_text(encoding="utf-8") == "disposable-local-only\n"
    assert fixture.environment["CONTROL_API_TOKEN"] == "sandbox-device-token"
    assert fixture.environment["CONTROL_API_HERMES_HOME"] == str(root / "hermes-home")
    assert fixture.environment["CONTROL_API_HERMES_COMMAND"] == "cmd.exe /c exit 0"
    assert fixture.environment["CONTROL_API_DEVICE_SANDBOX"] == "1"
    assert (root / "fixture.json").is_file()
    assert fixture.maestro_env == {
        "PROJECT_ID": PROJECT_ID,
        "P6_ATTENTION_ROOT": ATTENTION_ROOT_TASK_ID,
        "P6_ACTIVE_ROOT": ACTIVE_ROOT_TASK_ID,
        "P6_RECENT_ROOT": RECENT_ROOT_TASK_ID,
        "RECOVERY_SLUG": RECOVERY_SLUG,
    }

    workspace = HermesWorkspaceStore(root / "hermes-home")
    project = workspace.get_project(PROJECT_ID)
    assert project is not None
    assert project.primary_folder == str(root / "workspaces" / PROJECT_ID)
    assert project.folders == [str(root / "workspaces" / PROJECT_ID), str(root / "workspaces" / PROJECT_ID / "repo")]
    assert [session.session_id for session in workspace.list_sessions(project_id=PROJECT_ID)] == ["sandbox-session"]

    projection = TaskProjection(SQLiteTaskStore(root / "control-api.db"), workspace, allow_synthetic_projects=False)
    threads = {thread.root_task_id: thread.latest_attempt.status for thread in projection.list_work_threads(project_id=PROJECT_ID)}
    assert threads == {
        ATTENTION_ROOT_TASK_ID: "blocked",
        ACTIVE_ROOT_TASK_ID: "queued",
        RECENT_ROOT_TASK_ID: "completed",
    }
    attention = projection.get_task(ATTENTION_ROOT_TASK_ID)
    assert attention is not None
    assert attention.session_id == "sandbox-session"

    with sqlite3.connect(root / "hermes-home" / "projects.db") as db:
        assert db.execute("SELECT slug FROM projects").fetchall() == [(PROJECT_ID,)]

    # This second managed workspace intentionally has a valid descriptor but no
    # native record, so a physical recovery-plan confirmation can make one
    # isolated, deterministic restoration without touching the populated task
    # project.
    recovery_workspace = root / "workspaces" / RECOVERY_SLUG
    assert recovery_workspace.is_dir()
    assert (recovery_workspace / "hermes-project.yaml").is_file()
    assert workspace.get_project(RECOVERY_SLUG) is None


def test_create_sandbox_provisions_a_deterministic_local_git_remote(tmp_path):
    root = tmp_path / "device-sandbox"

    fixture = create_sandbox(root)

    assert fixture.git_remote == root / "git-fixture" / "sandbox-repository.git"
    assert fixture.git_remote.is_dir()
    result = subprocess.run(
        ["git", "--git-dir", str(fixture.git_remote), "show", "HEAD:README.md"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "# Sandbox repository\n"


def test_destroy_sandbox_removes_windows_git_fixture_with_read_only_objects(tmp_path):
    root = tmp_path / "device-sandbox"
    create_sandbox(root)

    destroy_sandbox(root)

    assert not root.exists()


def test_prepare_command_runs_from_the_repository_root(tmp_path):
    root = tmp_path / "cli-sandbox"

    result = subprocess.run(
        [sys.executable, "scripts/device_sandbox.py", "prepare", "--root", str(root)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (root / "fixture.json").is_file()
