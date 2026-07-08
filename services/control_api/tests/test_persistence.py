import pytest

from services.control_api.models import TaskCreateRequest, TaskStatus
from services.control_api.projection import TaskProjection
from services.control_api.storage import SQLiteTaskStore


pytestmark = pytest.mark.unit


def test_sqlite_task_store_reloads_created_tasks(tmp_path):
    db_path = tmp_path / "tasks.db"
    first_projection = TaskProjection(store=SQLiteTaskStore(db_path))
    created = first_projection.create_task(
        TaskCreateRequest(prompt="Persist this task", project_id="durable-project", priority="high")
    )

    second_projection = TaskProjection(store=SQLiteTaskStore(db_path))
    reloaded = second_projection.get_task(created.task_id)

    assert reloaded is not None
    assert reloaded.prompt == "Persist this task"
    assert reloaded.project_id == "durable-project"
    assert reloaded.priority == "high"


def test_sqlite_task_store_reloads_task_updates(tmp_path):
    db_path = tmp_path / "tasks.db"
    first_projection = TaskProjection(store=SQLiteTaskStore(db_path))
    created = first_projection.create_task(TaskCreateRequest(prompt="Persist update"))
    first_projection.update_task(
        created.task_id,
        status=TaskStatus.RUNNING,
        progress_message="Task started",
    )

    second_projection = TaskProjection(store=SQLiteTaskStore(db_path))
    reloaded = second_projection.get_task(created.task_id)

    assert reloaded is not None
    assert reloaded.status == TaskStatus.RUNNING
    assert reloaded.progress_log == ["Task started"]
