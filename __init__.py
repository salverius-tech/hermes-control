"""Hermes Control Extension plugin entrypoint."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .services.hermes_extension import HermesExtensionServer, handler_from_environment
except ImportError:
    from services.hermes_extension import HermesExtensionServer, handler_from_environment

_bridge_stop_event = threading.Event()
_bridge_thread: threading.Thread | None = None
_logger = logging.getLogger(__name__)


_TOOL_SCHEMA = {
    "name": "hermes_control",
    "description": "Inspect or submit tasks through the local Hermes Control API.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["health", "tasks", "create_task"],
                "description": "Control API operation.",
            },
            "prompt": {"type": "string", "description": "Prompt for create_task."},
            "project_id": {"type": "string", "description": "Project for create_task."},
            "priority": {"type": "string", "enum": ["low", "normal", "high"]},
            "requires_approval": {"type": "boolean"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def _control_api(args: dict[str, Any]) -> str:
    action = str(args.get("action", "")).strip().lower()
    base_url = os.getenv("CONTROL_API_URL", "http://127.0.0.1:8787").rstrip("/")
    token = os.getenv("CONTROL_API_TOKEN", "")
    paths = {"health": "/health", "tasks": "/tasks"}
    path = paths.get(action)
    method = "GET"
    body = None
    if action == "create_task":
        prompt = str(args.get("prompt", "")).strip()
        if not prompt:
            return json.dumps({"ok": False, "error": "prompt is required for create_task"})
        path = "/tasks"
        method = "POST"
        body = json.dumps(
            {
                "prompt": prompt,
                "project_id": str(args.get("project_id", "default")),
                "priority": str(args.get("priority", "normal")),
                "source": "hermes-plugin",
                "requires_approval": bool(args.get("requires_approval", False)),
            }
        ).encode()
    if path is None:
        return json.dumps({"ok": False, "error": "unsupported action"})
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        request = Request(f"{base_url}{path}", data=body, headers=headers, method=method)
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
        return json.dumps({"ok": True, "data": payload}, sort_keys=True)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as error:
        return json.dumps({"ok": False, "error": str(error)})


def _handle_control(args: dict[str, Any], **_: Any) -> str:
    return _control_api(args)


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _nonnegative_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def _bridge_token() -> str | None:
    token = os.getenv("HERMES_CONTROL_EXTENSION_TOKEN")
    if token:
        return token
    if os.getenv("HERMES_CONTROL_EXTENSION_ALLOW_UNAUTHENTICATED") == "1":
        return None
    raise RuntimeError(
        "HERMES_CONTROL_EXTENSION_TOKEN is required; set "
        "HERMES_CONTROL_EXTENSION_ALLOW_UNAUTHENTICATED=1 only for development"
    )


def _run_bridge() -> None:
    socket_path = os.getenv("HERMES_CONTROL_EXTENSION_SOCKET", "/run/hermes/control-extension.sock")

    async def serve() -> None:
        server = HermesExtensionServer(
            socket_path,
            handler_from_environment(),
            auth_token=_bridge_token(),
            max_message_bytes=_positive_int("HERMES_CONTROL_EXTENSION_MAX_MESSAGE_BYTES", 1_048_576),
            max_concurrent_tasks=_positive_int("HERMES_CONTROL_EXTENSION_MAX_CONCURRENT_TASKS", 4),
            heartbeat_seconds=_nonnegative_float("HERMES_CONTROL_EXTENSION_HEARTBEAT_SECONDS", 0),
        )
        try:
            await server.start()
            await asyncio.to_thread(_bridge_stop_event.wait)
        finally:
            await server.close()

    try:
        asyncio.run(serve())
    except (OSError, RuntimeError):
        _logger.exception("Hermes Control Extension bridge failed to start at %s", socket_path)


def _start_bridge() -> None:
    global _bridge_thread
    if _bridge_thread is not None and _bridge_thread.is_alive():
        return
    _bridge_stop_event.clear()
    _bridge_thread = threading.Thread(target=_run_bridge, name="hermes-control-extension", daemon=True)
    _bridge_thread.start()


def stop_bridge() -> None:
    """Stop the plugin bridge during Hermes plugin unload or test teardown."""
    _bridge_stop_event.set()


def register(ctx) -> None:
    ctx.register_tool(
        name="hermes_control",
        toolset="hermes_control",
        schema=_TOOL_SCHEMA,
        handler=_handle_control,
        description="Read the local Hermes Control API.",
        emoji="📱",
    )
    _start_bridge()
