import pytest

from services.control_api.hermes_client import FakeHermesExecutor, HermesTaskService
from services.control_api.models import TaskCreateRequest
from services.control_api.notifications import DiscordWebhookNotifier, NullNotifier, notifier_from_environment
from services.control_api.projection import TaskProjection


pytestmark = pytest.mark.unit


@pytest.mark.anyio
async def test_discord_notifier_posts_task_payload():
    calls = []

    async def post(url: str, payload: dict[str, object]) -> None:
        calls.append((url, payload))

    notifier = DiscordWebhookNotifier("https://discord.example/webhook", post=post)
    task = TaskProjection().create_task(TaskCreateRequest(prompt="Review status", project_id="ops", priority="high"))

    await notifier.notify_task(task, event_type="task.completed")

    assert calls == [
        (
            "https://discord.example/webhook",
            {
                "content": "Hermes task completed: Review status",
                "embeds": [
                    {
                        "title": "Review status",
                        "description": "Project: ops\nPriority: high\nStatus: queued",
                        "color": 0x22C55E,
                    }
                ],
            },
        )
    ]


@pytest.mark.anyio
async def test_null_notifier_is_safe_noop():
    task = TaskProjection().create_task(TaskCreateRequest(prompt="No webhook"))

    await NullNotifier().notify_task(task, event_type="task.failed")


@pytest.mark.anyio
async def test_notifier_from_environment_uses_null_without_webhook(monkeypatch):
    monkeypatch.delenv("CONTROL_API_DISCORD_WEBHOOK_URL", raising=False)

    assert isinstance(notifier_from_environment(), NullNotifier)


@pytest.mark.anyio
async def test_task_service_notifies_approval_requests_and_terminal_states():
    events = []

    class RecordingNotifier:
        async def notify_task(self, task, *, event_type: str) -> None:
            events.append((event_type, task.status, task.title))

    projection = TaskProjection()
    service = HermesTaskService(
        projection=projection,
        executor=FakeHermesExecutor(result_summary="done"),
        notifier=RecordingNotifier(),
    )

    await service.submit_task(TaskCreateRequest(prompt="Needs review", requires_approval=True))
    await service.submit_task(TaskCreateRequest(prompt="Run now"), run_inline=True)

    assert events == [
        ("task.approval_requested", "awaiting_approval", "Needs review"),
        ("task.completed", "completed", "Run now"),
    ]


@pytest.mark.anyio
async def test_task_service_notifies_failures():
    events = []

    class RecordingNotifier:
        async def notify_task(self, task, *, event_type: str) -> None:
            events.append((event_type, task.status, task.error))

    service = HermesTaskService(
        projection=TaskProjection(),
        executor=FakeHermesExecutor(error="boom"),
        notifier=RecordingNotifier(),
    )

    await service.submit_task(TaskCreateRequest(prompt="Fail"), run_inline=True)

    assert events == [("task.failed", "failed", "boom")]
