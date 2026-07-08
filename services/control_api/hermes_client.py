from __future__ import annotations

import asyncio
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


class HermesExecutor(Protocol):
    async def run(self, request: TaskCreateRequest) -> HermesExecutionResult: ...


@dataclass
class FakeHermesExecutor:
    result_summary: str = "Hermes task completed"
    log_messages: list[str] = field(default_factory=list)
    error: str | None = None

    async def run(self, request: TaskCreateRequest) -> HermesExecutionResult:
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

    async def run(self, request: TaskCreateRequest) -> HermesExecutionResult:
        process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(request.prompt.encode("utf-8")),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError("Hermes command timed out") from exc

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            detail = stderr_text or stdout_text or f"Hermes command exited with {process.returncode}"
            raise RuntimeError(detail)

        logs = [line for line in stderr_text.splitlines() if line]
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

    async def submit_task(
        self,
        request: TaskCreateRequest,
        *,
        run_inline: bool = False,
        on_update: TaskUpdateCallback | None = None,
    ) -> TaskSummary:
        task = self.projection.create_task(request)
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
        asyncio.create_task(self._execute(task.task_id, request, on_update=on_update))

    async def _execute(
        self,
        task_id: str,
        request: TaskCreateRequest,
        *,
        on_update: TaskUpdateCallback | None = None,
    ) -> TaskSummary:
        running = self.projection.update_task(
            task_id,
            status=TaskStatus.RUNNING,
            progress_message="Hermes task started",
            event_type="task.started",
        )
        if on_update is not None:
            await on_update(running)

        try:
            result = await self.executor.run(request)
        except Exception as exc:  # noqa: BLE001 - boundary converts adapter failures to task state
            failed = self.projection.update_task(task_id, status=TaskStatus.FAILED, error=str(exc), event_type="task.failed")
            if on_update is not None:
                await on_update(failed)
            return failed

        latest = running
        for message in result.log_messages:
            latest = self.projection.update_task(task_id, progress_message=message, event_type="task.progress")
            if on_update is not None:
                await on_update(latest)

        completed = self.projection.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            result_summary=result.result_summary,
            event_type="task.completed",
        )
        if on_update is not None:
            await on_update(completed)
        return completed
