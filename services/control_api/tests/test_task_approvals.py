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


def test_approve_unknown_task_returns_404(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.post("/tasks/task-missing/approve", headers=auth_headers())

    assert response.status_code == 404
