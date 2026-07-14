import pytest
from pydantic import ValidationError

from services.control_api.models import (
    AgentStatus,
    ProjectSummary,
    TaskCreateRequest,
    TaskStatus,
    TaskSummary,
)


pytestmark = pytest.mark.unit


def test_task_create_request_requires_non_empty_prompt():
    with pytest.raises(ValidationError):
        TaskCreateRequest(prompt="   ")


def test_task_create_request_requires_non_empty_project_id():
    with pytest.raises(ValidationError):
        TaskCreateRequest(prompt="Run diagnostics", project_id="   ")


def test_task_create_request_rejects_unknown_priority():
    with pytest.raises(ValidationError):
        TaskCreateRequest(prompt="Run diagnostics", priority="urgent")


def test_task_create_request_defaults_project_and_priority():
    request = TaskCreateRequest(prompt="Run the nightly maintenance checks")

    assert request.prompt == "Run the nightly maintenance checks"
    assert request.project_id == "default"
    assert request.priority == "normal"
    assert request.requires_approval is False


def test_task_summary_accepts_supported_statuses():
    summary = TaskSummary(
        task_id="task-123",
        title="Nightly checks",
        prompt="Run checks",
        status=TaskStatus.RUNNING,
        project_id="default",
    )

    assert summary.status == TaskStatus.RUNNING


def test_task_summary_accepts_blocker_metadata():
    summary = TaskSummary(
        task_id="task-blocked",
        title="Blocked task",
        prompt="Run checks",
        status=TaskStatus.BLOCKED,
        project_id="default",
        blocker_category="connection",
        blocker_message="Hermes bridge unavailable",
        blocker_retryable=True,
    )

    assert summary.status == TaskStatus.BLOCKED
    assert summary.blocker_category == "connection"
    assert summary.blocker_retryable is True


def test_task_create_request_preserves_recovery_relation_and_context():
    request = TaskCreateRequest(
        prompt="Continue the work",
        project_id="hermes-control",
        execution_folder="/home/anvil/repos/hermes-control",
        session_id="session-123",
        parent_task_id="task-parent",
        root_task_id="task-root",
        relation="continuation",
    )

    assert request.project_id == "hermes-control"
    assert request.execution_folder == "/home/anvil/repos/hermes-control"
    assert request.session_id == "session-123"
    assert request.relation == "continuation"


def test_task_summary_rejects_unknown_status():
    with pytest.raises(ValidationError):
        TaskSummary(
            task_id="task-123",
            title="Nightly checks",
            prompt="Run checks",
            status="paused",
            project_id="default",
        )


def test_project_summary_defaults_counts():
    project = ProjectSummary(project_id="default", name="Default")

    assert project.queued_count == 0
    assert project.running_count == 0
    assert project.completed_count == 0
    assert project.failed_count == 0


def test_agent_status_defaults_to_offline_without_current_task():
    status = AgentStatus(agent_id="hermes-agent")

    assert status.status == "offline"
    assert status.current_task_id is None
    assert status.project_id == "default"
