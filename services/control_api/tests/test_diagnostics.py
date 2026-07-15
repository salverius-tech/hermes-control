import pytest
from fastapi.testclient import TestClient

from services.control_api.main import create_app
from services.control_api.workspace import HermesWorkspaceStore


pytestmark = pytest.mark.integration


def test_diagnostics_reports_backend_storage_and_execution_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    monkeypatch.setenv("CONTROL_API_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("CONTROL_API_HERMES_COMMAND", "hermes chat -q")
    monkeypatch.setenv("CONTROL_API_DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    client = TestClient(create_app())

    response = client.get("/diagnostics", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "version": "0.1.0",
        "storage": "sqlite",
        "schema_version": "1",
        "execution_mode": "command",
        "notification_mode": "discord",
        "websocket_path": "/ws/events",
        "hermes_home": str(HermesWorkspaceStore().hermes_home),
        "hermes_home_available": str(HermesWorkspaceStore().available).lower(),
    }
