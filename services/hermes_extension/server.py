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
class _BridgeJob:
    request: PluginRequest
    records: list[bytes] = field(default_factory=list)
    task: asyncio.Task[None] | None = None
    done: bool = False
    changed: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class HermesExtensionServer:
    """Supervised local IPC bridge.

    A submitted job is owned by this server, not by the client socket that
    submitted it. Clients may reconnect with the same request_id to replay
    progress and wait for the terminal event. Server shutdown explicitly
    cancels and awaits every job so a subprocess cannot become orphaned.
    """

    socket_path: str
    handler: HermesTaskHandler
    file_mode: int = 0o660
    auth_token: str | None = None
    max_message_bytes: int = 1_048_576
    max_concurrent_tasks: int = 4
    heartbeat_seconds: float = 15
    replay_cache_size: int = 128
    _server: asyncio.AbstractServer | None = None
    _shutdown_event: asyncio.Event | None = field(default=None, init=False)
    _client_tasks: set[asyncio.Task[None]] = field(default_factory=set, init=False)
    _task_slots: asyncio.Semaphore | None = field(default=None, init=False)
    _replay_cache: OrderedDict[str, tuple[bytes, ...]] = field(default_factory=OrderedDict, init=False)
    _jobs: dict[str, _BridgeJob] = field(default_factory=dict, init=False)
    _closing: bool = field(default=False, init=False)

    async def start(self) -> None:
        if self._server is not None:
            return
        if self.max_message_bytes < 1 or self.max_concurrent_tasks < 1 or self.heartbeat_seconds < 0 or self.replay_cache_size < 1:
            raise ValueError("bridge limits must be positive")
        # A dedicated service is the single owner of this path. Refuse to steal
        # an active listener; only remove an unreachable stale pathname.
        if os.path.exists(self.socket_path):
            try:
                reader, writer = await asyncio.open_unix_connection(self.socket_path)
            except (ConnectionRefusedError, FileNotFoundError):
                os.unlink(self.socket_path)
            else:
                writer.close()
                await writer.wait_closed()
                raise RuntimeError(f"Hermes extension bridge is already listening at {self.socket_path}")
        self._task_slots = asyncio.Semaphore(self.max_concurrent_tasks)
        self._shutdown_event = asyncio.Event()
        self._closing = False
        self._server = await asyncio.start_unix_server(self._handle_client, path=self.socket_path)
        os.chmod(self.socket_path, self.file_mode)

    async def serve_forever(self) -> None:
        if self._server is None or self._shutdown_event is None:
            raise RuntimeError("extension bridge is not started")
        await self._shutdown_event.wait()

    async def close(self) -> None:
        self._closing = True
        if self._shutdown_event is not None:
            self._shutdown_event.set()
        jobs = tuple(job.task for job in self._jobs.values() if job.task is not None and not job.task.done())
        for task in jobs:
            task.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        clients = tuple(self._client_tasks)
        for task in clients:
            task.cancel()
        if clients:
            await asyncio.gather(*clients, return_exceptions=True)
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
        try:
            line = await reader.readline()
            if len(line) > self.max_message_bytes:
                raise ValueError("bridge message exceeds configured size limit")
            message = decode_message(line)
            if message.get("type") != "task.submit":
                raise ValueError("expected task.submit message")
            request = PluginRequest.from_message(message)
            if self.auth_token is not None and not hmac.compare_digest(request.auth_token or "", self.auth_token):
                raise PermissionError("invalid Hermes extension token")
            replay = self._replay_cache.get(request.request_id)
            if replay is not None:
                for record in replay:
                    writer.write(record)
                await writer.drain()
                return
            job = self._jobs.get(request.request_id)
            if job is None:
                if self._closing:
                    raise RuntimeError("Hermes extension bridge is shutting down")
                job = _BridgeJob(request=request)
                self._jobs[request.request_id] = job
                job.task = asyncio.create_task(self._run_job(job), name=f"hermes-control:{request.request_id}")
            await self._stream_job(job, writer)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # protocol failures have a structured terminal event
            request_id = locals().get("request", None)
            event = PluginEvent(event_type="failed", request_id=request_id.request_id if request_id else "unknown", error=str(exc))
            with contextlib.suppress(ConnectionError, BrokenPipeError):
                writer.write(encode_message(event.to_message()))
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()
            if current_task is not None:
                self._client_tasks.discard(current_task)

    async def _stream_job(self, job: _BridgeJob, writer: asyncio.StreamWriter) -> None:
        offset = 0
        while True:
            records = job.records[offset:]
            for record in records:
                writer.write(record)
            if records:
                await writer.drain()
                offset += len(records)
            if job.done:
                return
            job.changed.clear()
            # Prevent a lost wakeup between inspecting records and waiting.
            if len(job.records) != offset or job.done:
                continue
            await job.changed.wait()

    async def _run_job(self, job: _BridgeJob) -> None:
        assert self._task_slots is not None
        sequence = 0

        async def emit(event: PluginEvent) -> None:
            nonlocal sequence
            if event.request_id != job.request.request_id:
                raise ValueError("plugin event request_id does not match task request")
            sequence += 1
            if event.sequence is None:
                event = replace(event, sequence=sequence)
            elif event.sequence != sequence:
                raise ValueError("plugin event sequence is not monotonic")
            job.records.append(encode_message(event.to_message()))
            job.changed.set()

        heartbeat: asyncio.Task[None] | None = None
        try:
            async with self._task_slots:
                if self.heartbeat_seconds > 0:
                    heartbeat = asyncio.create_task(self._heartbeat_loop(job.request.request_id, emit))
                result = await self.handler.run(job.request, emit=emit)
            await emit(PluginEvent(event_type="completed", request_id=job.request.request_id, result_summary=result))
        except asyncio.CancelledError:
            # Deliberate server shutdown: do not report completion for work that
            # was terminated; a reconnecting API will retry the stable request id.
            raise
        except Exception as exc:  # noqa: BLE001
            detail = str(exc).strip() or f"{type(exc).__name__} raised without a diagnostic message"
            await emit(PluginEvent(event_type="failed", request_id=job.request.request_id, error=detail))
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            job.done = True
            job.changed.set()
            if job.records:
                self._store_replay(job.request.request_id, job.records)
            self._jobs.pop(job.request.request_id, None)

    async def _heartbeat_loop(self, request_id: str, emit: PluginEventSink) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            await emit(PluginEvent(
                event_type="heartbeat",
                request_id=request_id,
                metadata={"bridge": "alive"},
            ))

    def _store_replay(self, request_id: str, records: list[bytes]) -> None:
        self._replay_cache[request_id] = tuple(records)
        self._replay_cache.move_to_end(request_id)
        while len(self._replay_cache) > self.replay_cache_size:
            self._replay_cache.popitem(last=False)
