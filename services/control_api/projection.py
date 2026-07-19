from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from .models import AgentStatus, ProjectSummary, TaskCreateRequest, TaskEvent, TaskStatus, TaskSummary
from .storage import TaskStore
from .workspace import HermesWorkspaceStore


class TaskStateError(ValueError):
    pass


class TaskProjection:
    """Task read model and event projection for the mobile control API."""

    def __init__(self, store: TaskStore | None = None, workspace: HermesWorkspaceStore | None = None) -> None:
        self._store = store
        self.workspace = workspace
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
            requires_approval=request.requires_approval,
            execution_folder=request.execution_folder,
            parent_task_id=request.parent_task_id,
            root_task_id=request.root_task_id,
            session_id=request.session_id,
            relation=request.relation,
            idempotency_key=request.idempotency_key,
            status=TaskStatus.AWAITING_APPROVAL if request.requires_approval else TaskStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        self._tasks[task_id] = task
        self._save(task)
        self.record_event(task_id, event_type="task.created", status=TaskStatus(task.status), message="Task created")
        if request.requires_approval:
            self.record_event(
                task_id,
                event_type="task.approval_requested",
                status=TaskStatus.AWAITING_APPROVAL,
                message="Task is waiting for approval",
            )
        return task

    def list_tasks(self, *, include_archived: bool = False) -> list[TaskSummary]:
        tasks = self._tasks.values() if include_archived else (task for task in self._tasks.values() if task.archived_at is None)
        return sorted(tasks, key=lambda task: task.created_at, reverse=True)

    def get_task(self, task_id: str) -> TaskSummary | None:
        return self._tasks.get(task_id)

    def get_task_by_idempotency_key(self, key: str) -> TaskSummary | None:
        return next((task for task in self._tasks.values() if task.idempotency_key == key), None)

    def cancel_task(self, task_id: str) -> TaskSummary:
        self._require_status(task_id, {TaskStatus.AWAITING_APPROVAL, TaskStatus.QUEUED, TaskStatus.RUNNING})
        return self.update_task(
            task_id,
            status=TaskStatus.CANCELED,
            progress_message="Task canceled from mobile control",
            event_type="task.canceled",
        )

    def approve_task(self, task_id: str) -> TaskSummary:
        self._require_status(task_id, {TaskStatus.AWAITING_APPROVAL})
        return self.update_task(
            task_id,
            status=TaskStatus.QUEUED,
            progress_message="Task approved from mobile control",
            event_type="task.approved",
        )

    def reject_task(self, task_id: str) -> TaskSummary:
        self._require_status(task_id, {TaskStatus.AWAITING_APPROVAL})
        return self.update_task(
            task_id,
            status=TaskStatus.REJECTED,
            progress_message="Task rejected from mobile control",
            event_type="task.rejected",
        )

    def archive_task(self, task_id: str) -> TaskSummary:
        task = self._tasks[task_id]
        terminal_statuses = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELED, TaskStatus.REJECTED, TaskStatus.BLOCKED}
        if TaskStatus(task.status) not in terminal_statuses:
            raise ValueError("Only terminal tasks can be archived")
        if task.archived_at is not None:
            return task
        return self._set_archived(task, archived_at=datetime.now(timezone.utc), event_type="task.archived", message="Task removed from inbox")

    def restore_task(self, task_id: str) -> TaskSummary:
        task = self._tasks[task_id]
        if task.archived_at is None:
            return task
        return self._set_archived(task, archived_at=None, event_type="task.restored", message="Task restored to inbox")

    def list_task_events(self, task_id: str) -> list[TaskEvent]:
        return sorted(self._events.get(task_id, []), key=lambda event: event.created_at)

    def _require_status(self, task_id: str, allowed: set[TaskStatus]) -> TaskSummary:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(task_id)
        current = TaskStatus(task.status)
        if current not in allowed:
            expected = ", ".join(item.value for item in sorted(allowed, key=lambda item: item.value))
            raise TaskStateError(f"task is {current.value}; expected one of: {expected}")
        return task

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        progress_message: str | None = None,
        result_summary: str | None = None,
        error: str | None = None,
        session_id: str | None = None,
        blocker_category: str | None = None,
        blocker_message: str | None = None,
        blocker_retryable: bool = False,
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
        if session_id is not None:
            update_data["session_id"] = session_id
        if blocker_category is not None:
            update_data["blocker_category"] = blocker_category
            update_data["blocker_message"] = blocker_message or error
            update_data["blocker_retryable"] = blocker_retryable
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
        metadata: dict[str, object] | None = None,
    ) -> TaskEvent:
        event = TaskEvent(task_id=task_id, event_type=event_type, status=status, message=message, metadata=metadata or {})
        self._events[task_id].append(event)
        if self._store is not None:
            self._store.save_event(event)
        return event

    def _set_archived(self, task: TaskSummary, *, archived_at: datetime | None, event_type: str, message: str) -> TaskSummary:
        updated = task.model_copy(update={"archived_at": archived_at, "updated_at": datetime.now(timezone.utc)})
        self._tasks[task.task_id] = updated
        self._save(updated)
        self.record_event(task.task_id, event_type=event_type, status=TaskStatus(updated.status), message=message)
        return updated

    def _save(self, task: TaskSummary) -> None:
        if self._store is not None:
            self._store.save_task(task)

    def list_projects(self, *, include_archived: bool = False) -> list[ProjectSummary]:
        workspace_projects = self.workspace.list_projects(include_archived=include_archived) if self.workspace is not None else []
        known = {project.project_id: project for project in workspace_projects}
        counts: dict[str, dict[TaskStatus, int]] = defaultdict(lambda: defaultdict(int))
        for task in self._tasks.values():
            if task.archived_at is not None:
                continue
            counts[task.project_id][TaskStatus(task.status)] += 1

        projects: list[ProjectSummary] = []
        for project_id, status_counts in counts.items():
            project = known.get(project_id, ProjectSummary(project_id=project_id, name=self._project_name(project_id)))
            projects.append(project.model_copy(update={
                "queued_count": status_counts[TaskStatus.QUEUED] + status_counts[TaskStatus.AWAITING_APPROVAL],
                "running_count": status_counts[TaskStatus.RUNNING],
                "completed_count": status_counts[TaskStatus.COMPLETED],
                "failed_count": status_counts[TaskStatus.FAILED] + status_counts[TaskStatus.CANCELED] + status_counts[TaskStatus.REJECTED],
            }))
        for project in workspace_projects:
            if project.project_id not in {item.project_id for item in projects}:
                projects.append(project)
        if not projects:
            projects.append(ProjectSummary(project_id="default", name="Default"))
        return sorted(projects, key=lambda project: project.name.lower())

    def get_project(self, project_id: str, *, include_archived: bool = True) -> ProjectSummary | None:
        return next((project for project in self.list_projects(include_archived=include_archived) if project.project_id == project_id), None)

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
