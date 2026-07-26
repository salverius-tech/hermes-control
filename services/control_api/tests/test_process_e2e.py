from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.e2e


@pytest.fixture
def process_server(tmp_path: Path):
    port_socket = socket.socket()
    port_socket.bind(("127.0.0.1", 0))
    port = port_socket.getsockname()[1]
    port_socket.close()

    executor = tmp_path / "fixture_executor.py"
    executor.write_text(
        "import sys\n"
        "prompt = sys.stdin.read()\n"
        "if 'PROCESS-E2E-FAIL' in prompt:\n"
        "    print('fixture executor failed', file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
        "print('PROCESS-E2E-PROGRESS', flush=True)\n"
        "print('PROCESS-E2E-READY', flush=True)\n"
        "print('Session: process-e2e-session', flush=True)\n"
    )
    database = tmp_path / "control-api.db"
    environment = os.environ.copy()
    environment.update(
        {
            "CONTROL_API_TOKEN": "process-e2e-token",
            "CONTROL_API_DB_PATH": str(database),
            "CONTROL_API_ALLOW_SYNTHETIC_PROJECTS": "1",
            "CONTROL_API_REQUIRE_TASK_APPROVAL": "1",
            "CONTROL_API_HERMES_COMMAND": f"{sys.executable} {executor}",
            "CONTROL_API_RESUME_TASKS_ON_STARTUP": "1",
            "CONTROL_API_RATE_LIMIT_PER_MINUTE": "1000",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "services.control_api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{base_url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("process-level API did not become ready")
        yield base_url, environment, database, executor
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _client(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url, headers={"Authorization": "Bearer process-e2e-token"}, timeout=5)


def _wait_for_status(client: httpx.Client, task_id: str, expected: str) -> dict:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        task = client.get(f"/tasks/{task_id}").json()
        if task["status"] == expected:
            return task
        time.sleep(0.1)
    raise AssertionError(f"task {task_id} did not reach {expected}")


def test_process_api_approval_progress_completion_and_restart_persistence(process_server):
    base_url, environment, database, executor = process_server
    with _client(base_url) as client:
        websocket_url = base_url.replace("http://", "ws://") + "/ws/events?token=process-e2e-token"
        with connect(websocket_url, open_timeout=5, close_timeout=5) as websocket:
            snapshot = websocket.recv()
            snapshot_text = snapshot.decode() if isinstance(snapshot, bytes) else snapshot
            assert '"type":"snapshot"' in snapshot_text
            created = client.post("/tasks", json={"prompt": "PROCESS-E2E-READY", "project_id": "process-project"})
            assert created.status_code == 201
            task = created.json()
            assert task["status"] == "awaiting_approval"
            approved = client.post(f"/tasks/{task['task_id']}/approve", json={"reason": "process e2e"})
            assert approved.status_code == 200
            completed = _wait_for_status(client, task["task_id"], "completed")
            assert "PROCESS-E2E-READY" in completed["result_summary"]
            assert completed["session_id"] == "process-e2e-session"
            events = client.get(f"/tasks/{task['task_id']}/events").json()
            event_types = {event["event_type"] for event in events}
            assert {"task.created", "task.started", "task.progress", "task.completed"} <= event_types

    restarted = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "services.control_api.main:app", "--host", "127.0.0.1", "--port", base_url.rsplit(":", 1)[1]],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with _client(base_url) as client:
            _wait_for_status(client, task["task_id"], "completed")
            persisted_events = client.get(f"/tasks/{task['task_id']}/events").json()
            assert any(event["event_type"] == "task.completed" for event in persisted_events)
    finally:
        restarted.terminate()
        restarted.wait(timeout=5)


def test_process_api_reports_executor_failure_as_failed_task(process_server):
    base_url, _, _, _ = process_server
    with _client(base_url) as client:
        created = client.post("/tasks", json={"prompt": "PROCESS-E2E-FAIL", "project_id": "process-project"})
        task_id = created.json()["task_id"]
        assert client.post(f"/tasks/{task_id}/approve", json={"reason": "failure probe"}).status_code == 200
        failed = _wait_for_status(client, task_id, "failed")
        assert "fixture executor failed" in failed["error"]
        events = client.get(f"/tasks/{task_id}/events").json()
        assert any(event["event_type"] == "task.failed" for event in events)
