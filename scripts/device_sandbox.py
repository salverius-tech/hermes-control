"""Create a disposable, local-only Control API fixture for device validation.

The fixture is deliberately self-contained: it creates a temporary Hermes home,
workspace, native-project SQLite records, and Control API SQLite records below a
caller-supplied directory.  It never reads a user profile, credentials, or real
project files.  `destroy` refuses to remove a directory without the marker this
module writes during `prepare`.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from urllib.request import Request, urlopen
from pathlib import Path

# Running `python scripts/device_sandbox.py` makes Python put scripts/ on
# sys.path, not the repository root where the services package lives.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.control_api.models import TaskCreateRequest, TaskExecutionState, TaskStatus
from services.control_api.projection import TaskProjection
from services.control_api.storage import SQLiteTaskStore
from services.control_api.workspace import HermesWorkspaceStore

PROJECT_ID = "sandbox-mobile-project"
ATTENTION_ROOT_TASK_ID = "sandbox-attention-root"
ACTIVE_ROOT_TASK_ID = "sandbox-active-root"
RECENT_ROOT_TASK_ID = "sandbox-recent-root"
RECOVERY_SLUG = "sandbox-recovery-ready"
SANDBOX_TOKEN = "sandbox-device-token"
MARKER = ".hermes-control-device-sandbox"


@dataclass(frozen=True)
class SandboxFixture:
    root: Path
    git_remote: Path
    environment: dict[str, str]
    maestro_env: dict[str, str]

    def git_http_url(self, port: int) -> str:
        """Return the fixture's loopback-only dumb-HTTP clone URL."""
        if not 1 <= port <= 65535:
            raise ValueError("Git fixture port must be in 1..65535")
        return f"http://127.0.0.1:{port}/{self.git_remote.name}"


def _initialize_native_projects(home: Path, workspace: Path) -> None:
    with sqlite3.connect(home / "projects.db") as db:
        db.executescript(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY, slug TEXT NOT NULL, name TEXT NOT NULL,
                description TEXT, primary_path TEXT, created_at INTEGER NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE project_folders (
                project_id TEXT NOT NULL, path TEXT NOT NULL, label TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0, added_at INTEGER NOT NULL,
                PRIMARY KEY (project_id, path)
            );
            """
        )
        db.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("p_sandbox", PROJECT_ID, "Sandbox mobile project", "Disposable device fixture", str(workspace), 1, 0),
        )
        for path, label, primary in ((workspace, "workspace", 1), (workspace / "repo", "repository", 0)):
            db.execute(
                "INSERT INTO project_folders VALUES (?, ?, ?, ?, ?)",
                ("p_sandbox", str(path), label, primary, 1),
            )


def _initialize_native_session(home: Path, workspace: Path) -> None:
    with sqlite3.connect(home / "state.db") as db:
        db.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT, source TEXT, started_at INTEGER, "
            "ended_at INTEGER, cwd TEXT, parent_session_id TEXT, archived INTEGER NOT NULL DEFAULT 0)"
        )
        db.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("sandbox-session", "Sandbox device session", "fixture", 3, 3, str(workspace), None, 0),
        )


def _initialize_recovery_workspace(root: Path) -> Path:
    """Seed one valid managed workspace deliberately absent from projects.db."""
    workspace = root / "workspaces" / RECOVERY_SLUG
    workspace.mkdir()
    (workspace / "hermes-project.yaml").write_text(
        "\n".join((
            "schema_version: 1",
            "identity:",
            f"  slug: {RECOVERY_SLUG}",
            "  name: Sandbox Recovery Ready",
            "  workspace_id: sandbox-recovery-workspace",
            "workspace:",
            "  folders:",
            "    - path: .",
            "      role: workspace",
            "      primary: true",
            "lifecycle:",
            "  created_at: '2026-07-21T00:00:00Z'",
            "  native_registration: registration_failed",
            "",
        )),
        encoding="utf-8",
    )
    return workspace


def _initialize_git_remote(root: Path) -> Path:
    """Create a committed bare remote served only by a caller's loopback HTTP server."""
    fixture_root = root / "git-fixture"
    remote = fixture_root / "sandbox-repository.git"
    source = fixture_root / "seed"
    fixture_root.mkdir()
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    source.mkdir()
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True, text=True)
    (source / "README.md").write_text("# Sandbox repository\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=Hermes Sandbox", "-c", "user.email=sandbox@example.invalid", "commit", "-m", "Seed sandbox repository"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "-C", str(source), "remote", "add", "origin", str(remote)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(source), "push", "origin", "HEAD:main"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "--git-dir", str(remote), "update-server-info"], check=True, capture_output=True, text=True)
    # Keep the seed checkout inside the marker-protected fixture. Git's object
    # files may be read-only on Windows, while destroying the whole sandbox is
    # already the deliberate cleanup boundary.
    return remote


