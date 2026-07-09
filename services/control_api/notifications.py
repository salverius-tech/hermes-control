from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

import httpx

from .models import TaskStatus, TaskSummary


class TaskNotifier(Protocol):
    async def notify_task(self, task: TaskSummary, *, event_type: str) -> None: ...


@dataclass(frozen=True)
class NullNotifier:
    async def notify_task(self, task: TaskSummary, *, event_type: str) -> None:
        return None


DiscordPost = Callable[[str, dict[str, object]], Awaitable[None]]


async def _post_discord_webhook(url: str, payload: dict[str, object]) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()


@dataclass(frozen=True)
class DiscordWebhookNotifier:
    webhook_url: str
    post: DiscordPost = _post_discord_webhook

    async def notify_task(self, task: TaskSummary, *, event_type: str) -> None:
        await self.post(self.webhook_url, _discord_payload(task, event_type=event_type))


def notifier_from_environment() -> TaskNotifier:
    webhook_url = os.getenv("CONTROL_API_DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return NullNotifier()
    return DiscordWebhookNotifier(webhook_url)


def _discord_payload(task: TaskSummary, *, event_type: str) -> dict[str, object]:
    return {
        "content": f"Hermes {_event_label(event_type)}: {task.title}",
        "embeds": [
            {
                "title": task.title,
                "description": f"Project: {task.project_id}\nPriority: {task.priority}\nStatus: {task.status}",
                "color": _event_color(event_type, fallback_status=TaskStatus(task.status)),
            }
        ],
    }


def _event_label(event_type: str) -> str:
    labels = {
        "task.approval_requested": "task awaiting approval",
        "task.completed": "task completed",
        "task.failed": "task failed",
        "task.canceled": "task canceled",
        "task.rejected": "task rejected",
    }
    return labels.get(event_type, "task updated")


def _status_color(status: TaskStatus) -> int:
    colors = {
        TaskStatus.AWAITING_APPROVAL: 0x38BDF8,
        TaskStatus.COMPLETED: 0x22C55E,
        TaskStatus.FAILED: 0xEF4444,
        TaskStatus.CANCELED: 0x94A3B8,
        TaskStatus.REJECTED: 0xEF4444,
    }
    return colors.get(status, 0x8B5CF6)


def _event_color(event_type: str, *, fallback_status: TaskStatus) -> int:
    colors = {
        "task.approval_requested": 0x38BDF8,
        "task.completed": 0x22C55E,
        "task.failed": 0xEF4444,
        "task.canceled": 0x94A3B8,
        "task.rejected": 0xEF4444,
    }
    return colors.get(event_type, _status_color(fallback_status))
