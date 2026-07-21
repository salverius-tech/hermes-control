import pytest

from services.control_api.hermes_client import FakeHermesExecutor, HermesTaskService
from services.control_api.models import TaskCreateRequest, TaskExecutionState, TaskStatus
from services.control_api.projection import TaskProjection
from services.control_api.storage import SQLiteTaskStore


pytestmark = pytest.mark.unit


@pytest.mark.anyio
async def test_task_service_distinguishes_completed_failed_and_ordinary_blocked_outcomes():
    projection = TaskProjection()
    completed = await HermesTaskService(
        projection=projection,
        executor=FakeHermesExecutor(result_summary="Hermes finished normally"),
    ).submit_task(TaskCreateRequest(prompt="Complete this task"), run_inline=True)
    failed = await HermesTaskService(
        projection=projection,
        executor=FakeHermesExecutor(error="Hermes command exited with 1"),
    ).submit_task(TaskCreateRequest(prompt="Fail this task"), run_inline=True)
    blocked = await HermesTaskService(
        projection=projection,
        executor=FakeHermesExecutor(error="Hermes execution is not configured"),
    ).submit_task(TaskCreateRequest(prompt="Block this task"), run_inline=True)

    assert completed.status == TaskStatus.COMPLETED
    assert completed.result_summary == "Hermes finished normally"
    assert completed.error is None
    assert completed.blocker_category is None
    assert projection.list_task_events(completed.task_id)[-1].event_type == "task.completed"

    assert failed.status == TaskStatus.FAILED
    assert failed.error == "Hermes command exited with 1"
    assert failed.blocker_category is None
    assert failed.blocker_retryable is False
    assert projection.list_task_events(failed.task_id)[-1].event_type == "task.failed"

    assert blocked.status == TaskStatus.BLOCKED
    assert blocked.blocker_category == "configuration"
    assert blocked.blocker_retryable is True
    assert blocked.execution_state == TaskExecutionState.ACTIVE
    assert blocked.terminal_reason is None
    assert projection.list_task_events(blocked.task_id)[-1].event_type == "task.blocked"


@pytest.mark.anyio
async def test_quiet_but_alive_attention_state_is_nonterminal_and_persists_separately(tmp_path):
    db_path = tmp_path / "tasks.db"
    projection = TaskProjection(store=SQLiteTaskStore(db_path))
    task = projection.create_task(TaskCreateRequest(prompt="Wait quietly for Hermes"))

    quiet = projection.update_task(
        task.task_id,
        status=TaskStatus.ATTENTION_REQUIRED,
        execution_state=TaskExecutionState.STALLED,
        execution_phase="awaiting_hermes",
        execution_detail="Hermes child process is alive but has not emitted output",
        event_type="task.stalled",
        event_metadata={"child_process": "alive", "execution_state": "quiet"},
    )
    reloaded = TaskProjection(store=SQLiteTaskStore(db_path))
    persisted = reloaded.get_task(task.task_id)

    assert quiet.status == TaskStatus.ATTENTION_REQUIRED
    assert quiet.execution_state == TaskExecutionState.STALLED
    assert quiet.terminal_reason is None
    assert persisted is not None
    assert persisted.status == TaskStatus.ATTENTION_REQUIRED
    assert persisted.execution_state == TaskExecutionState.STALLED
    event = reloaded.list_task_events(task.task_id)[-1]
    assert event.event_type == "task.stalled"
    assert event.status == TaskStatus.ATTENTION_REQUIRED
    assert event.metadata == {"child_process": "alive", "execution_state": "quiet"}
