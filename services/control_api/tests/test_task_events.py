import pytest

from services.control_api.models import TaskCreateRequest, TaskStatus
from services.control_api.projection import TaskProjection
from services.control_api.storage import SQLiteTaskStore


pytestmark = pytest.mark.unit


def test_projection_records_task_events_for_creation_and_updates():
    projection = TaskProjection()

    task = projection.create_task(TaskCreateRequest(prompt="Run with events"))
    projection.update_task(task.task_id, status=TaskStatus.RUNNING, progress_message="Hermes task started")

    events = projection.list_task_events(task.task_id)

    assert [event.event_type for event in events] == ["task.created", "task.updated"]
    assert events[0].status == TaskStatus.QUEUED
    assert events[1].status == TaskStatus.RUNNING
    assert events[1].message == "Hermes task started"


def test_sqlite_task_store_reloads_task_events(tmp_path):
    db_path = tmp_path / "tasks.db"
    first_projection = TaskProjection(store=SQLiteTaskStore(db_path))
    task = first_projection.create_task(TaskCreateRequest(prompt="Persist event stream"))
    first_projection.update_task(task.task_id, status=TaskStatus.COMPLETED, result_summary="Done")

    second_projection = TaskProjection(store=SQLiteTaskStore(db_path))
    events = second_projection.list_task_events(task.task_id)

    assert [event.event_type for event in events] == ["task.created", "task.updated"]
    assert events[-1].status == TaskStatus.COMPLETED
    assert events[-1].message == "Done"
