from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

BRIDGE_VERSION = 1


@dataclass(frozen=True)
class PluginRequest:
    """A task request sent from the Control API to the Hermes plugin."""

    request_id: str
    prompt: str
    project_id: str
    priority: str
    source: str
    requires_approval: bool
    auth_token: str | None = None

    def to_message(self) -> dict[str, Any]:
        message = {
            "version": BRIDGE_VERSION,
            "type": "task.submit",
            "request_id": self.request_id,
            "task": {
                "prompt": self.prompt,
                "project_id": self.project_id,
                "priority": self.priority,
                "source": self.source,
                "requires_approval": self.requires_approval,
            },
        }
        if self.auth_token is not None:
            message["auth_token"] = self.auth_token
        return message

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> "PluginRequest":
        if message.get("version") != BRIDGE_VERSION or message.get("type") != "task.submit":
            raise ValueError("expected versioned task.submit message")
        request_id = message.get("request_id")
        task = message.get("task")
        if not isinstance(request_id, str) or not isinstance(task, dict):
            raise ValueError("task.submit requires request_id and task")
        required = ("prompt", "project_id", "priority", "source", "requires_approval")
        if any(field not in task for field in required):
            raise ValueError("task.submit task payload is incomplete")
        if not all(isinstance(task[field], str) for field in ("prompt", "project_id", "priority", "source")):
            raise ValueError("task.submit string fields are invalid")
        if not task["prompt"].strip() or not task["project_id"].strip() or not task["source"].strip():
            raise ValueError("task.submit string fields must not be blank")
        if task["priority"] not in {"low", "normal", "high"}:
            raise ValueError("task.submit priority is invalid")
        if not isinstance(task["requires_approval"], bool):
            raise ValueError("task.submit requires_approval must be boolean")
        auth_token = message.get("auth_token")
        if auth_token is not None and not isinstance(auth_token, str):
            raise ValueError("task.submit auth_token is invalid")
        return cls(
            request_id=request_id,
            prompt=task["prompt"],
            project_id=task["project_id"],
            priority=task["priority"],
            source=task["source"],
            requires_approval=task["requires_approval"],
            auth_token=auth_token,
        )


@dataclass(frozen=True)
class PluginEvent:
    """A structured event emitted by the Hermes plugin."""

    event_type: str
    request_id: str
    message: str | None = None
    result_summary: str | None = None
    error: str | None = None

    def to_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {
            "version": BRIDGE_VERSION,
            "type": "task.event",
            "event": self.event_type,
            "request_id": self.request_id,
        }
        if self.message is not None:
            message["message"] = self.message
        if self.result_summary is not None:
            message["result_summary"] = self.result_summary
        if self.error is not None:
            message["error"] = self.error
        return message

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> "PluginEvent":
        if message.get("version") != BRIDGE_VERSION:
            raise ValueError("unsupported Hermes extension bridge version")
        if message.get("type") != "task.event":
            raise ValueError("expected task.event message")
        request_id = message.get("request_id")
        event_type = message.get("event")
        if not isinstance(request_id, str) or not isinstance(event_type, str):
            raise ValueError("task.event requires request_id and event")
        return cls(
            event_type=event_type,
            request_id=request_id,
            message=message.get("message"),
            result_summary=message.get("result_summary"),
            error=message.get("error"),
        )


def encode_message(message: dict[str, Any]) -> bytes:
    """Encode one bridge message as a single newline-delimited JSON record."""

    return (json.dumps(message, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def decode_message(line: bytes) -> dict[str, Any]:
    """Decode and validate the common bridge envelope."""

    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError("bridge message must be a JSON object")
    if message.get("version") != BRIDGE_VERSION:
        raise ValueError("unsupported Hermes extension bridge version")
    return message
