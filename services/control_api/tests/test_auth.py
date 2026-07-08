import os

import pytest

from fastapi.testclient import TestClient

from services.control_api.main import create_app


pytestmark = pytest.mark.integration


def test_health_does_not_require_auth(monkeypatch):
    monkeypatch.delenv("CONTROL_API_TOKEN", raising=False)
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_tasks_require_bearer_token(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.get("/tasks")

    assert response.status_code == 401


def test_tasks_reject_invalid_bearer_token(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.get("/tasks", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401


def test_tasks_reject_malformed_authorization_header(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.get("/tasks", headers={"Authorization": "Token dev-token"})

    assert response.status_code == 401


def test_tasks_accept_valid_bearer_token(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.get("/tasks", headers={"Authorization": "Bearer dev-token"})

    assert response.status_code == 200
    assert response.json() == []
