import pytest

from services.control_api.hermes_client import HermesTaskService
from services.control_api.models import TaskCreateRequest, TaskExecutionState, TaskStatus
from services.control_api.projection import TaskProjection
from services.control_api.storage import SQLiteTaskStore


pytestmark = pytest.mark.unit


class FailingExecutor:
    def __init__(self, message: str) -> None:
        self.message = message

    async def run(self, request: TaskCreateRequest, *, on_log=None):
        raise RuntimeError(self.message)


@pytest.mark.anyio
async def test_missing_bridge_heartbeat_is_a_retryable_block_with_stale_activity_state():
    projection = TaskProjection()
    service = HermesTaskService(
        projection=projection,
        executor=FailingExecutor("No bridge heartbeat or task output was received for 30 seconds; the bridge may be stalled or unavailable"),
    )

    task = await service.submit_task(TaskCreateRequest(prompt="Detect a stale bridge"), run_inline=True)

    assert task.status == TaskStatus.BLOCKED
    assert task.blocker_category == "stale_heartbeat"
    assert task.blocker_retryable is True
    assert task.execution_state == TaskExecutionState.STALE_HEARTBEAT
    assert task.execution_phase == "bridge_unresponsive"
    assert task.terminal_reason == "missing_heartbeat"
    event = projection.list_task_events(task.task_id)[-1]
    assert event.event_type == "task.blocked"
    assert event.metadata == {"reason": "missing_heartbeat"}


@pytest.mark.anyio
async def test_configuration_block_is_not_misreported_as_a_stale_heartbeat():
    projection = TaskProjection()
    service = HermesTaskService(
        projection=projection,
        executor=FailingExecutor("Hermes execution is not configured"),
    )

    task = await service.submit_task(TaskCreateRequest(prompt="Separate blocked causes"), run_inline=True)

    assert task.status == TaskStatus.BLOCKED
    assert task.blocker_category == "configuration"
    assert task.execution_state == TaskExecutionState.ACTIVE
    assert task.terminal_reason is None


def test_restart_interruption_persists_a_distinct_recovery_outcome(tmp_path):
    db_path = tmp_path / "tasks.db"
    first = TaskProjection(store=SQLiteTaskStore(db_path))
    task = first.create_task(TaskCreateRequest(prompt="Survive restart"))
    first.update_task(
        task.task_id,
        status=TaskStatus.RUNNING,
        execution_state=TaskExecutionState.ACTIVE,
        execution_phase="executing",
    )

    interrupted = HermesTaskService(projection=first).reconcile_after_restart()
    reloaded = TaskProjection(store=SQLiteTaskStore(db_path)).get_task(task.task_id)

    assert [item.task_id for item in interrupted] == [task.task_id]
    assert reloaded is not None
    assert reloaded.status == TaskStatus.BLOCKED
    assert reloaded.blocker_category == "recovery"
    assert reloaded.execution_state == TaskExecutionState.INTERRUPTED
    assert reloaded.execution_phase == "interrupted"
    assert reloaded.terminal_reason == "control_api_restart"
    assert first.list_task_events(task.task_id)[-1].event_type == "task.interrupted"
