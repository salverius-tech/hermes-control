from __future__ import annotations

import asyncio
import os
import shlex
from dataclasses import dataclass

from .protocol import PluginEvent, PluginRequest
from .server import PluginEventSink


@dataclass(frozen=True)
class SubprocessHermesTaskHandler:
    """Execute extension tasks through a local Hermes-compatible command.

    This is the first concrete host implementation. Once Hermes exposes stable
    in-process lifecycle hooks for the installed runtime, this handler can be
    replaced without changing the bridge or Control API contract.
    """

    command: tuple[str, ...]
    timeout_seconds: float = 900

    async def run(self, request: PluginRequest, *, emit: PluginEventSink) -> str:
        process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdin is not None
        process.stdin.write(request.prompt.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        async def forward(stream: asyncio.StreamReader | None) -> list[str]:
            lines: list[str] = []
            if stream is None:
                return lines
            while line := await stream.readline():
                message = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if message:
                    lines.append(message)
                    await emit(
                        PluginEvent(
                            event_type="progress",
                            request_id=request.request_id,
                            message=message,
                        )
                    )
            return lines

        try:
            stdout_task = asyncio.create_task(forward(process.stdout))
            stderr_task = asyncio.create_task(forward(process.stderr))
            await asyncio.wait_for(process.wait(), timeout=self.timeout_seconds)
            stdout_lines, stderr_lines = await asyncio.gather(stdout_task, stderr_task)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError("Hermes extension command timed out") from exc
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

        if process.returncode != 0:
            detail = "\n".join(stderr_lines or stdout_lines) or f"Hermes exited with {process.returncode}"
            raise RuntimeError(detail)
        return "\n".join(stdout_lines) or "Hermes command completed"


def handler_from_environment() -> SubprocessHermesTaskHandler:
    command = os.getenv("HERMES_CONTROL_EXTENSION_HERMES_COMMAND", "hermes chat -q")
    return SubprocessHermesTaskHandler(tuple(shlex.split(command, posix=os.name != "nt")))