def _create_seed_task(
    projection: TaskProjection,
    *,
    task_id: str,
    prompt: str,
    status: TaskStatus,
    session_id: str | None = None,
) -> None:
    task = projection.create_task(TaskCreateRequest(prompt=prompt, project_id=PROJECT_ID, execution_folder=None, session_id=session_id))
    original_id = task.task_id
    # IDs are deterministic so Maestro selectors do not depend on generated UUIDs.
    projection._tasks.pop(original_id)  # noqa: SLF001 - fixture owns its isolated store.
    task = task.model_copy(update={"task_id": task_id, "root_task_id": task_id})
    projection._tasks[task_id] = task  # noqa: SLF001 - fixture owns its isolated store.
    projection._store.save_task(task)  # type: ignore[union-attr]  # noqa: SLF001
    with sqlite3.connect(projection._store.path) as db:  # type: ignore[union-attr]  # noqa: SLF001
        db.execute("DELETE FROM tasks WHERE task_id = ?", (original_id,))
        db.execute("UPDATE task_events SET task_id = ? WHERE task_id = ?", (task_id, original_id))
    projection.update_task(
        task_id,
        status=status,
        progress_message=f"Fixture task is {status.value}",
        result_summary="Fixture task completed" if status is TaskStatus.COMPLETED else None,
        blocker_category="fixture" if status is TaskStatus.ATTENTION_REQUIRED else None,
        blocker_message="Fixture task needs an operator decision" if status is TaskStatus.ATTENTION_REQUIRED else None,
        blocker_retryable=status is TaskStatus.ATTENTION_REQUIRED,
        execution_state=TaskExecutionState.ACTIVE if status is TaskStatus.RUNNING else TaskExecutionState.UNKNOWN,
    )


def create_sandbox(root: Path) -> SandboxFixture:
    root = root.expanduser().resolve()
    if root.exists():
        raise FileExistsError(f"Sandbox root already exists; refusing to reuse or overwrite it: {root}")
    home = root / "hermes-home"
    workspace = root / "workspaces" / PROJECT_ID
    (workspace / "repo").mkdir(parents=True)
    (workspace / "README.md").write_text("# Disposable device sandbox\n", encoding="utf-8")

    root.joinpath(MARKER).write_text("disposable-local-only\n", encoding="utf-8")
    home.mkdir()
    _initialize_native_projects(home, workspace)
    _initialize_native_session(home, workspace)
    _initialize_recovery_workspace(root)
    git_remote = _initialize_git_remote(root)
    store = SQLiteTaskStore(root / "control-api.db")
    projection = TaskProjection(store, HermesWorkspaceStore(home), allow_synthetic_projects=False)
    # Blocked and queued work are active Inbox categories but are not auto-resumed
    # by the API startup recovery loop, keeping this fixture stable. The blocked
    # task also exposes the retry/continuation controls for task-detail review.
    _create_seed_task(
        projection,
        task_id=ATTENTION_ROOT_TASK_ID,
        prompt="Review sandbox blocked work",
        status=TaskStatus.BLOCKED,
        session_id="sandbox-session",
    )
    _create_seed_task(projection, task_id=ACTIVE_ROOT_TASK_ID, prompt="Run sandbox work", status=TaskStatus.QUEUED)
    _create_seed_task(projection, task_id=RECENT_ROOT_TASK_ID, prompt="Completed sandbox work", status=TaskStatus.COMPLETED)
    environment = {
        "CONTROL_API_TOKEN": SANDBOX_TOKEN,
        "CONTROL_API_DB_PATH": str(root / "control-api.db"),
        "CONTROL_API_HERMES_HOME": str(home),
        "CONTROL_API_WORKSPACE_ROOT": str(root / "workspaces"),
        "CONTROL_API_PROJECT_ROOTS": str(root / "workspaces"),
        "CONTROL_API_ALLOW_SYNTHETIC_PROJECTS": "0",
        "CONTROL_API_RESUME_TASKS_ON_STARTUP": "0",
        "CONTROL_API_DEVICE_SANDBOX": "1",
        # `CONTROL_API_HERMES_COMMAND` is tokenized with POSIX-style shlex by
        # the API. A Windows Python path plus a script argument can therefore
        # be mis-tokenized; cmd.exe is path-safe and exits successfully without
        # touching a real executor or profile.
        "CONTROL_API_HERMES_COMMAND": "cmd.exe /c exit 0",
    }
    maestro_env = {
        "PROJECT_ID": PROJECT_ID,
        "P6_ATTENTION_ROOT": ATTENTION_ROOT_TASK_ID,
        "P6_ACTIVE_ROOT": ACTIVE_ROOT_TASK_ID,
        "P6_RECENT_ROOT": RECENT_ROOT_TASK_ID,
        "RECOVERY_SLUG": RECOVERY_SLUG,
    }
    fixture = SandboxFixture(root=root, git_remote=git_remote, environment=environment, maestro_env=maestro_env)
    (root / "fixture.json").write_text(
        json.dumps({"environment": environment, "maestro_env": maestro_env}, indent=2) + "\n",
        encoding="utf-8",
    )
    return fixture


