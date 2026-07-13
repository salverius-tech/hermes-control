from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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

    async def start(self) -> None:
        if self._server is not None:
            return
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.socket_path)
        self._server = await asyncio.start_unix_server(self._handle_client, path=self.socket_path)
        os.chmod(self.socket_path, self.file_mode)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.socket_path)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
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

            result = await self.handler.run(request, emit=emit)
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
