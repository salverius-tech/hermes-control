import pytest
from fastapi.testclient import TestClient

from services.control_api.main import create_app


pytestmark = pytest.mark.e2e


def test_mobile_user_can_connect_create_task_and_see_live_update(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"ok": True}

    with client.websocket_connect("/ws/events?token=dev-token") as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["tasks"] == []

        created = client.post(
            "/tasks",
            headers={"Authorization": "Bearer dev-token"},
            json={
                "prompt": "Use Hermes to summarize current project status",
                "project_id": "mobile-control",
                "priority": "high",
            },
        )
        assert created.status_code == 201
        task = created.json()
        assert task["status"] == "queued"
        assert task["source"] == "mobile"

        live_event = websocket.receive_json()
        assert live_event["type"] == "task.created"
        assert live_event["task"]["task_id"] == task["task_id"]

    task_detail = client.get(f"/tasks/{task['task_id']}", headers={"Authorization": "Bearer dev-token"})
    assert task_detail.status_code == 200
    assert task_detail.json()["prompt"] == "Use Hermes to summarize current project status"

    projects = client.get("/projects", headers={"Authorization": "Bearer dev-token"})
    assert projects.status_code == 200
    assert projects.json()[0]["project_id"] == "mobile-control"

    agents = client.get("/agents", headers={"Authorization": "Bearer dev-token"})
    assert agents.status_code == 200
    assert agents.json()[0]["agent_id"] == "hermes-agent"


def test_configured_sqlite_store_persists_tasks_across_app_instances(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    monkeypatch.setenv("CONTROL_API_DB_PATH", str(tmp_path / "control-api.db"))
    first_client = TestClient(create_app())

    created = first_client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Survive an API restart"},
    ).json()

    second_client = TestClient(create_app())
    response = second_client.get(f"/tasks/{created['task_id']}", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 200
    assert response.json()["prompt"] == "Survive an API restart"
