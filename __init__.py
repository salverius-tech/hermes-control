"""Hermes Control Extension plugin entrypoint.

The plugin registers the Control API tool only. Task execution is owned by the
separately supervised ``hermes-control-bridge.service``.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_logger = logging.getLogger(__name__)

_TOOL_SCHEMA = {
    "name": "hermes_control",
    "description": "Inspect or submit tasks through the local Hermes Control API.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["health", "tasks", "create_task"]},
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
        path, method = "/tasks", "POST"
        body = json.dumps({
            "prompt": prompt,
            "project_id": str(args.get("project_id", "default")),
            "priority": str(args.get("priority", "normal")),
            "source": "hermes-plugin",
            "requires_approval": bool(args.get("requires_approval", False)),
        }).encode()
    if path is None:
        return json.dumps({"ok": False, "error": "unsupported action"})
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(f"{base_url}{path}", data=body, headers=headers, method=method), timeout=10) as response:
            payload = json.loads(response.read())
        return json.dumps({"ok": True, "data": payload}, sort_keys=True)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as error:
        return json.dumps({"ok": False, "error": str(error)})


def _handle_control(args: dict[str, Any], **_: Any) -> str:
    return _control_api(args)


def register(ctx) -> None:
    ctx.register_tool(
        name="hermes_control",
        toolset="hermes_control",
        schema=_TOOL_SCHEMA,
        handler=_handle_control,
        description="Read the local Hermes Control API.",
        emoji="📱",
    )
    _logger.debug("Hermes Control Extension registered; bridge lifecycle is managed by hermes-control-bridge.service")
