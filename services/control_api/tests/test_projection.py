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


def test_projection_archives_terminal_task_and_hides_it_from_default_list():
    projection = TaskProjection()
    task = projection.create_task(TaskCreateRequest(prompt="Archive this completed task"))
    projection.update_task(task.task_id, status=TaskStatus.COMPLETED)

    archived = projection.archive_task(task.task_id)

    assert archived.archived_at is not None
    assert projection.list_tasks() == []
    assert [task.task_id for task in projection.list_tasks(include_archived=True)] == [task.task_id]
    assert projection.list_task_events(task.task_id)[-1].event_type == "task.archived"


def test_projection_rejects_archiving_active_task_and_can_restore_archived_task():
    projection = TaskProjection()
    task = projection.create_task(TaskCreateRequest(prompt="Keep this queued task visible"))

    with pytest.raises(ValueError, match="terminal"):
        projection.archive_task(task.task_id)

    projection.update_task(task.task_id, status=TaskStatus.CANCELED)
    projection.archive_task(task.task_id)
    restored = projection.restore_task(task.task_id)

    assert restored.archived_at is None
    assert projection.list_tasks()[0].task_id == task.task_id
    assert projection.list_task_events(task.task_id)[-1].event_type == "task.restored"