def load_sandbox(root: Path) -> SandboxFixture:
    root = root.expanduser().resolve()
    marker = root / MARKER
    metadata = root / "fixture.json"
    if not marker.is_file() or marker.read_text(encoding="utf-8") != "disposable-local-only\n" or not metadata.is_file():
        raise ValueError(f"Not a prepared disposable sandbox: {root}")
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    return SandboxFixture(
        root=root,
        git_remote=root / "git-fixture" / "sandbox-repository.git",
        environment=payload["environment"],
        maestro_env=payload["maestro_env"],
    )


def destroy_sandbox(root: Path) -> None:
    root = root.expanduser().resolve()
    marker = root / MARKER
    if not marker.is_file() or marker.read_text(encoding="utf-8") != "disposable-local-only\n":
        raise ValueError(f"Refusing to remove unmarked path: {root}")
    # Git fixture object files may be read-only on Windows.
    def clear_readonly(function, path, exc_info):  # type: ignore[no-untyped-def]
        del exc_info
        os.chmod(path, stat.S_IWRITE)
        function(path)

    # sqlite3 connection objects are finalized lazily on Windows. Collect and
    # retry briefly so a just-created fixture can be safely torn down in tests.
    gc.collect()
    for attempt in range(3):
        try:
            shutil.rmtree(root, onerror=clear_readonly)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.1)


def _print_fixture(fixture: SandboxFixture) -> None:
    print(json.dumps({"root": str(fixture.root), "environment": fixture.environment, "maestro_env": fixture.maestro_env}, indent=2))


def serve_sandbox(root: Path, port: int) -> None:
    """Serve only a previously prepared fixture on 127.0.0.1."""
    fixture = load_sandbox(root)
    os.environ.update(fixture.environment)
    import uvicorn

    uvicorn.run("services.control_api.main:create_app", factory=True, host="127.0.0.1", port=port)


def disconnect_websockets(root: Path, port: int) -> int:
    """Request the fixture-only close hook without exposing it beyond loopback."""
    if not 1 <= port <= 65535:
        raise ValueError("Control API port must be in 1..65535")
    fixture = load_sandbox(root)
    request = Request(
        f"http://127.0.0.1:{port}/__sandbox__/websocket-disconnect",
        data=b"",
        headers={"Authorization": f"Bearer {fixture.environment['CONTROL_API_TOKEN']}"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:  # noqa: S310 - fixed loopback fixture URL.
        payload = json.load(response)
    return int(payload["closed"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or remove a disposable local-only device fixture.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "destroy", "serve", "disconnect"):
        subparser = subcommands.add_parser(command)
        subparser.add_argument("--root", type=Path, required=True, help="new disposable sandbox directory")
        if command in {"serve", "disconnect"}:
            subparser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if args.command == "prepare":
        _print_fixture(create_sandbox(args.root))
        return
    if args.command == "serve":
        serve_sandbox(args.root, args.port)
        return
    if args.command == "disconnect":
        print(json.dumps({"closed": disconnect_websockets(args.root, args.port)}))
        return
    destroy_sandbox(args.root)
    print(f"Removed disposable sandbox: {args.root.expanduser().resolve()}")


if __name__ == "__main__":
    main()
