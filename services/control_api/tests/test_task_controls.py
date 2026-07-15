import pytest
from fastapi.testclient import TestClient

from services.control_api.main import create_app


pytestmark = pytest.mark.integration


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer dev-token"}


def test_cancel_task_marks_existing_task_canceled(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Cancel this task", "requires_approval": True},
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


def test_continue_task_creates_linked_continuation_with_same_session(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Start a session", "project_id": "ops", "session_id": "session-1"},
    ).json()

    response = client.post(
        f"/tasks/{created['task_id']}/continue",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Continue safely", "relation": "continuation"},
    )

    assert response.status_code == 201
    continuation = response.json()
    assert continuation["task_id"] != created["task_id"]
    assert continuation["prompt"] == "Continue safely"
    assert continuation["project_id"] == "ops"
    assert continuation["session_id"] == "session-1"
    assert continuation["parent_task_id"] == created["task_id"]
    assert continuation["root_task_id"] == created["task_id"]
    assert continuation["relation"] == "continuation"


def test_continue_task_creates_edited_retry_with_new_session(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Original instruction", "session_id": "session-2"},
    ).json()

    response = client.post(
        f"/tasks/{created['task_id']}/continue",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Edited instruction", "new_session": True, "relation": "edited_retry"},
    )

    assert response.status_code == 201
    edited = response.json()
    assert edited["prompt"] == "Edited instruction"
    assert edited["session_id"] is None
    assert edited["parent_task_id"] == created["task_id"]
    assert edited["root_task_id"] == created["task_id"]
    assert edited["relation"] == "edited_retry"


def test_continue_task_requires_a_session(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers=auth_headers(),
        json={"prompt": "No session here", "requires_approval": True},
    ).json()

    response = client.post(
        f"/tasks/{created['task_id']}/continue",
        headers=auth_headers(),
        json={"prompt": "Continue anyway"},
    )

    assert response.status_code == 409
    assert "no Hermes session" in response.json()["detail"]


def test_reject_non_approval_task_returns_conflict(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers=auth_headers(),
        json={"prompt": "Already executable"},
    ).json()

    response = client.post(f"/tasks/{created['task_id']}/reject", headers=auth_headers())

    assert response.status_code == 409


def test_repeated_approval_returns_conflict(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers=auth_headers(),
        json={"prompt": "Approve once", "requires_approval": True},
    ).json()

    first = client.post(f"/tasks/{created['task_id']}/approve", headers=auth_headers())
    second = client.post(f"/tasks/{created['task_id']}/approve", headers=auth_headers())

    assert first.status_code == 200
    assert second.status_code == 409


def test_execution_folder_must_be_in_an_approved_root(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.post(
        "/tasks",
        headers=auth_headers(),
        json={"prompt": "Reject unsafe cwd", "execution_folder": str(tmp_path)},
    )

    assert response.status_code == 400
    assert "approved project roots" in response.json()["detail"]
