import pytest
from fastapi.testclient import TestClient

from services.control_api.main import create_app


pytestmark = pytest.mark.integration


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer dev-token"}


def test_create_task_can_require_approval_before_execution(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.post(
        "/tasks",
        headers=auth_headers(),
        json={"prompt": "Delete old build artifacts", "requires_approval": True},
    )

    assert response.status_code == 201
    task = response.json()
    assert task["status"] == "awaiting_approval"
    assert task["requires_approval"] is True
    events = client.get(f"/tasks/{task['task_id']}/events", headers=auth_headers()).json()
    assert [event["event_type"] for event in events] == ["task.created", "task.approval_requested"]


def test_approve_task_moves_approval_required_task_to_queue(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    task = client.post(
        "/tasks",
        headers=auth_headers(),
        json={"prompt": "Restart service", "requires_approval": True},
    ).json()

    response = client.post(f"/tasks/{task['task_id']}/approve", headers=auth_headers())

    assert response.status_code == 200
    approved = response.json()
    assert approved["status"] == "queued"
    events = client.get(f"/tasks/{task['task_id']}/events", headers=auth_headers()).json()
    assert "task.approved" in [event["event_type"] for event in events]


def test_approval_audit_metadata_survives_sqlite_reload(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    monkeypatch.setenv("CONTROL_API_DB_PATH", str(tmp_path / "tasks.db"))
    headers = auth_headers()
    first_client = TestClient(create_app())
    task = first_client.post(
        "/tasks",
        headers=headers,
        json={"prompt": "Approve the durable audit", "requires_approval": True},
    ).json()

    response = first_client.post(
        f"/tasks/{task['task_id']}/approve",
        headers=headers,
        json={"actor": "operator", "device_id": "phone-1", "reason": "Reviewed on mobile"},
    )

    assert response.status_code == 200
    reloaded_events = TestClient(create_app()).get(f"/tasks/{task['task_id']}/events", headers=headers)
    assert reloaded_events.status_code == 200
    audit = next(event for event in reloaded_events.json() if event["event_type"] == "approval.audit")
    assert audit["status"] == "queued"
    assert audit["message"] == "Reviewed on mobile"
    assert audit["metadata"] == {
        "actor": "operator",
        "device_id": "phone-1",
        "reason": "Reviewed on mobile",
    }


def test_reject_task_records_rejection(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    task = client.post(
        "/tasks",
        headers=auth_headers(),
        json={"prompt": "Run risky migration", "requires_approval": True},
    ).json()

    response = client.post(
        f"/tasks/{task['task_id']}/reject",
        headers=auth_headers(),
        json={"actor": "operator", "device_id": "phone-1", "reason": "Not safe yet"},
    )

    assert response.status_code == 200
    rejected = response.json()
    assert rejected["status"] == "rejected"
    events = client.get(f"/tasks/{task['task_id']}/events", headers=auth_headers()).json()
    assert events[-1]["event_type"] == "approval.audit"
    assert events[-1]["metadata"] == {"actor": "operator", "device_id": "phone-1", "reason": "Not safe yet"}
    assert events[-2]["event_type"] == "task.rejected"


def test_project_metrics_and_events_are_available(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    headers = auth_headers()
    task = client.post("/tasks", headers=headers, json={"prompt": "Inspect project"}).json()

    metrics = client.get("/projects/default/metrics", headers=headers)
    events = client.get("/projects/default/events", headers=headers)

    assert metrics.status_code == 200
    assert metrics.json()["total"] == 1
    assert events.status_code == 200
    assert events.json()[0]["task_id"] == task["task_id"]


def test_project_files_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    monkeypatch.setenv("CONTROL_API_PROJECT_ROOTS", str(tmp_path))
    client = TestClient(create_app())
    headers = auth_headers()
    project_db = tmp_path / ".hermes" / "projects.db"
    project_db.parent.mkdir()
    # The synthetic projection has no folders, so a traversal request must not expose host paths.
    response = client.get("/projects/default/files?path=..", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


def test_approve_unknown_task_returns_404(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.post("/tasks/task-missing/approve", headers=auth_headers())

    assert response.status_code == 404
