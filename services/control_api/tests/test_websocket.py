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
