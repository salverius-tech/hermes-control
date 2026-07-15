from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shlex
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from services.hermes_extension import PluginEvent, PluginRequest, decode_message, encode_message

from .models import TaskCreateRequest, TaskStatus, TaskSummary
from .projection import TaskProjection


@dataclass(frozen=True)
class HermesExecutionResult:
    result_summary: str
    log_messages: list[str] = field(default_factory=list)
    session_id: str | None = None


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
        query_mode = any(argument in {"-q", "--query"} for argument in self.command)
        base_command = self.command
        if request.session_id and len(base_command) >= 2 and base_command[0] == "hermes" and base_command[1] == "chat":
            base_command = ("hermes", "chat", "--resume", request.session_id, *base_command[2:])
        command = (*base_command, request.prompt) if query_mode else base_command
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL if query_mode else asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=request.execution_folder,
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
            if not query_mode:
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
        return HermesExecutionResult(result_summary=stdout_text or "Hermes command completed", log_messages=logs, session_id=_session_id_from_output(stdout_text))


@dataclass(frozen=True)
class HermesPluginExecutor:
    """Executes a task through the local Hermes Control Extension bridge.

    The plugin owns Hermes lifecycle and tool integration. The Control API only
    translates the mobile task request into a versioned JSONL bridge request and
    forwards structured progress events to its projection layer.
    """

    socket_path: str
    timeout_seconds: float = 900
    auth_token: str | None = None

    async def run(
        self,
        request: TaskCreateRequest,
        *,
        on_log: TaskLogCallback | None = None,
        request_id: str | None = None,
    ) -> HermesExecutionResult:
        request_id = request_id or str(uuid.uuid4())
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(self.socket_path), timeout=self.timeout_seconds
        )
        bridge_request = PluginRequest(
            request_id=request_id,
            prompt=request.prompt,
            project_id=request.project_id,
            priority=request.priority,
            source=request.source,
            requires_approval=request.requires_approval,
            session_id=request.session_id,
            execution_folder=request.execution_folder,
            auth_token=self.auth_token,
        )
        writer.write(encode_message(bridge_request.to_message()))
        await writer.drain()
        logs: list[str] = []
        last_sequence = 0
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=self.timeout_seconds)
                if not line:
                    raise RuntimeError("Hermes extension bridge disconnected before task completion")
                event = PluginEvent.from_message(decode_message(line))
                if event.request_id != request_id:
                    continue
                if event.sequence is not None:
                    if event.sequence != last_sequence + 1:
                        raise RuntimeError("Hermes extension bridge event sequence is invalid")
                    last_sequence = event.sequence
                if event.message:
                    logs.append(event.message)
                    if on_log is not None:
                        await on_log(event.message)
                if event.event_type == "completed":
                    return HermesExecutionResult(
                        result_summary=event.result_summary or "Hermes plugin task completed",
                        log_messages=[] if on_log is not None else logs,
                        session_id=_session_id_from_output(event.result_summary or ""),
                    )
                if event.event_type == "failed":
                    raise RuntimeError(event.error or event.message or "Hermes plugin task failed")
        finally:
            writer.close()
            await writer.wait_closed()


def _session_id_from_output(output: str) -> str | None:
    match = re.search(r"^Session:\s*(\S+)", output, flags=re.MULTILINE)
    return match.group(1) if match else None


def _classify_failure(message: str) -> tuple[str, bool]:
    lowered = message.lower()
    if "not configured" in lowered:
        return "configuration", True
    if "connection refused" in lowered or "timed out" in lowered or "socket" in lowered:
        return "connectivity", True
    if "does not exist" in lowered or "folder" in lowered or "directory" in lowered:
        return "project_context", True
    if "permission denied" in lowered:
        return "permission", True
    return "execution", False


def executor_from_environment() -> HermesExecutor:
    plugin_socket = os.getenv("CONTROL_API_HERMES_PLUGIN_SOCKET")
    if plugin_socket:
        return HermesPluginExecutor(plugin_socket, auth_token=os.getenv("CONTROL_API_HERMES_PLUGIN_TOKEN"))
    command = os.getenv("CONTROL_API_HERMES_COMMAND")
    if command:
        return LocalHermesCommandExecutor(tuple(shlex.split(command, posix=os.name != "nt")))
    return FakeHermesExecutor(error="Hermes execution is not configured. Set CONTROL_API_HERMES_COMMAND or CONTROL_API_HERMES_PLUGIN_SOCKET to run real tasks.")


TaskUpdateCallback = Callable[[TaskSummary], Awaitable[None]]


@dataclass
class HermesTaskService:
    """Application service that creates tasks and executes them through Hermes."""

    projection: TaskProjection
    executor: HermesExecutor = field(default_factory=executor_from_environment)
    notifier: TaskNotifier = field(default_factory=NullTaskNotifier)
    max_concurrent_tasks: int = 4
    _running_tasks: dict[str, asyncio.Task[TaskSummary]] = field(default_factory=dict, init=False)
    _execution_slots: asyncio.Semaphore = field(init=False)

    @property
    def active_task_count(self) -> int:
        return len(self._running_tasks)

    def __post_init__(self) -> None:
        if self.max_concurrent_tasks < 1:
            raise ValueError("max_concurrent_tasks must be positive")
        self._execution_slots = asyncio.Semaphore(self.max_concurrent_tasks)

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
            return await self._execute_with_slot(task.task_id, request, on_update=on_update)
        return task

    def reconcile_after_restart(self) -> list[TaskSummary]:
        interrupted: list[TaskSummary] = []
        for task in self.projection.list_tasks():
            if TaskStatus(task.status) not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                continue
            interrupted.append(self.projection.update_task(
                task.task_id,
                status=TaskStatus.BLOCKED,
                error="Task was interrupted when the Control API restarted",
                blocker_category="recovery",
                blocker_message="Task was interrupted when the Control API restarted",
                blocker_retryable=True,
                event_type="task.interrupted",
            ))
        return interrupted

    def start_task(
        self,
        task: TaskSummary,
        request: TaskCreateRequest,
        *,
        on_update: TaskUpdateCallback | None = None,
    ) -> None:
        run_task = asyncio.create_task(self._execute_with_slot(task.task_id, request, on_update=on_update))
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
            category, blocked = _classify_failure(str(exc))
            failed = self.projection.update_task(
                task_id,
                status=TaskStatus.BLOCKED if blocked else TaskStatus.FAILED,
                error=str(exc),
                blocker_category=category if blocked else None,
                blocker_message=str(exc) if blocked else None,
                blocker_retryable=blocked,
                event_type="task.blocked" if blocked else "task.failed",
            )
            await self.notify_task(failed, event_type="task.blocked" if blocked else "task.failed")
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
            session_id=result.session_id,
            event_type="task.completed",
        )
        await self.notify_task(completed, event_type="task.completed")
        if on_update is not None:
            await on_update(completed)
        return completed

    async def _execute_with_slot(
        self,
        task_id: str,
        request: TaskCreateRequest,
        *,
        on_update: TaskUpdateCallback | None = None,
    ) -> TaskSummary:
        async with self._execution_slots:
            return await self._execute(task_id, request, on_update=on_update)

    async def notify_task(self, task: TaskSummary, *, event_type: str) -> None:
        try:
            await self.notifier.notify_task(task, event_type=event_type)
        except Exception:
            return None
