"""Hermes Control Extension plugin entrypoint."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.hermes_extension import HermesExtensionServer, handler_from_environment

_TOOL_SCHEMA = {
    "name": "hermes_control",
    "description": "Inspect the local Hermes Control API from inside Hermes.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["health", "tasks"],
                "description": "Control API read operation.",
            }
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def _control_api(action: str) -> str:
    base_url = os.getenv("CONTROL_API_URL", "http://127.0.0.1:8787").rstrip("/")
    token = os.getenv("CONTROL_API_TOKEN", "")
    paths = {"health": "/health", "tasks": "/tasks"}
    path = paths.get(action)
    if path is None:
        return json.dumps({"ok": False, "error": "unsupported action"})
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        request = Request(f"{base_url}{path}", headers=headers)
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
        return json.dumps({"ok": True, "data": payload}, sort_keys=True)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return json.dumps({"ok": False, "error": str(error)})


def _handle_control(args: dict[str, Any], **_: Any) -> str:
    return _control_api(str(args.get("action", "")).strip().lower())


def _run_bridge() -> None:
    socket_path = os.getenv("HERMES_CONTROL_EXTENSION_SOCKET", "/run/hermes/control-extension.sock")

    async def serve() -> None:
        server = HermesExtensionServer(
            socket_path,
            handler_from_environment(),
            auth_token=os.getenv("HERMES_CONTROL_EXTENSION_TOKEN"),
        )
        await server.start()
        await asyncio.Event().wait()

    try:
        asyncio.run(serve())
    except (OSError, RuntimeError):
        return


def _start_bridge() -> None:
    thread = threading.Thread(target=_run_bridge, name="hermes-control-extension", daemon=True)
    thread.start()


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
