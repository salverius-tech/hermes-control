import sys

import pytest

from services.control_api.hermes_client import FakeHermesExecutor, HermesTaskService, LocalHermesCommandExecutor
from services.control_api.models import TaskCreateRequest, TaskStatus
from services.control_api.projection import TaskProjection


pytestmark = pytest.mark.unit


@pytest.mark.anyio
async def test_task_service_runs_executor_and_records_successful_result():
    projection = TaskProjection()
    service = HermesTaskService(
        projection=projection,
        executor=FakeHermesExecutor(result_summary="Finished from Hermes", log_messages=["accepted", "working"]),
    )

    task = await service.submit_task(TaskCreateRequest(prompt="Execute for real"), run_inline=True)

    saved = projection.get_task(task.task_id)
    assert saved is not None
    assert saved.status == TaskStatus.COMPLETED
    assert saved.progress_log == ["Hermes task started", "accepted", "working"]
    assert saved.result_summary == "Finished from Hermes"


@pytest.mark.anyio
async def test_task_service_records_executor_failure():
    projection = TaskProjection()
    service = HermesTaskService(
        projection=projection,
        executor=FakeHermesExecutor(error="Hermes command failed"),
    )

    task = await service.submit_task(TaskCreateRequest(prompt="Fail visibly"), run_inline=True)

    saved = projection.get_task(task.task_id)
    assert saved is not None
    assert saved.status == TaskStatus.FAILED
    assert saved.error == "Hermes command failed"
    assert projection.list_task_events(task.task_id)[-1].event_type == "task.failed"


@pytest.mark.anyio
async def test_local_command_executor_sends_prompt_on_stdin_and_captures_stderr_logs():
    executor = LocalHermesCommandExecutor(
        (
            sys.executable,
            "-c",
            "import sys; prompt=sys.stdin.read(); print('result:' + prompt); print('log:accepted', file=sys.stderr)",
        )
    )

    result = await executor.run(TaskCreateRequest(prompt="hello from mobile"))

    assert result.result_summary == "result:hello from mobile"
    assert result.log_messages == ["log:accepted"]


@pytest.mark.anyio
async def test_local_command_executor_raises_stderr_for_nonzero_exit():
    executor = LocalHermesCommandExecutor(
        (sys.executable, "-c", "import sys; print('bad command', file=sys.stderr); raise SystemExit(7)")
    )

    with pytest.raises(RuntimeError, match="bad command"):
        await executor.run(TaskCreateRequest(prompt="fail"))


@pytest.mark.anyio
async def test_local_command_executor_times_out():
    executor = LocalHermesCommandExecutor(
        (sys.executable, "-c", "import time; time.sleep(10)"),
        timeout_seconds=0.05,
    )

    with pytest.raises(RuntimeError, match="timed out"):
        await executor.run(TaskCreateRequest(prompt="timeout"))
