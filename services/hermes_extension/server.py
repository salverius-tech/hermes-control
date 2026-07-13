from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from .protocol import PluginEvent, PluginRequest, decode_message, encode_message


PluginEventSink = Callable[[PluginEvent], Awaitable[None]]


class HermesTaskHandler(Protocol):
    async def run(self, request: PluginRequest, *, emit: PluginEventSink) -> str: ...


@dataclass
class HermesExtensionServer:
    """Serve the local Control Extension protocol for a Hermes host adapter."""

    socket_path: str
    handler: HermesTaskHandler
    file_mode: int = 0o660
    auth_token: str | None = None
    _server: asyncio.AbstractServer | None = None
    _client_tasks: set[asyncio.Task[None]] = field(default_factory=set, init=False)

    async def start(self) -> None:
        if self._server is not None:
            return
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.socket_path)
        self._server = await asyncio.start_unix_server(self._handle_client, path=self.socket_path)
        os.chmod(self.socket_path, self.file_mode)

    async def close(self) -> None:
        client_tasks = tuple(self._client_tasks)
        for task in client_tasks:
            task.cancel()
        if client_tasks:
            await asyncio.gather(*client_tasks, return_exceptions=True)
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.socket_path)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        current_task = asyncio.current_task()
        if current_task is not None:
            self._client_tasks.add(current_task)
        request_id = "unknown"
        try:
            line = await reader.readline()
            message = decode_message(line)
            if message.get("type") != "task.submit":
                raise ValueError("expected task.submit message")
            request = PluginRequest.from_message(message)
            request_id = request.request_id
            if self.auth_token is not None and not hmac.compare_digest(request.auth_token or "", self.auth_token):
                raise PermissionError("invalid Hermes extension token")

            async def emit(event: PluginEvent) -> None:
                if event.request_id != request.request_id:
                    raise ValueError("plugin event request_id does not match task request")
                writer.write(encode_message(event.to_message()))
                await writer.drain()

            handler_task = asyncio.create_task(self.handler.run(request, emit=emit))
            disconnect_task = asyncio.create_task(reader.read(1))
            done, _pending = await asyncio.wait(
                (handler_task, disconnect_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if disconnect_task in done:
                if not handler_task.done():
                    handler_task.cancel()
                    await asyncio.gather(handler_task, return_exceptions=True)
                return
            disconnect_task.cancel()
            await asyncio.gather(disconnect_task, return_exceptions=True)
            result = handler_task.result()
            await emit(
                PluginEvent(
                    event_type="completed",
                    request_id=request.request_id,
                    result_summary=result,
                )
            )
        except Exception as exc:  # noqa: BLE001 - protocol boundary reports handler failures
            with contextlib.suppress(ConnectionError, BrokenPipeError):
                writer.write(
                    encode_message(
                        PluginEvent(
                            event_type="failed",
                            request_id=request_id,
                            error=str(exc),
                        ).to_message()
                    )
                )
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
            if current_task is not None:
                self._client_tasks.discard(current_task)
