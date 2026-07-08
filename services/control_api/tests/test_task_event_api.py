import pytest
from fastapi.testclient import TestClient

from services.control_api.main import create_app


pytestmark = pytest.mark.integration


def test_task_events_can_be_read_back_by_id(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Open an observable Hermes task"},
    ).json()

    response = client.get(
        f"/tasks/{created['task_id']}/events",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert response.status_code == 200
    assert response.json()[0]["event_type"] == "task.created"


def test_task_events_returns_404_for_unknown_task(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.get("/tasks/task-missing/events", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"
