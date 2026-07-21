import pytest

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from services.control_api.main import create_app


pytestmark = pytest.mark.integration


def test_websocket_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    try:
        with client.websocket_connect("/ws/events"):
            raise AssertionError("websocket unexpectedly connected")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008


def test_websocket_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    try:
        with client.websocket_connect("/ws/events?token=wrong"):
            raise AssertionError("websocket unexpectedly connected")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008


def test_websocket_sends_initial_snapshot(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    with client.websocket_connect("/ws/events?token=dev-token") as websocket:
        message = websocket.receive_json()

    assert message["type"] == "snapshot"
    assert message["seq"] == 0
    assert message["tasks"] == []
    assert message["projects"][0]["project_id"] == "default"
    assert message["agents"][0]["agent_id"] == "hermes-agent"


def test_websocket_broadcasts_task_created(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    with client.websocket_connect("/ws/events?token=dev-token") as websocket:
        websocket.receive_json()
        response = client.post(
            "/tasks",
            headers={"Authorization": "Bearer dev-token"},
            json={"prompt": "Broadcast this task"},
        )
        message = websocket.receive_json()

    assert response.status_code == 201
    assert message["type"] == "task.created"
    assert message["seq"] == 1
    assert message["task"]["prompt"] == "Broadcast this task"


def test_websocket_snapshot_includes_archived_tasks_for_task_history(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev-token"}
    created = client.post("/tasks", headers=headers, json={"prompt": "Keep archived history available"}).json()
    client.post(f"/tasks/{created['task_id']}/cancel", headers=headers)
    client.post(f"/tasks/{created['task_id']}/archive", headers=headers)

    with client.websocket_connect("/ws/events?token=dev-token") as websocket:
        message = websocket.receive_json()

    assert [task["task_id"] for task in message["tasks"]] == [created["task_id"]]
    assert message["tasks"][0]["archived_at"] is not None


def test_websocket_reconnect_snapshot_reconciles_sequence_and_latest_task_state(monkeypatch):
    """A reconnect snapshot is authoritative after any events missed while disconnected."""
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev-token"}

    with client.websocket_connect("/ws/events?token=dev-token") as websocket:
        assert websocket.receive_json()["seq"] == 0
        created = client.post(
            "/tasks",
            headers=headers,
            json={"prompt": "Reconcile this after reconnect", "requires_approval": True},
        )
        created_event = websocket.receive_json()

    assert created.status_code == 201
    task_id = created.json()["task_id"]
    assert created_event == {
        "type": "task.created",
        "seq": 1,
        "task": created.json(),
    }

    with client.websocket_connect("/ws/events?token=dev-token") as websocket:
        reconnect_snapshot = websocket.receive_json()
        canceled = client.post(f"/tasks/{task_id}/cancel", headers=headers)
        canceled_event = websocket.receive_json()

    assert reconnect_snapshot["type"] == "snapshot"
    assert reconnect_snapshot["seq"] == 1
    assert [task["task_id"] for task in reconnect_snapshot["tasks"]] == [task_id]
    assert reconnect_snapshot["tasks"][0]["status"] == "awaiting_approval"
    assert canceled.status_code == 200
    assert canceled_event == {
        "type": "task.updated",
        "seq": 2,
        "task": canceled.json(),
    }

    with client.websocket_connect("/ws/events?token=dev-token") as websocket:
        final_snapshot = websocket.receive_json()

    assert final_snapshot["type"] == "snapshot"
    assert final_snapshot["seq"] == 2
    assert final_snapshot["tasks"] == [canceled.json()]
