import sys

import pytest

from services.hermes_extension.host import (
    NativeHermesTaskHandler,
    SubprocessHermesTaskHandler,
    handler_from_environment,
)
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
async def test_subprocess_handler_appends_prompt_for_query_mode():
    handler = SubprocessHermesTaskHandler(
        (
            sys.executable,
            "-c",
            "import sys; print('query:' + sys.argv[-1])",
            "-q",
        )
    )

    async def emit(_event):
        return None

    result = await handler.run(
        PluginRequest("req-query", "inspect this", "default", "normal", "mobile", False),
        emit=emit,
    )

    assert result == "query:inspect this"


@pytest.mark.anyio
async def test_subprocess_handler_completes_on_hermes_session_footer():
    handler = SubprocessHermesTaskHandler(
        (
            sys.executable,
            "-u",
            "-c",
            "import time; print('result'); print('Session: test'); time.sleep(30)",
        ),
        timeout_seconds=10,
    )

    async def emit(_event):
        return None

    result = await handler.run(
        PluginRequest("req-footer", "inspect", "default", "normal", "mobile", False),
        emit=emit,
    )

    assert result == "result\nSession: test"


@pytest.mark.anyio
async def test_subprocess_handler_suppresses_interpreter_shutdown_traceback_from_progress():
    handler = SubprocessHermesTaskHandler(
        (
            sys.executable,
            "-c",
            "import sys; print('result'); print('Exception ignored on threading shutdown:', file=sys.stderr); print('Traceback (most recent call last):', file=sys.stderr); print('KeyboardInterrupt:', file=sys.stderr)",
        )
    )
    events = []

    async def emit(event):
        events.append(event)

    result = await handler.run(
        PluginRequest("req-noise", "inspect", "default", "normal", "mobile", False),
        emit=emit,
    )

    assert result == "result"
    assert [event.message for event in events] == ["result"]


def test_default_handler_disables_recursive_plugin_loading(monkeypatch):
    monkeypatch.delenv("HERMES_CONTROL_EXTENSION_HERMES_COMMAND", raising=False)

    handler = handler_from_environment()

    assert handler.command == (
        "hermes",
        "chat",
        "--ignore-user-config",
        "--ignore-rules",
        "-q",
    )


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
