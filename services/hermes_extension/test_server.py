import os

import pytest

from services.control_api.hermes_client import HermesPluginExecutor
from services.control_api.models import TaskCreateRequest
from services.hermes_extension import HermesExtensionServer, PluginEvent


pytestmark = pytest.mark.unit


class RecordingHandler:
    async def run(self, request, *, emit):
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
