import pytest

from services.control_api.models import TaskCreateRequest, TaskStatus
from services.control_api.projection import TaskProjection


pytestmark = pytest.mark.unit


def test_projection_creates_queued_task():
    projection = TaskProjection()

    task = projection.create_task(TaskCreateRequest(prompt="Start a new Hermes task"))

    assert task.status == TaskStatus.QUEUED
    assert projection.list_tasks()[0].task_id == task.task_id


def test_projection_updates_task_status_and_progress_log():
    projection = TaskProjection()
    task = projection.create_task(TaskCreateRequest(prompt="Start a new Hermes task"))

    updated = projection.update_task(
        task.task_id,
        status=TaskStatus.RUNNING,
        progress_message="Hermes task started",
    )

    assert updated.status == TaskStatus.RUNNING
    assert updated.progress_log == ["Hermes task started"]


def test_projection_returns_project_counts():
    projection = TaskProjection()
    projection.create_task(TaskCreateRequest(prompt="Queued", project_id="alpha"))
    running = projection.create_task(TaskCreateRequest(prompt="Running", project_id="alpha"))
    projection.update_task(running.task_id, status=TaskStatus.RUNNING)

    projects = projection.list_projects()

    assert len(projects) == 1
    assert projects[0].project_id == "alpha"
    assert projects[0].queued_count == 1
    assert projects[0].running_count == 1


def test_projection_returns_default_agent_status():
    projection = TaskProjection()

    agents = projection.list_agents()

    assert len(agents) == 1
    assert agents[0].agent_id == "hermes-agent"
    assert agents[0].status == "offline"
