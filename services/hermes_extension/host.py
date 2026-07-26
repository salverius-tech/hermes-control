from __future__ import annotations

import asyncio
import os
import shlex
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .protocol import PluginEvent, PluginRequest
from .server import PluginEventSink


NativeTaskRunner = Callable[[PluginRequest, PluginEventSink], Awaitable[str]]


def build_command(command: tuple[str, ...], request: PluginRequest) -> tuple[tuple[str, ...], bool]:
    query_mode = any(argument in {"-q", "--query"} for argument in command)
    base_command = command
    if request.session_id and len(base_command) >= 2 and base_command[0] == "hermes" and base_command[1] == "chat":
        base_command = ("hermes", "chat", "--resume", request.session_id, *base_command[2:])
    model_args: tuple[str, ...] = ()
    if request.provider:
        model_args += ("--provider", request.provider)
    if request.model:
        model_args += ("--model", request.model)
    if query_mode:
        query_command: list[str] = []
        query_inserted = False
        for argument in base_command:
            query_command.append(argument)
            if argument in {"-q", "--query"}:
                query_command.append(request.prompt)
                query_inserted = True
        if not query_inserted:
            query_command.append(request.prompt)
        return (*query_command, *model_args), True
    return (*base_command, *model_args), False


@dataclass
class NativeHermesTaskHandler:
    """Adapter for a future Hermes-native task runner callback.

    Hermes currently does not expose a stable host-task lifecycle callback. A
    supported callback can be injected here without changing the bridge.
    """

    run_task: NativeTaskRunner

    async def run(self, request: PluginRequest, *, emit: PluginEventSink) -> str:
        return await self.run_task(request, emit)


@dataclass
class SubprocessHermesTaskHandler:
    """Run the configured Hermes CLI while preserving the structured bridge."""

    command: tuple[str, ...]
    # An operator may configure a hard safety cap, but it must not be the
    # normal completion mechanism for long-running agent work.
    timeout_seconds: float | None = None
    heartbeat_seconds: float = 15

    async def run(self, request: PluginRequest, *, emit: PluginEventSink) -> str:
        command, query_mode = build_command(self.command, request)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if not query_mode else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=request.execution_folder,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        if not query_mode:
            assert process.stdin is not None
            process.stdin.write(request.prompt.encode())
            await process.stdin.drain()
            process.stdin.close()

        completion_event = asyncio.Event()
        cleanup_candidate: list[str] = []
        shutdown_noise = False
        started_at = time.monotonic()

        async def read_stream(stream: asyncio.StreamReader, *, is_stdout: bool = False) -> list[str]:
            nonlocal shutdown_noise
            lines: list[str] = []
            suppress_shutdown_noise = False
            async for raw_line in stream:
                line = raw_line.decode(errors="replace").strip()
                if line:
                    if completion_event.is_set():
                        continue
                    if not is_stdout and (cleanup_candidate or line == "Traceback (most recent call last):"):
                        cleanup_candidate.append(line)
                        continue
                    lines.append(line)
                    if line.startswith("Session:"):
                        completion_event.set()
                    if line == "Exception ignored on threading shutdown:":
                        suppress_shutdown_noise = True
                        shutdown_noise = True
                    if not suppress_shutdown_noise:
                        await emit(PluginEvent(event_type="progress", request_id=request.request_id, message=line))
            return lines

        stdout_task = asyncio.create_task(read_stream(process.stdout, is_stdout=True))
        stderr_task = asyncio.create_task(read_stream(process.stderr))
        process_wait_task = asyncio.create_task(process.wait())
        completion_wait_task = asyncio.create_task(completion_event.wait())

        async def emit_process_heartbeats() -> None:
            while process.returncode is None:
                await asyncio.sleep(self.heartbeat_seconds)
                if process.returncode is None:
                    await emit(PluginEvent(
                        event_type="heartbeat",
                        request_id=request.request_id,
                        metadata={
                            "bridge": "alive",
                            "child_process": "alive",
                            "execution_state": "quiet",
                            "execution_phase": "awaiting_hermes",
                            "elapsed_seconds": round(time.monotonic() - started_at, 3),
                        },
                    ))

        heartbeat_task = asyncio.create_task(emit_process_heartbeats())
        completed_from_footer = False
        try:
            done, _pending = await asyncio.wait(
                (process_wait_task, completion_wait_task),
                timeout=self.timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                assert self.timeout_seconds is not None
                raise RuntimeError(
                    f"Hermes task exceeded the configured hard execution limit "
                    f"({self.timeout_seconds:g} seconds)"
                )
            if completion_wait_task in done and process.returncode is None:
                completed_from_footer = True
                process.terminate()
                try:
                    await asyncio.wait_for(process_wait_task, timeout=5)
                except TimeoutError:
                    process.kill()
                    await process_wait_task
            stdout_lines, stderr_lines = await asyncio.gather(stdout_task, stderr_task)
            if not completed_from_footer:
                stderr_lines.extend(cleanup_candidate)
                if not shutdown_noise:
                    for line in cleanup_candidate:
                        await emit(PluginEvent(event_type="progress", request_id=request.request_id, message=line))
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            for task in (stdout_task, stderr_task):
                task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            for task in (process_wait_task, completion_wait_task, heartbeat_task):
                task.cancel()
            await asyncio.gather(process_wait_task, completion_wait_task, heartbeat_task, return_exceptions=True)
            raise
        finally:
            for task in (process_wait_task, completion_wait_task, heartbeat_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(process_wait_task, completion_wait_task, heartbeat_task, return_exceptions=True)

        if process.returncode != 0 and not completed_from_footer:
            detail = "\n".join(stderr_lines or stdout_lines) or f"Hermes command exited with {process.returncode}"
            raise RuntimeError(detail)
        return "\n".join(stdout_lines) or "Hermes command completed"


def handler_from_environment() -> SubprocessHermesTaskHandler:
    command = os.getenv(
        "HERMES_CONTROL_EXTENSION_HERMES_COMMAND",
        "hermes chat --ignore-user-config --ignore-rules -q",
    )
    hard_timeout = os.getenv("HERMES_CONTROL_EXTENSION_HARD_TIMEOUT_SECONDS")
    timeout_seconds = float(hard_timeout) if hard_timeout else None
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("HERMES_CONTROL_EXTENSION_HARD_TIMEOUT_SECONDS must be positive when configured")
    heartbeat_seconds = float(os.getenv("HERMES_CONTROL_EXTENSION_PROCESS_HEARTBEAT_SECONDS", "15"))
    if heartbeat_seconds <= 0:
        raise ValueError("HERMES_CONTROL_EXTENSION_PROCESS_HEARTBEAT_SECONDS must be positive")
    return SubprocessHermesTaskHandler(
        tuple(shlex.split(command, posix=os.name != "nt")),
        timeout_seconds=timeout_seconds,
        heartbeat_seconds=heartbeat_seconds,
    )
