import asyncio
import sys

import pytest

from services.control_api.hermes_client import (
    FakeHermesExecutor,
    HermesExecutionResult,
    HermesPluginExecutor,
    HermesTaskService,
    LocalHermesCommandExecutor,
)
from services.control_api.models import TaskCreateRequest, TaskStatus
from services.control_api.projection import TaskProjection
from services.hermes_extension import decode_message, encode_message


pytestmark = pytest.mark.unit


class BlockingHermesExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.canceled = asyncio.Event()

    async def run(self, request: TaskCreateRequest, *, on_log=None):
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.canceled.set()
            raise


class StreamingHermesExecutor:
    async def run(self, request: TaskCreateRequest, *, on_log=None) -> HermesExecutionResult:
        assert on_log is not None
        await on_log("streamed stdout")
        await on_log("streamed stderr")
        return HermesExecutionResult(result_summary="stream complete")


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
async def test_task_service_cancels_active_executor_task():
    projection = TaskProjection()
    executor = BlockingHermesExecutor()
    service = HermesTaskService(projection=projection, executor=executor)
    task = await service.submit_task(TaskCreateRequest(prompt="Stop this task"))

    service.start_task(task, TaskCreateRequest(prompt="Stop this task"))
    await asyncio.wait_for(executor.started.wait(), timeout=1)

    canceled = await service.cancel_task(task.task_id)

    assert canceled.status == TaskStatus.CANCELED
    assert executor.canceled.is_set()
    assert projection.list_task_events(task.task_id)[-1].event_type == "task.canceled"


@pytest.mark.anyio
async def test_task_service_records_streamed_executor_progress():
    projection = TaskProjection()
    service = HermesTaskService(projection=projection, executor=StreamingHermesExecutor())

    task = await service.submit_task(TaskCreateRequest(prompt="Stream progress"), run_inline=True)

    saved = projection.get_task(task.task_id)
    assert saved is not None
    assert saved.status == TaskStatus.COMPLETED
    assert saved.progress_log == ["Hermes task started", "streamed stdout", "streamed stderr"]
    assert saved.result_summary == "stream complete"


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


@pytest.mark.anyio
async def test_local_command_executor_streams_output_before_process_exits():
    executor = LocalHermesCommandExecutor(
        (
            sys.executable,
            "-c",
            "import sys, time; print('stdout:first', flush=True); print('stderr:first', file=sys.stderr, flush=True); time.sleep(0.3); print('stdout:done', flush=True)",
        )
    )
    seen_first_line = asyncio.Event()
    progress_messages = []

    async def record_progress(message: str) -> None:
        progress_messages.append(message)
        if message == "stdout:first":
            seen_first_line.set()

    run_task = asyncio.create_task(executor.run(TaskCreateRequest(prompt="stream"), on_log=record_progress))
    await asyncio.wait_for(seen_first_line.wait(), timeout=1)

    assert not run_task.done()
    result = await run_task

    assert "stdout:first" in progress_messages
    assert "stderr:first" in progress_messages
    assert result.result_summary == "stdout:first\nstdout:done"


@pytest.mark.anyio
async def test_plugin_executor_round_trips_structured_task_and_progress(tmp_path):
    socket_path = str(tmp_path / "hermes-extension.sock")
    received = {}

    async def handle(reader, writer):
        received.update(decode_message(await reader.readline()))
        request_id = received["request_id"]
        writer.write(encode_message({
            "version": 1,
            "type": "task.event",
            "event": "progress",
            "request_id": request_id,
            "message": "plugin started",
        }))
        writer.write(encode_message({
            "version": 1,
            "type": "task.event",
            "event": "completed",
            "request_id": request_id,
            "result_summary": "plugin result",
        }))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, path=socket_path)
    try:
        progress = []

        async def on_log(message: str) -> None:
            progress.append(message)

        result = await HermesPluginExecutor(socket_path, timeout_seconds=1).run(
            TaskCreateRequest(prompt="run through plugin", project_id="mobile"),
            on_log=on_log,
        )
    finally:
        server.close()
        await server.wait_closed()

    assert received["type"] == "task.submit"
    assert received["task"]["prompt"] == "run through plugin"
    assert received["task"]["project_id"] == "mobile"
    assert progress == ["plugin started"]
    assert result.result_summary == "plugin result"
