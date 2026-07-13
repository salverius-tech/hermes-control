import asyncio
import os

import pytest

from services.control_api.hermes_client import HermesPluginExecutor
from services.control_api.models import TaskCreateRequest
from services.hermes_extension import HermesExtensionServer, PluginEvent
from services.hermes_extension.protocol import PluginRequest, encode_message


pytestmark = pytest.mark.unit


class RecordingHandler:
    def __init__(self):
        self.calls = 0

    async def run(self, request, *, emit):
        self.calls += 1
        await emit(PluginEvent(event_type="progress", request_id=request.request_id, message="accepted"))
        await emit(PluginEvent(event_type="progress", request_id=request.request_id, message="running"))
        return f"completed: {request.prompt}"


@pytest.mark.anyio
async def test_extension_server_accepts_task_and_emits_structured_events(tmp_path):
    socket_path = str(tmp_path / "control-extension.sock")
    server = HermesExtensionServer(socket_path, RecordingHandler())
    await server.start()
    try:
        progress = []

        async def on_log(message: str) -> None:
            progress.append(message)

        result = await HermesPluginExecutor(socket_path, timeout_seconds=1).run(
            TaskCreateRequest(prompt="inspect the runtime"),
            on_log=on_log,
        )
    finally:
        await server.close()

    assert progress == ["accepted", "running"]
    assert result.result_summary == "completed: inspect the runtime"
    assert not os.path.exists(socket_path)


@pytest.mark.anyio
async def test_duplicate_request_id_replays_without_rerunning_handler(tmp_path):
    socket_path = str(tmp_path / "replay-extension.sock")
    handler = RecordingHandler()
    server = HermesExtensionServer(socket_path, handler)
    await server.start()
    try:
        executor = HermesPluginExecutor(socket_path, timeout_seconds=1)
        request = TaskCreateRequest(prompt="replay me")
        first = await executor.run(request, request_id="stable-request")
        second = await executor.run(request, request_id="stable-request")
    finally:
        await server.close()

    assert first.result_summary == second.result_summary == "completed: replay me"
    assert handler.calls == 1


@pytest.mark.anyio
async def test_extension_server_reports_handler_failures(tmp_path):
    socket_path = str(tmp_path / "control-extension.sock")

    class FailingHandler:
        async def run(self, request, *, emit):
            raise RuntimeError("Hermes hook unavailable")

    server = HermesExtensionServer(socket_path, FailingHandler())
    await server.start()
    try:
        with pytest.raises(RuntimeError, match="Hermes hook unavailable"):
            await HermesPluginExecutor(socket_path, timeout_seconds=1).run(
                TaskCreateRequest(prompt="fail cleanly")
            )
    finally:
        await server.close()


@pytest.mark.anyio
async def test_extension_server_rejects_missing_or_invalid_auth_token(tmp_path):
    socket_path = str(tmp_path / "protected-extension.sock")
    server = HermesExtensionServer(socket_path, RecordingHandler(), auth_token="secret")
    await server.start()
    try:
        request = TaskCreateRequest(prompt="protected")
        with pytest.raises(RuntimeError, match="invalid Hermes extension token"):
            await HermesPluginExecutor(socket_path, timeout_seconds=1).run(request)
        with pytest.raises(RuntimeError, match="invalid Hermes extension token"):
            await HermesPluginExecutor(socket_path, timeout_seconds=1, auth_token="wrong").run(request)
        result = await HermesPluginExecutor(socket_path, timeout_seconds=1, auth_token="secret").run(request)
    finally:
        await server.close()

    assert result.result_summary == "completed: protected"


@pytest.mark.anyio
async def test_client_disconnect_cancels_inflight_handler(tmp_path):
    socket_path = str(tmp_path / "cancel-extension.sock")

    class BlockingHandler:
        def __init__(self):
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def run(self, request, *, emit):
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise

    handler = BlockingHandler()
    server = HermesExtensionServer(socket_path, handler)
    await server.start()
    reader, writer = await asyncio.open_unix_connection(socket_path)
    writer.write(
        encode_message(
            PluginRequest(
                request_id="cancel-1",
                prompt="cancel me",
                project_id="default",
                priority="normal",
                source="mobile",
                requires_approval=False,
            ).to_message()
        )
    )
    await writer.drain()
    await asyncio.wait_for(handler.started.wait(), timeout=1)

    writer.close()
    await writer.wait_closed()
    await asyncio.wait_for(handler.cancelled.wait(), timeout=1)
    await server.close()


@pytest.mark.anyio
async def test_extension_server_rejects_invalid_resource_limits(tmp_path):
    with pytest.raises(ValueError, match="bridge limits must be positive"):
        await HermesExtensionServer(
            str(tmp_path / "invalid.sock"),
            RecordingHandler(),
            max_message_bytes=0,
        ).start()

    with pytest.raises(ValueError, match="bridge limits must be positive"):
        await HermesExtensionServer(
            str(tmp_path / "invalid.sock"),
            RecordingHandler(),
            max_concurrent_tasks=0,
        ).start()


@pytest.mark.anyio
async def test_server_serve_forever_stops_with_close(tmp_path):
    server = HermesExtensionServer(str(tmp_path / "lifecycle.sock"), RecordingHandler())
    await server.start()
    serving = asyncio.create_task(server.serve_forever())
    await asyncio.sleep(0)
    await server.close()
    await asyncio.wait_for(serving, timeout=1)


@pytest.mark.anyio
async def test_heartbeat_loop_is_cancelable():
    server = HermesExtensionServer("unused.sock", RecordingHandler(), heartbeat_seconds=0.001)
    events = []

    async def emit(event):
        events.append(event)

    heartbeat = asyncio.create_task(server._heartbeat_loop("heartbeat-request", emit))
    await asyncio.sleep(0.01)
    heartbeat.cancel()
    await asyncio.gather(heartbeat, return_exceptions=True)

    assert events
    assert all(event.event_type == "heartbeat" for event in events)
