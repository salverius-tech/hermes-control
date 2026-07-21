import sqlite3

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


def test_sqlite_task_store_tracks_schema_version(tmp_path):
    db_path = tmp_path / "tasks.db"

    store = SQLiteTaskStore(db_path)
    with sqlite3.connect(db_path) as connection:
        version = connection.execute("SELECT version FROM schema_migrations WHERE name = ?", ("control_api",)).fetchone()

    assert version == (store.schema_version,)


def test_sqlite_task_store_reloads_archived_task(tmp_path):
    db_path = tmp_path / "tasks.db"
    first_projection = TaskProjection(store=SQLiteTaskStore(db_path))
    task = first_projection.create_task(TaskCreateRequest(prompt="Persist archived task"))
    first_projection.update_task(task.task_id, status=TaskStatus.COMPLETED)
    first_projection.archive_task(task.task_id)

    reloaded = TaskProjection(store=SQLiteTaskStore(db_path)).get_task(task.task_id)

    assert reloaded is not None
    assert reloaded.archived_at is not None


def test_sqlite_task_store_reloads_work_thread_lineage(tmp_path):
    db_path = tmp_path / "tasks.db"
    first = TaskProjection(store=SQLiteTaskStore(db_path))
    root = first.create_task(TaskCreateRequest(prompt="Recover deployment", project_id="ops"))
    first.update_task(root.task_id, status=TaskStatus.FAILED)
    retry = first.create_task(TaskCreateRequest(prompt="Recover deployment", project_id="ops", parent_task_id=root.task_id, root_task_id=root.task_id, relation="retry"))
    first.update_task(retry.task_id, status=TaskStatus.COMPLETED)

    threads = TaskProjection(store=SQLiteTaskStore(db_path)).list_work_threads(project_id="ops")

    assert len(threads) == 1
    assert [attempt.task_id for attempt in threads[0].attempts] == [root.task_id, retry.task_id]
    assert threads[0].latest_attempt.task_id == retry.task_id
