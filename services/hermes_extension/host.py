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
        command = (*self.command, request.prompt) if query_mode else self.command
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if not query_mode else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        if not query_mode:
            assert process.stdin is not None
            process.stdin.write(request.prompt.encode())
            await process.stdin.drain()
            process.stdin.close()

        async def read_stream(stream: asyncio.StreamReader) -> list[str]:
            lines: list[str] = []
            async for raw_line in stream:
                line = raw_line.decode(errors="replace").strip()
                if line:
                    lines.append(line)
                    await emit(PluginEvent(event_type="progress", request_id=request.request_id, message=line))
            return lines

        stdout_task = asyncio.create_task(read_stream(process.stdout))
        stderr_task = asyncio.create_task(read_stream(process.stderr))
        try:
            await asyncio.wait_for(process.wait(), timeout=self.timeout_seconds)
            stdout_lines, stderr_lines = await asyncio.gather(stdout_task, stderr_task)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            for task in (stdout_task, stderr_task):
                task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise

        if process.returncode != 0:
            detail = "\n".join(stderr_lines or stdout_lines) or f"Hermes command exited with {process.returncode}"
            raise RuntimeError(detail)
        return "\n".join(stdout_lines) or "Hermes command completed"


def handler_from_environment() -> SubprocessHermesTaskHandler:
    command = os.getenv(
        "HERMES_CONTROL_EXTENSION_HERMES_COMMAND",
        "hermes chat -q --ignore-user-config --ignore-rules",
    )
    return SubprocessHermesTaskHandler(tuple(shlex.split(command, posix=os.name != "nt")))
