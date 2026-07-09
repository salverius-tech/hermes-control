import pytest
from fastapi.testclient import TestClient

from services.control_api.main import create_app


pytestmark = pytest.mark.integration


def test_cancel_task_marks_existing_task_canceled(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Cancel this task"},
    ).json()

    response = client.post(f"/tasks/{created['task_id']}/cancel", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    events = client.get(f"/tasks/{created['task_id']}/events", headers={"Authorization": "Bearer dev-token"}).json()
    assert events[-1]["event_type"] == "task.canceled"


def test_cancel_unknown_task_returns_404(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.post("/tasks/task-missing/cancel", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 404


def test_retry_task_creates_new_task_with_original_prompt(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Retry this task", "project_id": "ops", "priority": "high"},
    ).json()

    response = client.post(f"/tasks/{created['task_id']}/retry", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 201
    retried = response.json()
    assert retried["task_id"] != created["task_id"]
    assert retried["prompt"] == "Retry this task"
    assert retried["project_id"] == "ops"
    assert retried["priority"] == "high"
    assert retried["status"] == "queued"
