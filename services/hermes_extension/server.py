from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
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
    max_message_bytes: int = 1_048_576
    max_concurrent_tasks: int = 4
    heartbeat_seconds: float = 0
    replay_cache_size: int = 128
    _server: asyncio.AbstractServer | None = None
    _shutdown_event: asyncio.Event | None = field(default=None, init=False)
    _client_tasks: set[asyncio.Task[None]] = field(default_factory=set, init=False)
    _task_slots: asyncio.Semaphore | None = field(default=None, init=False)
    _replay_cache: OrderedDict[str, tuple[bytes, ...]] = field(default_factory=OrderedDict, init=False)
    _active_request_ids: set[str] = field(default_factory=set, init=False)

    async def start(self) -> None:
        if self._server is not None:
            return
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.socket_path)
        if self.max_message_bytes < 1 or self.max_concurrent_tasks < 1 or self.heartbeat_seconds < 0 or self.replay_cache_size < 1:
            raise ValueError("bridge limits must be positive")
        self._task_slots = asyncio.Semaphore(self.max_concurrent_tasks)
        self._shutdown_event = asyncio.Event()
        self._server = await asyncio.start_unix_server(self._handle_client, path=self.socket_path)
        os.chmod(self.socket_path, self.file_mode)

    async def serve_forever(self) -> None:
        if self._server is None or self._shutdown_event is None:
            raise RuntimeError("extension bridge is not started")
        await self._shutdown_event.wait()

    async def close(self) -> None:
        if self._shutdown_event is not None:
            self._shutdown_event.set()
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
        claimed_request_id: str | None = None
        emitted_records: list[bytes] = []
        try:
            line = await reader.readline()
            if len(line) > self.max_message_bytes:
                raise ValueError("bridge message exceeds configured size limit")
            message = decode_message(line)
            if message.get("type") != "task.submit":
                raise ValueError("expected task.submit message")
            request = PluginRequest.from_message(message)
            request_id = request.request_id
            event_sequence = 0
            if self.auth_token is not None and not hmac.compare_digest(request.auth_token or "", self.auth_token):
                raise PermissionError("invalid Hermes extension token")
            replay = self._replay_cache.get(request_id)
            if replay is not None:
                for record in replay:
                    writer.write(record)
                await writer.drain()
                return
            if request_id in self._active_request_ids:
                raise ValueError("duplicate task request is already running")
            self._active_request_ids.add(request_id)
            claimed_request_id = request_id

            async def emit(event: PluginEvent) -> None:
                nonlocal event_sequence
                if event.request_id != request.request_id:
                    raise ValueError("plugin event request_id does not match task request")
                event_sequence += 1
                if event.sequence is None:
                    event = replace(event, sequence=event_sequence)
                elif event.sequence != event_sequence:
                    raise ValueError("plugin event sequence is not monotonic")
                record = encode_message(event.to_message())
                emitted_records.append(record)
                writer.write(record)
                await writer.drain()

            if self._task_slots is None:
                raise RuntimeError("extension bridge is not started")
            handler_task = asyncio.create_task(self._run_handler(request, emit))
            disconnect_task = asyncio.create_task(reader.read(1))
            heartbeat_task = (
                asyncio.create_task(self._heartbeat_loop(request.request_id, emit))
                if self.heartbeat_seconds > 0
                else None
            )
            try:
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
                self._store_replay(request_id, emitted_records)
            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    await asyncio.gather(heartbeat_task, return_exceptions=True)
        except Exception as exc:  # noqa: BLE001 - protocol boundary reports handler failures
            with contextlib.suppress(ConnectionError, BrokenPipeError):
                failure_record = encode_message(
                    PluginEvent(
                        event_type="failed",
                        request_id=request_id,
                        error=str(exc),
                    ).to_message()
                )
                writer.write(failure_record)
                await writer.drain()
                if claimed_request_id is not None:
                    self._store_replay(request_id, [*emitted_records, failure_record])
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
            if current_task is not None:
                self._client_tasks.discard(current_task)
            if claimed_request_id is not None:
                self._active_request_ids.discard(claimed_request_id)

    async def _heartbeat_loop(self, request_id: str, emit: PluginEventSink) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            await emit(PluginEvent(event_type="heartbeat", request_id=request_id))

    def _store_replay(self, request_id: str, records: list[bytes]) -> None:
        self._replay_cache[request_id] = tuple(records)
        self._replay_cache.move_to_end(request_id)
        while len(self._replay_cache) > self.replay_cache_size:
            self._replay_cache.popitem(last=False)

    async def _run_handler(self, request: PluginRequest, emit: PluginEventSink) -> str:
        assert self._task_slots is not None
        async with self._task_slots:
            return await self.handler.run(request, emit=emit)
