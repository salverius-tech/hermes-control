from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from .models import TaskCreateRequest, TaskStatus, TaskSummary
from .projection import TaskProjection


@dataclass(frozen=True)
class HermesExecutionResult:
    result_summary: str
    log_messages: list[str] = field(default_factory=list)


TaskLogCallback = Callable[[str], Awaitable[None]]


class HermesExecutor(Protocol):
    async def run(self, request: TaskCreateRequest, *, on_log: TaskLogCallback | None = None) -> HermesExecutionResult: ...


class TaskNotifier(Protocol):
    async def notify_task(self, task: TaskSummary, *, event_type: str) -> None: ...


@dataclass(frozen=True)
class NullTaskNotifier:
    async def notify_task(self, task: TaskSummary, *, event_type: str) -> None:
        return None


@dataclass
class FakeHermesExecutor:
    result_summary: str = "Hermes task completed"
    log_messages: list[str] = field(default_factory=list)
    error: str | None = None

    async def run(self, request: TaskCreateRequest, *, on_log: TaskLogCallback | None = None) -> HermesExecutionResult:
        if self.error is not None:
            raise RuntimeError(self.error)
        return HermesExecutionResult(result_summary=self.result_summary, log_messages=self.log_messages)


@dataclass
class LocalHermesCommandExecutor:
    """Runs a configured local Hermes command and captures its output.

    Set CONTROL_API_HERMES_COMMAND to an argv-like command, for example:
    `hermes chat -q`.
    The mobile prompt is sent to stdin so prompts with shell metacharacters are
    never interpolated into a command string.
    """

    command: tuple[str, ...]
    timeout_seconds: float = 900

    async def run(self, request: TaskCreateRequest, *, on_log: TaskLogCallback | None = None) -> HermesExecutionResult:
        process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        async def read_stream(stream: asyncio.StreamReader | None, sink: list[str]) -> None:
            if stream is None:
                return
            while True:
                line = await stream.readline()
                if not line:
                    return
                message = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not message:
                    continue
                sink.append(message)
                if on_log is not None:
                    await on_log(message)

        async def run_process() -> None:
            assert process.stdin is not None
            process.stdin.write(request.prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
            readers = [
                asyncio.create_task(read_stream(process.stdout, stdout_lines)),
                asyncio.create_task(read_stream(process.stderr, stderr_lines)),
            ]
            await process.wait()
            await asyncio.gather(*readers)

        try:
            await asyncio.wait_for(run_process(), timeout=self.timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError("Hermes command timed out") from exc
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

        stdout_text = "\n".join(stdout_lines).strip()
        stderr_text = "\n".join(stderr_lines).strip()
        if process.returncode != 0:
            detail = stderr_text or stdout_text or f"Hermes command exited with {process.returncode}"
            raise RuntimeError(detail)

        logs = [] if on_log is not None else stderr_lines
        return HermesExecutionResult(result_summary=stdout_text or "Hermes command completed", log_messages=logs)


def executor_from_environment() -> HermesExecutor:
    command = os.getenv("CONTROL_API_HERMES_COMMAND")
    if command:
        return LocalHermesCommandExecutor(tuple(shlex.split(command, posix=os.name != "nt")))
    return FakeHermesExecutor(
        result_summary="Hermes execution is not configured. Set CONTROL_API_HERMES_COMMAND to run real tasks.",
        log_messages=["Task accepted by the local control API", "Hermes execution adapter is not configured"],
    )


TaskUpdateCallback = Callable[[TaskSummary], Awaitable[None]]


@dataclass
class HermesTaskService:
    """Application service that creates tasks and executes them through Hermes."""

    projection: TaskProjection
    executor: HermesExecutor = field(default_factory=executor_from_environment)
    notifier: TaskNotifier = field(default_factory=NullTaskNotifier)
    _running_tasks: dict[str, asyncio.Task[TaskSummary]] = field(default_factory=dict, init=False)

    async def submit_task(
        self,
        request: TaskCreateRequest,
        *,
        run_inline: bool = False,
        on_update: TaskUpdateCallback | None = None,
    ) -> TaskSummary:
        task = self.projection.create_task(request)
        if TaskStatus(task.status) == TaskStatus.AWAITING_APPROVAL:
            await self.notify_task(task, event_type="task.approval_requested")
        if run_inline:
            return await self._execute(task.task_id, request, on_update=on_update)
        return task

    def start_task(
        self,
        task: TaskSummary,
        request: TaskCreateRequest,
        *,
        on_update: TaskUpdateCallback | None = None,
    ) -> None:
        run_task = asyncio.create_task(self._execute(task.task_id, request, on_update=on_update))
        self._running_tasks[task.task_id] = run_task
        run_task.add_done_callback(lambda completed: self._running_tasks.pop(task.task_id, None))

    async def cancel_task(
        self,
        task_id: str,
        *,
        on_update: TaskUpdateCallback | None = None,
    ) -> TaskSummary:
        canceled = self.projection.cancel_task(task_id)
        running_task = self._running_tasks.pop(task_id, None)
        if running_task is not None and not running_task.done():
            running_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await running_task
        await self.notify_task(canceled, event_type="task.canceled")
        if on_update is not None:
            await on_update(canceled)
        return canceled

    async def _execute(
        self,
        task_id: str,
        request: TaskCreateRequest,
        *,
        on_update: TaskUpdateCallback | None = None,
    ) -> TaskSummary:
        current = self.projection.get_task(task_id)
        if current is not None and TaskStatus(current.status) == TaskStatus.CANCELED:
            return current
        running = self.projection.update_task(
            task_id,
            status=TaskStatus.RUNNING,
            progress_message="Hermes task started",
            event_type="task.started",
        )
        if on_update is not None:
            await on_update(running)

        latest = running

        async def record_progress(message: str) -> None:
            nonlocal latest
            current = self.projection.get_task(task_id)
            if current is not None and TaskStatus(current.status) == TaskStatus.CANCELED:
                raise asyncio.CancelledError
            latest = self.projection.update_task(task_id, progress_message=message, event_type="task.progress")
            if on_update is not None:
                await on_update(latest)

        try:
            result = await self.executor.run(request, on_log=record_progress)
        except asyncio.CancelledError:
            canceled = self.projection.get_task(task_id)
            if canceled is None or TaskStatus(canceled.status) != TaskStatus.CANCELED:
                canceled = self.projection.cancel_task(task_id)
            if on_update is not None:
                await on_update(canceled)
            return canceled
        except Exception as exc:  # noqa: BLE001 - boundary converts adapter failures to task state
            failed = self.projection.update_task(task_id, status=TaskStatus.FAILED, error=str(exc), event_type="task.failed")
            await self.notify_task(failed, event_type="task.failed")
            if on_update is not None:
                await on_update(failed)
            return failed

        latest = running
        for message in result.log_messages:
            current = self.projection.get_task(task_id)
            if current is not None and TaskStatus(current.status) == TaskStatus.CANCELED:
                return current
            latest = self.projection.update_task(task_id, progress_message=message, event_type="task.progress")
            if on_update is not None:
                await on_update(latest)

        current = self.projection.get_task(task_id)
        if current is not None and TaskStatus(current.status) == TaskStatus.CANCELED:
            return current

        completed = self.projection.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            result_summary=result.result_summary,
            event_type="task.completed",
        )
        await self.notify_task(completed, event_type="task.completed")
        if on_update is not None:
            await on_update(completed)
        return completed

    async def notify_task(self, task: TaskSummary, *, event_type: str) -> None:
        try:
            await self.notifier.notify_task(task, event_type=event_type)
        except Exception:
            return None
