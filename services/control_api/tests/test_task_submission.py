import pytest

from fastapi.testclient import TestClient

from services.control_api.main import create_app


pytestmark = pytest.mark.integration


def test_create_task_returns_generated_task_summary(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Check the status of my Hermes projects", "project_id": "default"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["task_id"]
    assert body["project_id"] == "default"
    assert body["prompt"] == "Check the status of my Hermes projects"
    assert body["status"] == "queued"
    assert body["source"] == "mobile"


def test_create_task_rejects_blank_prompt(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "   "},
    )

    assert response.status_code == 422


def test_create_task_rejects_blank_project_id(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Run diagnostics", "project_id": "   "},
    )

    assert response.status_code == 422


def test_get_task_returns_404_for_unknown_task(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.get("/tasks/task-missing", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_create_task_can_be_read_back_from_list(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Summarize current running tasks"},
    ).json()

    response = client.get("/tasks", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 200
    assert response.json()[0]["task_id"] == created["task_id"]


def test_create_task_can_be_read_back_by_id(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Open a Hermes planning session"},
    ).json()

    response = client.get(
        f"/tasks/{created['task_id']}",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert response.status_code == 200
    assert response.json()["prompt"] == "Open a Hermes planning session"


def test_mutating_task_requests_are_rate_limited(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    monkeypatch.setenv("CONTROL_API_RATE_LIMIT_PER_MINUTE", "1")
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev-token"}
    payload = {"prompt": "first", "project_id": "default"}

    assert client.post("/tasks", headers=headers, json=payload).status_code == 201
    response = client.post("/tasks", headers=headers, json={**payload, "prompt": "second"})

    assert response.status_code == 429


def test_idempotency_key_returns_the_original_task(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev-token", "Idempotency-Key": "local-1"}

    first = client.post("/tasks", headers=headers, json={"prompt": "first"})
    second = client.post("/tasks", headers=headers, json={"prompt": "different retry"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["task_id"] == first.json()["task_id"]
