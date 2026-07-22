from __future__ import annotations

import os
import secrets
import shlex
import shutil
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status

from .auth import expected_token, require_auth
from .hermes_client import HermesTaskService
from .managed_workspace import ManagedWorkspaceStore, ProjectManifest
from .models import (
    AgentStatus,
    ApprovalRequest,
    FolderRequest,
    GuidanceRequest,
    NewSessionRequest,
    ProjectCreateRequest,
    RecoveryApplyRequest,
    RepositoryAttachRequest,
    ProjectSummary,
    ProjectUpdateRequest,
    SessionSummary,
    WorkThreadSummary,
    TaskCreateRequest,
    TaskEvent,
    TaskStatus,
    TaskSummary,
)
from .notifications import notifier_from_environment
from .projection import TaskProjection, TaskStateError
from .rate_limit import RateLimiter
from .storage import SQLiteTaskStore
from .websocket import ConnectionManager
from .recovery_audit import RecoveryAuditStore
from .workspace import HermesWorkspaceStore


def create_app() -> FastAPI:
    app = FastAPI(title="Hermes Mobile Control API", version="0.1.0")
    store_path = os.getenv("CONTROL_API_DB_PATH")
    store = SQLiteTaskStore(store_path) if store_path else None
    recovery_audit = RecoveryAuditStore(store_path) if store_path else None
    hermes_home = os.getenv("CONTROL_API_HERMES_HOME")
    allow_synthetic_projects = os.getenv("CONTROL_API_ALLOW_SYNTHETIC_PROJECTS") == "1"
    workspace = HermesWorkspaceStore(hermes_home) if hermes_home else None
    managed_workspace = (
        ManagedWorkspaceStore(workspace, os.environ["CONTROL_API_WORKSPACE_ROOT"])
        if workspace is not None and os.getenv("CONTROL_API_WORKSPACE_ROOT")
        else None
    )
    projection = TaskProjection(
        store=store,
        workspace=workspace,
        allow_synthetic_projects=allow_synthetic_projects,
    )
    task_service = HermesTaskService(
        projection=projection,
        notifier=notifier_from_environment(),
        max_concurrent_tasks=int(os.getenv("CONTROL_API_MAX_CONCURRENT_TASKS", "4")),
        stall_after_seconds=float(os.getenv("CONTROL_API_TASK_STALL_SECONDS", "600")),
    )
    task_rate_limiter = RateLimiter(int(os.getenv("CONTROL_API_RATE_LIMIT_PER_MINUTE", "60")))
    connections = ConnectionManager()

    def enforce_task_rate_limit(request: Request) -> None:
        client = request.client.host if request.client is not None else "unknown"
        if not task_rate_limiter.allow(client):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Task request rate limit exceeded")

    async def broadcast_task_update(task: TaskSummary) -> None:
        await connections.broadcast_task_updated(task)

    def request_from_task(task: TaskSummary, *, requires_approval: bool | None = None, relation: Literal["retry", "edited_retry"] = "retry") -> TaskCreateRequest:
        return TaskCreateRequest(
            prompt=task.prompt,
            project_id=task.project_id,
            priority=task.priority,
            source=task.source,
            requires_approval=task.requires_approval if requires_approval is None else requires_approval,
            parent_task_id=task.task_id,
            root_task_id=task.root_task_id or task.task_id,
            session_id=task.session_id,
            relation=relation,
            execution_folder=task.execution_folder,
        )

    def _require_recovery_source(task: TaskSummary) -> None:
        if task.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Restore the task before creating another attempt")
        active_statuses = {TaskStatus.AWAITING_APPROVAL, TaskStatus.QUEUED, TaskStatus.RUNNING}
        if TaskStatus(task.status) in active_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Task is {task.status}; wait for it to stop before creating another attempt",
            )

    def executor_ready() -> bool:
        plugin_socket = os.getenv("CONTROL_API_HERMES_PLUGIN_SOCKET")
        command = os.getenv("CONTROL_API_HERMES_COMMAND")
        command_parts = shlex.split(command, posix=os.name != "nt") if command else []
        command_ready = bool(command_parts and (Path(command_parts[0]).exists() or shutil.which(command_parts[0])))
        return bool((plugin_socket and Path(plugin_socket).exists()) or command_ready)

    def require_workspace() -> HermesWorkspaceStore:
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Native Hermes project integration is not configured",
            )
        if not workspace.available:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Native Hermes project store is unavailable",
            )
        return workspace

    def resolve_project_context(request: TaskCreateRequest) -> TaskCreateRequest:
        if allow_synthetic_projects and workspace is None:
            if request.execution_folder:
                try:
                    execution_folder = HermesWorkspaceStore().validate_execution_folder(request.execution_folder)
                except ValueError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
                return request.model_copy(update={"execution_folder": execution_folder})
            return request
        native_workspace = require_workspace()
        project = native_workspace.get_project(request.project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown Hermes project: {request.project_id}")
        if project.archived:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Project is archived: {request.project_id}")
        if not project.primary_folder:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Project has no primary folder: {request.project_id}")
        try:
            execution_folder = (
                native_workspace.validate_project_execution_folder(request.project_id, request.execution_folder)
                if request.execution_folder
                else native_workspace.validate_project_execution_folder(request.project_id, project.primary_folder)
            )
            if request.session_id:
                # A resumed Hermes session owns its cwd.  Do not resume it from
                # another folder in the same project, which can silently change
                # the context seen by Hermes.
                session_folder = native_workspace.validate_session(request.session_id, request.project_id)
                if request.execution_folder and execution_folder != session_folder:
                    raise ValueError("execution folder does not match the Hermes session working directory")
                execution_folder = session_folder
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return request.model_copy(update={"execution_folder": execution_folder})

    async def submit_linked_task(request: TaskCreateRequest, *, idempotency_key: str | None) -> TaskSummary:
        if idempotency_key:
            existing = projection.get_task_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
            request = request.model_copy(update={"idempotency_key": idempotency_key})
        request = resolve_project_context(request)
        task = await task_service.submit_task(request, on_update=broadcast_task_update)
        await connections.broadcast_task_created(task)
        if not request.requires_approval:
            task_service.start_task(task, request, on_update=broadcast_task_update)
        return task

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/diagnostics", dependencies=[Depends(require_auth)])
    def diagnostics() -> dict[str, str]:
        plugin_socket = os.getenv("CONTROL_API_HERMES_PLUGIN_SOCKET")
        command = os.getenv("CONTROL_API_HERMES_COMMAND")
        command_parts = shlex.split(command, posix=os.name != "nt") if command else []
        command_ready = bool(command_parts and (Path(command_parts[0]).exists() or shutil.which(command_parts[0])))
        return {
            "version": "0.1.0",
            "storage": "sqlite" if store_path else "memory",
            "schema_version": str(store.schema_version) if store else "0",
            "execution_mode": (
                "plugin"
                if os.getenv("CONTROL_API_HERMES_PLUGIN_SOCKET")
                else "command"
                if os.getenv("CONTROL_API_HERMES_COMMAND")
                else "unconfigured"
            ),
            "notification_mode": "discord" if os.getenv("CONTROL_API_DISCORD_WEBHOOK_URL") else "disabled",
            "websocket_path": "/ws/events",
            "native_projects_configured": str(workspace is not None).lower(),
            "hermes_home_available": str(bool(workspace and workspace.available)).lower(),
            "synthetic_projects_enabled": str(allow_synthetic_projects).lower(),
            "managed_workspace_ready": str(bool(managed_workspace and managed_workspace.ready)).lower(),
            "bridge_configured": str(bool(plugin_socket)).lower(),
            "bridge_socket_available": str(bool(plugin_socket and Path(plugin_socket).exists())).lower(),
            "executor_ready": str(bool((plugin_socket and Path(plugin_socket).exists()) or command_ready)).lower(),
            "active_task_count": str(task_service.active_task_count),
        }

    @app.get("/tasks", dependencies=[Depends(require_auth)])
    def list_tasks(include_archived: bool = False) -> list[TaskSummary]:
        return projection.list_tasks(include_archived=include_archived)

    @app.post("/tasks", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def create_task(request: TaskCreateRequest, idempotency_key: str | None = Header(default=None)) -> TaskSummary:
        if idempotency_key:
            existing = projection.get_task_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
            request = request.model_copy(update={"idempotency_key": idempotency_key})
        request = resolve_project_context(request)
        task = await task_service.submit_task(request, on_update=broadcast_task_update)
        await connections.broadcast_task_created(task)
        if not request.requires_approval:
            task_service.start_task(task, request, on_update=broadcast_task_update)
        return task

    @app.post("/tasks/{task_id}/approve", dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def approve_task(task_id: str, request: ApprovalRequest | None = None) -> TaskSummary:
        original = projection.get_task(task_id)
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        try:
            task = projection.approve_task(task_id)
        except TaskStateError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        approval = request or ApprovalRequest()
        projection.record_event(task_id, event_type="approval.audit", status=task.status, message=approval.reason, metadata=approval.model_dump())
        await connections.broadcast_task_updated(task)
        task_service.start_task(task, request_from_task(task, requires_approval=False), on_update=broadcast_task_update)
        return task

    @app.post("/tasks/{task_id}/reject", dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def reject_task(task_id: str, request: ApprovalRequest | None = None) -> TaskSummary:
        if projection.get_task(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        try:
            task = projection.reject_task(task_id)
        except TaskStateError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        approval = request or ApprovalRequest()
        projection.record_event(task_id, event_type="approval.audit", status=task.status, message=approval.reason, metadata=approval.model_dump())
        await task_service.notify_task(task, event_type="task.rejected")
        await connections.broadcast_task_updated(task)
        return task

    @app.post("/tasks/{task_id}/cancel", dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def cancel_task(task_id: str) -> TaskSummary:
        if projection.get_task(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        try:
            return await task_service.cancel_task(task_id, on_update=broadcast_task_update)
        except TaskStateError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.post("/tasks/{task_id}/archive", dependencies=[Depends(require_auth)])
    async def archive_task(task_id: str) -> TaskSummary:
        if projection.get_task(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        try:
            task = projection.archive_task(task_id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        await connections.broadcast_task_updated(task)
        return task

    @app.post("/tasks/{task_id}/restore", dependencies=[Depends(require_auth)])
    async def restore_task(task_id: str) -> TaskSummary:
        if projection.get_task(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        task = projection.restore_task(task_id)
        await connections.broadcast_task_updated(task)
        return task

    @app.post("/tasks/{task_id}/retry", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def retry_task(task_id: str, idempotency_key: str | None = Header(default=None)) -> TaskSummary:
        original = projection.get_task(task_id)
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        _require_recovery_source(original)
        return await submit_linked_task(request_from_task(original), idempotency_key=idempotency_key)

    @app.post("/tasks/{task_id}/continue", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def continue_task(task_id: str, request: GuidanceRequest, idempotency_key: str | None = Header(default=None)) -> TaskSummary:
        original = projection.get_task(task_id)
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if original.session_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task has no Hermes session to continue")
        _require_recovery_source(original)
        if request.new_session or request.relation == "edited_retry":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Use edit-retry or new-session for a new Hermes session")
        task_request = TaskCreateRequest(
            prompt=request.prompt,
            project_id=original.project_id,
            priority=original.priority,
            source=original.source,
            requires_approval=request.requires_approval,
            parent_task_id=original.task_id,
            root_task_id=original.root_task_id or original.task_id,
            session_id=original.session_id,
            relation=request.relation,
        )
        return await submit_linked_task(task_request, idempotency_key=idempotency_key)

    @app.post("/tasks/{task_id}/edit-retry", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def edit_retry_task(task_id: str, request: GuidanceRequest, idempotency_key: str | None = Header(default=None)) -> TaskSummary:
        original = projection.get_task(task_id)
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        _require_recovery_source(original)
        task_request = TaskCreateRequest(
            prompt=request.prompt,
            project_id=original.project_id,
            priority=original.priority,
            source=original.source,
            requires_approval=request.requires_approval,
            parent_task_id=original.task_id,
            root_task_id=original.root_task_id or original.task_id,
            relation="edited_retry",
        )
        return await submit_linked_task(task_request, idempotency_key=idempotency_key)

    @app.post("/tasks/{task_id}/new-session", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def new_session_task(task_id: str, request: NewSessionRequest, idempotency_key: str | None = Header(default=None)) -> TaskSummary:
        original = projection.get_task(task_id)
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        _require_recovery_source(original)
        task_request = TaskCreateRequest(
            prompt=request.prompt or original.prompt,
            project_id=original.project_id,
            priority=original.priority,
            source=original.source,
            requires_approval=request.requires_approval,
            parent_task_id=original.task_id,
            root_task_id=original.root_task_id or original.task_id,
            relation="retry",
        )
        return await submit_linked_task(task_request, idempotency_key=idempotency_key)

    @app.get("/tasks/{task_id}/environment", dependencies=[Depends(require_auth)])
    def check_task_environment(task_id: str) -> dict[str, bool | str | list[str] | None]:
        task = projection.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        issues: list[str] = []
        project_ready = True
        session_ready: bool | None = None
        try:
            resolve_project_context(request_from_task(task))
        except HTTPException as exc:
            project_ready = False
            issues.append(str(exc.detail))
        if task.session_id:
            session_ready = project_ready
        ready = project_ready and executor_ready()
        if not executor_ready():
            issues.append("Hermes executor is not ready")
        return {
            "task_id": task.task_id,
            "ready": ready,
            "project_ready": project_ready,
            "session_ready": session_ready,
            "executor_ready": executor_ready(),
            "issues": issues,
        }

    @app.get("/tasks/{task_id}", dependencies=[Depends(require_auth)])
    def get_task(task_id: str) -> TaskSummary:
        task = projection.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task

    @app.get("/tasks/{task_id}/events", dependencies=[Depends(require_auth)])
    def get_task_events(task_id: str) -> list[TaskEvent]:
        if projection.get_task(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return projection.list_task_events(task_id)

    @app.get("/attention", dependencies=[Depends(require_auth)])
    def list_attention() -> list[TaskSummary]:
        return [task for task in projection.list_tasks() if task.status in {"awaiting_approval", "attention_required", "failed", "blocked"}]

    def recovery_plan_entries() -> list[tuple[dict[str, str], Path | None, ProjectManifest | None]]:
        """Freshly classify discovery results for both review and destructive apply."""
        if managed_workspace is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Managed workspace root is not configured")
        native_workspace = require_workspace()
        entries: list[tuple[dict[str, str], Path | None, ProjectManifest | None]] = []
        slug_counts: dict[str, int] = {}
        for workspace_path, manifest, error in managed_workspace.discover_manifests():
            if error is not None:
                entries.append(({"workspace": str(workspace_path), "status": "blocked", "detail": error}, None, None))
                continue
            assert manifest is not None
            slug_counts[manifest.identity.slug] = slug_counts.get(manifest.identity.slug, 0) + 1
            entry = {"workspace": str(workspace_path), "slug": manifest.identity.slug}
            try:
                repository = managed_workspace.repository_directory(workspace_path, manifest)
            except ValueError as exc:
                entries.append(({**entry, "status": "blocked", "detail": str(exc)}, workspace_path, manifest))
                continue
            registered = native_workspace.get_project(manifest.identity.slug)
            if repository is not None and not repository.is_dir():
                status_name = "missing_repository"
            elif registered and Path(registered.primary_folder or "").resolve() != workspace_path:
                status_name = "conflict"
            else:
                status_name = "already_registered" if registered else "ready"
            entries.append(({**entry, "status": status_name}, workspace_path, manifest))
        return [
            (({**entry, "status": "conflict"} if entry.get("slug") and slug_counts[entry["slug"]] > 1 else entry), path, manifest)
            for entry, path, manifest in entries
        ]

    @app.post("/recovery-plan/apply", dependencies=[Depends(require_auth)])
    def apply_recovery_plan(request: RecoveryApplyRequest) -> dict[str, list[dict[str, str]]]:
        # Do not trust a prior plan: rebuild all classifications immediately before
        # each creation so changed, duplicate, missing, or conflicting descriptors
        # cannot be applied.
        entries = recovery_plan_entries()
        assert managed_workspace is not None
        results = []
        for slug in request.slugs:
            selected = [(entry, path, manifest) for entry, path, manifest in entries if entry.get("slug") == slug and entry["status"] == "ready"]
            if len(selected) != 1:
                results.append({"slug": slug, "status": "blocked"})
                if recovery_audit is not None:
                    recovery_audit.record(slug, "blocked")
                continue
            _, workspace_path, manifest = selected[0]
            assert workspace_path is not None and manifest is not None
            folders = [str(workspace_path)]
            repository = managed_workspace.repository_directory(workspace_path, manifest)
            if repository is not None and repository.is_dir():
                folders.append(str(repository))
            try:
                require_workspace().create_project(ProjectCreateRequest(name=manifest.identity.name, slug=slug, description=manifest.identity.description, folders=folders, primary_folder=str(workspace_path)))
                managed_workspace.write_manifest(workspace_path, manifest.model_copy(update={
                    "lifecycle": manifest.lifecycle.model_copy(update={"native_registration": "registered"})
                }))
                results.append({"slug": slug, "status": "restored"})
                if recovery_audit is not None:
                    recovery_audit.record(slug, "restored")
            except (RuntimeError, ValueError):
                results.append({"slug": slug, "status": "blocked"})
                if recovery_audit is not None:
                    recovery_audit.record(slug, "blocked")
        return {"results": results}

    @app.get("/recovery-audit", dependencies=[Depends(require_auth)])
    def recovery_audit_timeline(slug: str | None = None, limit: int = 100) -> dict[str, list[dict[str, str]]]:
        if recovery_audit is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Recovery audit storage is not configured")
        return {"entries": recovery_audit.list_entries(slug=slug, limit=min(max(limit, 1), 500))}

    @app.get("/work-threads", response_model=list[WorkThreadSummary], dependencies=[Depends(require_auth)])
    def list_work_threads(project_id: str | None = None, include_archived: bool = False) -> list[WorkThreadSummary]:
        return projection.list_work_threads(project_id=project_id, include_archived=include_archived)

    @app.get("/work-threads/{root_task_id}", response_model=WorkThreadSummary, dependencies=[Depends(require_auth)])
    def get_work_thread(root_task_id: str) -> WorkThreadSummary:
        thread = next((thread for thread in projection.list_work_threads(include_archived=True) if thread.root_task_id == root_task_id), None)
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="work thread not found")
        return thread

    @app.get("/recovery-plan", dependencies=[Depends(require_auth)])
    def recovery_plan() -> dict[str, list[dict[str, str]]]:
        return {"entries": [entry for entry, _, _ in recovery_plan_entries()]}

    @app.get("/projects", dependencies=[Depends(require_auth)])
    def list_projects(include_archived: bool = False) -> list[ProjectSummary]:
        if allow_synthetic_projects and workspace is None:
            return projection.list_projects(include_archived=include_archived)
        native_workspace = require_workspace()
        if include_archived:
            archived = native_workspace.list_projects(include_archived=True)
            active = {project.project_id: project for project in projection.list_projects()}
            return [active.get(project.project_id, project) for project in archived]
        return projection.list_projects()

    @app.get("/projects/{project_id}", dependencies=[Depends(require_auth)])
    def get_project(project_id: str) -> ProjectSummary:
        if allow_synthetic_projects and workspace is None:
            project = projection.get_project(project_id, include_archived=True)
            if project is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
            return project
        require_workspace()
        project = projection.get_project(project_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project

    @app.get("/projects/{project_id}/metrics", dependencies=[Depends(require_auth)])
    def project_metrics(project_id: str) -> dict[str, int | str]:
        project = projection.get_project(project_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        tasks = [task for task in projection.list_tasks() if task.project_id == project_id]
        return {
            "project_id": project_id,
            "total": len(tasks),
            "attention": sum(task.status in {"awaiting_approval", "attention_required", "failed", "blocked"} for task in tasks),
            "active": sum(task.status in {"queued", "running", "attention_required"} for task in tasks),
            "completed": sum(task.status == "completed" for task in tasks),
            "failed": sum(task.status in {"failed", "canceled", "rejected"} for task in tasks),
        }

    @app.get("/projects/{project_id}/events", dependencies=[Depends(require_auth)])
    def project_events(project_id: str, limit: int = 100) -> list[TaskEvent]:
        project = projection.get_project(project_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        events = [event for task in projection.list_tasks() if task.project_id == project_id for event in projection.list_task_events(task.task_id)]
        return sorted(events, key=lambda event: event.created_at, reverse=True)[: min(max(limit, 1), 500)]

    @app.get("/projects/{project_id}/files", dependencies=[Depends(require_auth)])
    def project_files(project_id: str, path: str | None = None) -> list[dict[str, str | int]]:
        project = projection.get_project(project_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        entries: list[dict[str, str | int]] = []
        for folder in project.folders:
            root = Path(folder).expanduser().resolve()
            current = (root / path).resolve() if path else root
            if not current.is_relative_to(root) or not current.is_dir():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="path is outside the project folder")
            for child in sorted(current.iterdir(), key=lambda item: item.name.lower()):
                if child.name.startswith("."):
                    continue
                relative = str(child.relative_to(root))
                item: dict[str, str | int] = {"path": relative, "name": child.name, "kind": "directory" if child.is_dir() else "file"}
                if child.is_file():
                    item["size"] = child.stat().st_size
                entries.append(item)
        return entries

    @app.post("/projects", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth)])
    def create_project(request: ProjectCreateRequest) -> ProjectSummary:
        try:
            if request.origin == "workspace":
                if managed_workspace is None:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Managed workspace root is not configured")
                return managed_workspace.create_workspace_project(request)
            if request.origin == "clone":
                if managed_workspace is None:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Managed workspace root is not configured")
                return managed_workspace.create_clone_project(request)
            return require_workspace().create_project(request)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    def synchronize_managed_project(project: ProjectSummary) -> ProjectSummary:
        if managed_workspace is not None:
            managed_workspace.synchronize_project(project)
        return project

    @app.patch("/projects/{project_id}", dependencies=[Depends(require_auth)])
    def update_project(project_id: str, request: ProjectUpdateRequest) -> ProjectSummary:
        try:
            return synchronize_managed_project(require_workspace().update_project(project_id, request))
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/projects/{project_id}/repository", dependencies=[Depends(require_auth)])
    def attach_project_repository(project_id: str, request: RepositoryAttachRequest) -> ProjectSummary:
        if managed_workspace is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Managed workspace root is not configured")
        try:
            return synchronize_managed_project(managed_workspace.attach_repository(project_id, request.repository_url))
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/projects/{project_id}/folders", dependencies=[Depends(require_auth)])
    def add_project_folder(project_id: str, request: FolderRequest) -> ProjectSummary:
        try:
            return synchronize_managed_project(require_workspace().add_folder(project_id, request.path))
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/projects/{project_id}/folders", dependencies=[Depends(require_auth)])
    def remove_project_folder(project_id: str, request: FolderRequest) -> ProjectSummary:
        try:
            return synchronize_managed_project(require_workspace().remove_folder(project_id, request.path))
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/sessions", dependencies=[Depends(require_auth)])
    def list_sessions(project_id: str | None = None, limit: int = 100) -> list[SessionSummary]:
        return require_workspace().list_sessions(project_id=project_id, limit=min(max(limit, 1), 500))

    @app.get("/folders", dependencies=[Depends(require_auth)])
    def list_folders(path: str | None = None) -> list[str]:
        try:
            return require_workspace().list_directories(path)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/agents", dependencies=[Depends(require_auth)])
    def list_agents() -> list[AgentStatus]:
        return projection.list_agents()

    @app.websocket("/ws/events")
    async def event_stream(websocket: WebSocket, token: str | None = None) -> None:
        configured_token = expected_token()
        if configured_token is None or token is None or not secrets.compare_digest(token, configured_token):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await connections.connect(websocket)
        try:
            await connections.send_snapshot(
                websocket,
                tasks=projection.list_tasks(include_archived=True),
                projects=projection.list_projects(),
                agents=projection.list_agents(),
            )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            connections.disconnect(websocket)

    @app.on_event("startup")
    async def resume_persisted_tasks() -> None:
        # The API worker is restartable. Reuse the stable task ID as the bridge
        # request ID so running work reattaches/replays instead of duplicating.
        # Disposable device fixtures disable this explicitly so their seeded
        # queued/running presentation states are not executed by a test server.
        if os.getenv("CONTROL_API_RESUME_TASKS_ON_STARTUP", "1") != "1":
            return
        for task in task_service.resume_after_restart():
            task_service.start_task(
                task,
                request_from_task(task, requires_approval=False),
                on_update=broadcast_task_update,
            )

    return app


app = create_app()
