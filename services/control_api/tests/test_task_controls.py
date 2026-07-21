import pytest
from fastapi.testclient import TestClient

from services.control_api.hermes_client import HermesTaskService
from services.control_api.main import create_app
from services.control_api.models import TaskStatus


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


def test_archive_terminal_task_hides_it_from_default_list_and_can_be_restored(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev-token"}
    created = client.post("/tasks", headers=headers, json={"prompt": "Archive this task"}).json()
    client.post(f"/tasks/{created['task_id']}/cancel", headers=headers)

    archived = client.post(f"/tasks/{created['task_id']}/archive", headers=headers)

    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert client.get("/tasks", headers=headers).json() == []
    assert client.get("/tasks?include_archived=true", headers=headers).json()[0]["task_id"] == created["task_id"]
    assert client.post(f"/tasks/{created['task_id']}/restore", headers=headers).json()["archived_at"] is None


def test_archive_active_or_unknown_task_returns_clear_error(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer dev-token"}
    created = client.post(
        "/tasks",
        headers=headers,
        json={"prompt": "Do not archive active work", "requires_approval": True},
    ).json()

    active_response = client.post(f"/tasks/{created['task_id']}/archive", headers=headers)
    unknown_response = client.post("/tasks/task-missing/archive", headers=headers)

    assert active_response.status_code == 409
    assert "terminal" in active_response.json()["detail"]
    assert unknown_response.status_code == 404


def test_retry_task_creates_new_task_with_original_prompt(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Retry this task", "project_id": "ops", "priority": "high"},
    ).json()

    headers = {"Authorization": "Bearer dev-token", "Idempotency-Key": "retry-original"}
    response = client.post(f"/tasks/{created['task_id']}/retry", headers=headers)
    repeated = client.post(f"/tasks/{created['task_id']}/retry", headers=headers)

    assert response.status_code == 201
    assert repeated.status_code == 201
    retried = response.json()
    assert repeated.json()["task_id"] == retried["task_id"]
    assert retried["task_id"] != created["task_id"]
    assert retried["prompt"] == "Retry this task"
    assert retried["project_id"] == "ops"
    assert retried["priority"] == "high"
    assert retried["status"] == "queued"


def test_get_missing_work_thread_returns_404(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())

    response = client.get("/work-threads/task-missing", headers=auth_headers())

    assert response.status_code == 404
    assert response.json()["detail"] == "work thread not found"


def test_work_thread_contract_uses_completed_retry_as_latest_for_historical_root(monkeypatch):
    """A historical attempt must resolve to its newer successful outcome."""
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")

    def complete_attempt(self, task, request, *, on_update=None):
        status = TaskStatus.COMPLETED if request.relation == "retry" else TaskStatus.FAILED
        self.projection.update_task(task.task_id, status=status)

    monkeypatch.setattr(HermesTaskService, "start_task", complete_attempt)
    client = TestClient(create_app())

    root = client.post("/tasks", headers=auth_headers(), json={"prompt": "Repair deployment", "project_id": "ops"}).json()
    assert client.get(f"/tasks/{root['task_id']}", headers=auth_headers()).json()["status"] == "failed"

    retry = client.post(f"/tasks/{root['task_id']}/retry", headers=auth_headers())
    assert retry.status_code == 201

    listed = client.get("/work-threads?project_id=ops", headers=auth_headers())
    historical_link = client.get(f"/work-threads/{root['task_id']}", headers=auth_headers())

    assert listed.status_code == 200
    assert len(listed.json()) == 1
    thread = historical_link.json()
    assert historical_link.status_code == 200
    assert thread["root_task_id"] == root["task_id"]
    assert [attempt["task_id"] for attempt in thread["attempts"]] == [root["task_id"], retry.json()["task_id"]]
    assert thread["attempts"][0]["status"] == "failed"
    assert thread["latest_attempt"]["task_id"] == retry.json()["task_id"]
    assert thread["latest_outcome"] == "completed"


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


def test_edit_retry_creates_edited_retry_with_new_session(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Original instruction", "session_id": "session-2"},
    ).json()

    response = client.post(
        f"/tasks/{created['task_id']}/edit-retry",
        headers={"Authorization": "Bearer dev-token"},
        json={"prompt": "Edited instruction"},
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


def test_recovery_actions_are_guarded_when_original_task_is_active(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers=auth_headers(),
        json={"prompt": "Wait for approval", "session_id": "session-active", "requires_approval": True},
    ).json()

    retry = client.post(f"/tasks/{created['task_id']}/retry", headers=auth_headers())
    continuation = client.post(
        f"/tasks/{created['task_id']}/continue", headers=auth_headers(), json={"prompt": "Do not duplicate"}
    )
    edited = client.post(
        f"/tasks/{created['task_id']}/edit-retry", headers=auth_headers(), json={"prompt": "Reworded"}
    )
    new_session = client.post(f"/tasks/{created['task_id']}/new-session", headers=auth_headers(), json={})

    assert [response.status_code for response in (retry, continuation, edited, new_session)] == [409, 409, 409, 409]
    assert client.get("/tasks", headers=auth_headers()).json()[0]["task_id"] == created["task_id"]


def test_recovery_controls_are_linked_idempotent_and_environment_check_does_not_retry(monkeypatch):
    monkeypatch.setenv("CONTROL_API_TOKEN", "dev-token")
    client = TestClient(create_app())
    created = client.post(
        "/tasks",
        headers=auth_headers(),
        json={"prompt": "Recover this safely", "session_id": "session-recovery", "requires_approval": True},
    ).json()
    canceled = client.post(f"/tasks/{created['task_id']}/cancel", headers=auth_headers())
    repeated_cancel = client.post(f"/tasks/{created['task_id']}/cancel", headers=auth_headers())
    assert canceled.status_code == 200
    assert repeated_cancel.status_code == 409
    event_count = len(client.get(f"/tasks/{created['task_id']}/events", headers=auth_headers()).json())

    environment = client.get(f"/tasks/{created['task_id']}/environment", headers=auth_headers())
    continuation_headers = {**auth_headers(), "Idempotency-Key": "continue-recovery"}
    first_continue = client.post(
        f"/tasks/{created['task_id']}/continue", headers=continuation_headers, json={"prompt": "Continue in place"}
    )
    second_continue = client.post(
        f"/tasks/{created['task_id']}/continue", headers=continuation_headers, json={"prompt": "Continue in place"}
    )
    edited_headers = {**auth_headers(), "Idempotency-Key": "edit-recovery"}
    edited = client.post(
        f"/tasks/{created['task_id']}/edit-retry", headers=edited_headers, json={"prompt": "Edited recovery"}
    )
    edited_repeat = client.post(
        f"/tasks/{created['task_id']}/edit-retry", headers=edited_headers, json={"prompt": "Edited recovery"}
    )
    new_session_headers = {**auth_headers(), "Idempotency-Key": "new-session-recovery"}
    new_session = client.post(f"/tasks/{created['task_id']}/new-session", headers=new_session_headers, json={})
    new_session_repeat = client.post(f"/tasks/{created['task_id']}/new-session", headers=new_session_headers, json={})

    assert environment.status_code == 200
    assert environment.json() == {
        "task_id": created["task_id"],
        "ready": False,
        "project_ready": True,
        "session_ready": True,
        "executor_ready": False,
        "issues": ["Hermes executor is not ready"],
    }
    assert len(client.get(f"/tasks/{created['task_id']}/events", headers=auth_headers()).json()) == event_count
    assert first_continue.status_code == second_continue.status_code == 201
    assert first_continue.json()["task_id"] == second_continue.json()["task_id"]
    assert first_continue.json()["session_id"] == "session-recovery"
    assert edited.json()["relation"] == "edited_retry"
    assert edited.json()["task_id"] == edited_repeat.json()["task_id"]
    assert edited.json()["session_id"] is None
    assert new_session.json()["relation"] == "retry"
    assert new_session.json()["task_id"] == new_session_repeat.json()["task_id"]
    assert new_session.json()["prompt"] == "Recover this safely"
    assert new_session.json()["session_id"] is None
