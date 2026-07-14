from __future__ import annotations

import os
import secrets
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status

from .auth import expected_token, require_auth
from .hermes_client import HermesTaskService
from .models import (
    AgentStatus,
    FolderRequest,
    GuidanceRequest,
    ProjectCreateRequest,
    ProjectSummary,
    ProjectUpdateRequest,
    SessionSummary,
    TaskCreateRequest,
    TaskEvent,
    TaskSummary,
)
from .notifications import notifier_from_environment
from .projection import TaskProjection
from .rate_limit import RateLimiter
from .storage import SQLiteTaskStore
from .websocket import ConnectionManager
from .workspace import HermesWorkspaceStore


def create_app() -> FastAPI:
    app = FastAPI(title="Hermes Mobile Control API", version="0.1.0")
    store_path = os.getenv("CONTROL_API_DB_PATH")
    store = SQLiteTaskStore(store_path) if store_path else None
    workspace = HermesWorkspaceStore(os.getenv("CONTROL_API_HERMES_HOME", "~/.hermes"))
    projection = TaskProjection(store=store, workspace=workspace if os.getenv("CONTROL_API_HERMES_HOME") else None)
    task_service = HermesTaskService(
        projection=projection,
        notifier=notifier_from_environment(),
        max_concurrent_tasks=int(os.getenv("CONTROL_API_MAX_CONCURRENT_TASKS", "4")),
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

    def resolve_project_context(request: TaskCreateRequest) -> TaskCreateRequest:
        if not os.getenv("CONTROL_API_HERMES_HOME") or request.execution_folder:
            return request
        project = workspace.get_project(request.project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown Hermes project: {request.project_id}")
        if not project.primary_folder:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Project has no primary folder: {request.project_id}")
        return request.model_copy(update={"execution_folder": project.primary_folder})

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/diagnostics", dependencies=[Depends(require_auth)])
    def diagnostics() -> dict[str, str]:
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
            "hermes_home": str(workspace.hermes_home),
            "hermes_home_available": str(workspace.available).lower(),
        }

    @app.get("/tasks", dependencies=[Depends(require_auth)])
    def list_tasks() -> list[TaskSummary]:
        return projection.list_tasks()

    @app.post("/tasks", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def create_task(request: TaskCreateRequest) -> TaskSummary:
        request = resolve_project_context(request)
        task = await task_service.submit_task(request, on_update=broadcast_task_update)
        await connections.broadcast_task_created(task)
        if not request.requires_approval:
            task_service.start_task(task, request, on_update=broadcast_task_update)
        return task

    @app.post("/tasks/{task_id}/approve", dependencies=[Depends(require_auth)])
    async def approve_task(task_id: str) -> TaskSummary:
        original = projection.get_task(task_id)
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        task = projection.approve_task(task_id)
        await connections.broadcast_task_updated(task)
        task_service.start_task(task, request_from_task(task, requires_approval=False), on_update=broadcast_task_update)
        return task

    @app.post("/tasks/{task_id}/reject", dependencies=[Depends(require_auth)])
    async def reject_task(task_id: str) -> TaskSummary:
        if projection.get_task(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        task = projection.reject_task(task_id)
        await task_service.notify_task(task, event_type="task.rejected")
        await connections.broadcast_task_updated(task)
        return task

    @app.post("/tasks/{task_id}/cancel", dependencies=[Depends(require_auth)])
    async def cancel_task(task_id: str) -> TaskSummary:
        if projection.get_task(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return await task_service.cancel_task(task_id, on_update=broadcast_task_update)

    @app.post("/tasks/{task_id}/retry", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def retry_task(task_id: str) -> TaskSummary:
        original = projection.get_task(task_id)
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        request = request_from_task(original)
        request = resolve_project_context(request)
        task = await task_service.submit_task(request, on_update=broadcast_task_update)
        await connections.broadcast_task_created(task)
        if not request.requires_approval:
            task_service.start_task(task, request, on_update=broadcast_task_update)
        return task

    @app.post("/tasks/{task_id}/continue", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth), Depends(enforce_task_rate_limit)])
    async def continue_task(task_id: str, request: GuidanceRequest) -> TaskSummary:
        original = projection.get_task(task_id)
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        task_request = TaskCreateRequest(
            prompt=request.prompt,
            project_id=original.project_id,
            priority=original.priority,
            source=original.source,
            requires_approval=request.requires_approval,
            parent_task_id=original.task_id,
            root_task_id=original.root_task_id or original.task_id,
            session_id=None if request.new_session else original.session_id,
            relation="follow_up" if request.new_session else "continuation",
        )
        task_request = resolve_project_context(task_request)
        task = await task_service.submit_task(task_request, on_update=broadcast_task_update)
        await connections.broadcast_task_created(task)
        if not task_request.requires_approval:
            task_service.start_task(task, task_request, on_update=broadcast_task_update)
        return task

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

    @app.get("/projects", dependencies=[Depends(require_auth)])
    def list_projects() -> list[ProjectSummary]:
        return projection.list_projects()

    @app.get("/projects/{project_id}", dependencies=[Depends(require_auth)])
    def get_project(project_id: str) -> ProjectSummary:
        project = workspace.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project

    @app.post("/projects", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth)])
    def create_project(request: ProjectCreateRequest) -> ProjectSummary:
        try:
            return workspace.create_project(request)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.patch("/projects/{project_id}", dependencies=[Depends(require_auth)])
    def update_project(project_id: str, request: ProjectUpdateRequest) -> ProjectSummary:
        try:
            return workspace.update_project(project_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/projects/{project_id}/folders", dependencies=[Depends(require_auth)])
    def add_project_folder(project_id: str, request: FolderRequest) -> ProjectSummary:
        try:
            return workspace.add_folder(project_id, request.path)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/projects/{project_id}/folders", dependencies=[Depends(require_auth)])
    def remove_project_folder(project_id: str, request: FolderRequest) -> ProjectSummary:
        try:
            return workspace.remove_folder(project_id, request.path)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/sessions", dependencies=[Depends(require_auth)])
    def list_sessions(project_id: str | None = None, limit: int = 100) -> list[SessionSummary]:
        return workspace.list_sessions(project_id=project_id, limit=min(max(limit, 1), 500))

    @app.get("/folders", dependencies=[Depends(require_auth)])
    def list_folders(path: str | None = None) -> list[str]:
        try:
            return workspace.list_directories(path)
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
                tasks=projection.list_tasks(),
                projects=projection.list_projects(),
                agents=projection.list_agents(),
            )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            connections.disconnect(websocket)

    return app


app = create_app()
