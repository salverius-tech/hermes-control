from __future__ import annotations

import asyncio
import os
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .protocol import PluginEvent, PluginRequest
from .server import PluginEventSink


NativeTaskRunner = Callable[[PluginRequest, PluginEventSink], Awaitable[str]]


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
    timeout_seconds: float = 900

    async def run(self, request: PluginRequest, *, emit: PluginEventSink) -> str:
        query_mode = any(argument in {"-q", "--query"} for argument in self.command)
        base_command = self.command
        if request.session_id and len(base_command) >= 2 and base_command[0] == "hermes" and base_command[1] == "chat":
            base_command = ("hermes", "chat", "--resume", request.session_id, *base_command[2:])
        command = (*base_command, request.prompt) if query_mode else base_command
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

        async def read_stream(stream: asyncio.StreamReader, *, is_stdout: bool = False) -> list[str]:
            lines: list[str] = []
            suppress_shutdown_noise = False
            async for raw_line in stream:
                line = raw_line.decode(errors="replace").strip()
                if line:
                    lines.append(line)
                    if line == "Exception ignored on threading shutdown:":
                        suppress_shutdown_noise = True
                    if not suppress_shutdown_noise:
                        await emit(PluginEvent(event_type="progress", request_id=request.request_id, message=line))
                    if is_stdout and line.startswith("Session:"):
                        completion_event.set()
            return lines

        stdout_task = asyncio.create_task(read_stream(process.stdout, is_stdout=True))
        stderr_task = asyncio.create_task(read_stream(process.stderr))
        process_wait_task = asyncio.create_task(process.wait())
        completion_wait_task = asyncio.create_task(completion_event.wait())
        completed_from_footer = False
        try:
            done, _pending = await asyncio.wait(
                (process_wait_task, completion_wait_task),
                timeout=self.timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                raise TimeoutError
            if completion_wait_task in done and process.returncode is None:
                completed_from_footer = True
                process.terminate()
                try:
                    await asyncio.wait_for(process_wait_task, timeout=5)
                except TimeoutError:
                    process.kill()
                    await process_wait_task
            stdout_lines, stderr_lines = await asyncio.gather(stdout_task, stderr_task)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            for task in (stdout_task, stderr_task):
                task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            for task in (process_wait_task, completion_wait_task):
                task.cancel()
            await asyncio.gather(process_wait_task, completion_wait_task, return_exceptions=True)
            raise
        finally:
            for task in (process_wait_task, completion_wait_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(process_wait_task, completion_wait_task, return_exceptions=True)

        if process.returncode != 0 and not completed_from_footer:
            detail = "\n".join(stderr_lines or stdout_lines) or f"Hermes command exited with {process.returncode}"
            raise RuntimeError(detail)
        return "\n".join(stdout_lines) or "Hermes command completed"


def handler_from_environment() -> SubprocessHermesTaskHandler:
    command = os.getenv(
        "HERMES_CONTROL_EXTENSION_HERMES_COMMAND",
        "hermes chat --ignore-user-config --ignore-rules -q",
    )
    return SubprocessHermesTaskHandler(tuple(shlex.split(command, posix=os.name != "nt")))
