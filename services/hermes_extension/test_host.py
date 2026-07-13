import sys

import pytest

from services.hermes_extension.host import NativeHermesTaskHandler, SubprocessHermesTaskHandler
from services.hermes_extension.protocol import PluginRequest


pytestmark = pytest.mark.unit


@pytest.mark.anyio
async def test_subprocess_handler_forwards_output_and_returns_stdout():
    handler = SubprocessHermesTaskHandler(
        (
            sys.executable,
            "-c",
            "import sys; print('result:' + sys.stdin.read()); print('progress', file=sys.stderr)",
        )
    )
    events = []

    async def emit(event):
        events.append(event)

    result = await handler.run(
        PluginRequest(
            request_id="req-1",
            prompt="inspect",
            project_id="default",
            priority="normal",
            source="mobile",
            requires_approval=False,
        ),
        emit=emit,
    )

    assert result == "result:inspect"
    assert {event.message for event in events} == {"progress", "result:inspect"}
    assert all(event.event_type == "progress" for event in events)


@pytest.mark.anyio
async def test_native_handler_delegates_to_injected_supported_runner():
    events = []

    async def runner(request, emit):
        await emit(PluginEvent(event_type="progress", request_id=request.request_id, message="native"))
        return "native result"

    from services.hermes_extension.protocol import PluginEvent

    async def emit(event):
        events.append(event)

    result = await NativeHermesTaskHandler(runner).run(
        PluginRequest("req-native", "inspect", "default", "normal", "test", False),
        emit=emit,
    )

    assert result == "native result"
    assert events[0].message == "native"


@pytest.mark.anyio
async def test_subprocess_handler_reports_nonzero_exit():
    handler = SubprocessHermesTaskHandler(
        (sys.executable, "-c", "import sys; print('failed', file=sys.stderr); raise SystemExit(3)")
    )

    async def emit(_event):
        return None

    with pytest.raises(RuntimeError, match="failed"):
        await handler.run(
            PluginRequest(
                request_id="req-2",
                prompt="fail",
                project_id="default",
                priority="normal",
                source="mobile",
                requires_approval=False,
            ),
            emit=emit,
        )
