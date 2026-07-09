from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from .models import AgentStatus, ProjectSummary, TaskCreateRequest, TaskEvent, TaskStatus, TaskSummary
from .storage import TaskStore


class TaskProjection:
    """Task read model and event projection for the mobile control API."""

    def __init__(self, store: TaskStore | None = None) -> None:
        self._store = store
        self._tasks: dict[str, TaskSummary] = {task.task_id: task for task in store.load_tasks()} if store else {}
        self._events: dict[str, list[TaskEvent]] = defaultdict(list)
        if store:
            for event in store.load_events():
                self._events[event.task_id].append(event)
        self._agents: dict[str, AgentStatus] = {
            "hermes-agent": AgentStatus(agent_id="hermes-agent"),
        }

    def create_task(self, request: TaskCreateRequest) -> TaskSummary:
        task_id = f"task-{uuid4().hex}"
        now = datetime.now(timezone.utc)
        task = TaskSummary(
            task_id=task_id,
            title=self._title_from_prompt(request.prompt),
            prompt=request.prompt,
            project_id=request.project_id,
            source=request.source,
            priority=request.priority,
            status=TaskStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        self._tasks[task_id] = task
        self._save(task)
        self.record_event(task_id, event_type="task.created", status=TaskStatus.QUEUED, message="Task queued")
        return task

    def list_tasks(self) -> list[TaskSummary]:
        return sorted(self._tasks.values(), key=lambda task: task.created_at, reverse=True)

    def get_task(self, task_id: str) -> TaskSummary | None:
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> TaskSummary:
        return self.update_task(
            task_id,
            status=TaskStatus.CANCELED,
            progress_message="Task canceled from mobile control",
            event_type="task.canceled",
        )

    def list_task_events(self, task_id: str) -> list[TaskEvent]:
        return sorted(self._events.get(task_id, []), key=lambda event: event.created_at)

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        progress_message: str | None = None,
        result_summary: str | None = None,
        error: str | None = None,
        event_type: str = "task.updated",
    ) -> TaskSummary:
        task = self._tasks[task_id]
        update_data = task.model_dump()
        if status is not None:
            update_data["status"] = status
        if progress_message:
            update_data["progress_log"] = [*task.progress_log, progress_message]
        if result_summary is not None:
            update_data["result_summary"] = result_summary
        if error is not None:
            update_data["error"] = error
        update_data["updated_at"] = datetime.now(timezone.utc)
        updated = TaskSummary(**update_data)
        self._tasks[task_id] = updated
        self._save(updated)
        self.record_event(
            task_id,
            event_type=event_type,
            status=TaskStatus(updated.status),
            message=progress_message or result_summary or error,
        )
        return updated

    def record_event(
        self,
        task_id: str,
        *,
        event_type: str,
        status: TaskStatus | None = None,
        message: str | None = None,
    ) -> TaskEvent:
        event = TaskEvent(task_id=task_id, event_type=event_type, status=status, message=message)
        self._events[task_id].append(event)
        if self._store is not None:
            self._store.save_event(event)
        return event

    def _save(self, task: TaskSummary) -> None:
        if self._store is not None:
            self._store.save_task(task)

    def list_projects(self) -> list[ProjectSummary]:
        counts: dict[str, dict[TaskStatus, int]] = defaultdict(lambda: defaultdict(int))
        for task in self._tasks.values():
            counts[task.project_id][TaskStatus(task.status)] += 1

        projects = []
        for project_id, status_counts in sorted(counts.items()):
            projects.append(
                ProjectSummary(
                    project_id=project_id,
                    name=self._project_name(project_id),
                    queued_count=status_counts[TaskStatus.QUEUED],
                    running_count=status_counts[TaskStatus.RUNNING],
                    completed_count=status_counts[TaskStatus.COMPLETED],
                    failed_count=status_counts[TaskStatus.FAILED] + status_counts[TaskStatus.CANCELED],
                )
            )
        if not projects:
            projects.append(ProjectSummary(project_id="default", name="Default"))
        return projects

    def list_agents(self) -> list[AgentStatus]:
        return sorted(self._agents.values(), key=lambda agent: agent.agent_id)

    @staticmethod
    def _title_from_prompt(prompt: str) -> str:
        words = prompt.strip().split()
        title = " ".join(words[:8])
        return title or "Untitled task"

    @staticmethod
    def _project_name(project_id: str) -> str:
        return project_id.replace("-", " ").replace("_", " ").title()
