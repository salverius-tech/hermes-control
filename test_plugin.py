from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


PLUGIN_PATH = Path(__file__).with_name("__init__.py")


def load_plugin():
    spec = importlib.util.spec_from_file_location("hermes_control_plugin_test", PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


@pytest.mark.unit
def test_plugin_tool_creates_task_with_expected_api_request(monkeypatch):
    plugin = load_plugin()
    captured = {}

    def fake_urlopen(request, timeout):
        captured["method"] = request.method
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse({"task_id": "task-1"})

    monkeypatch.setattr(plugin, "urlopen", fake_urlopen)
    monkeypatch.setenv("CONTROL_API_URL", "http://control.test")
    monkeypatch.setenv("CONTROL_API_TOKEN", "secret")

    result = json.loads(
        plugin._handle_control(
            {
                "action": "create_task",
                "prompt": "Check status",
                "project_id": "ops",
                "priority": "high",
                "requires_approval": True,
            }
        )
    )

    assert result == {"ok": True, "data": {"task_id": "task-1"}}
    assert captured == {
        "method": "POST",
        "url": "http://control.test/tasks",
        "headers": {"Authorization": "Bearer secret", "Content-type": "application/json"},
        "body": {
            "prompt": "Check status",
            "project_id": "ops",
            "priority": "high",
            "source": "hermes-plugin",
            "requires_approval": True,
        },
        "timeout": 10,
    }


@pytest.mark.unit
def test_plugin_tool_rejects_create_without_prompt(monkeypatch):
    plugin = load_plugin()
    monkeypatch.setattr(plugin, "urlopen", lambda *_args, **_kwargs: pytest.fail("network call unexpected"))

    result = json.loads(plugin._handle_control({"action": "create_task"}))

    assert result == {"ok": False, "error": "prompt is required for create_task"}


@pytest.mark.unit
def test_plugin_tool_converts_api_errors_to_structured_failure(monkeypatch):
    plugin = load_plugin()

    def fail(*_args, **_kwargs):
        raise OSError("control API unavailable")

    monkeypatch.setattr(plugin, "urlopen", fail)

    result = json.loads(plugin._handle_control({"action": "tasks"}))

    assert result["ok"] is False
    assert "control API unavailable" in result["error"]


@pytest.mark.unit
def test_plugin_registers_tool_and_starts_bridge(monkeypatch):
    plugin = load_plugin()
    registered = {}
    started = []

    class Context:
        def register_tool(self, **kwargs):
            registered.update(kwargs)

    monkeypatch.setattr(plugin, "_start_bridge", lambda: started.append(True))

    plugin.register(Context())

    assert registered["name"] == "hermes_control"
    assert registered["handler"] is plugin._handle_control
    assert started == [True]
