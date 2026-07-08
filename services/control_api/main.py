from __future__ import annotations

import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status

from .auth import expected_token, require_auth
from .hermes_client import HermesTaskService
from .models import AgentStatus, ProjectSummary, TaskCreateRequest, TaskEvent, TaskSummary
from .projection import TaskProjection
from .storage import SQLiteTaskStore
from .websocket import ConnectionManager


def create_app() -> FastAPI:
    app = FastAPI(title="Hermes Mobile Control API", version="0.1.0")
    store_path = os.getenv("CONTROL_API_DB_PATH")
    projection = TaskProjection(store=SQLiteTaskStore(store_path)) if store_path else TaskProjection()
    task_service = HermesTaskService(projection=projection)
    connections = ConnectionManager()

    async def broadcast_task_update(task: TaskSummary) -> None:
        await connections.broadcast_task_updated(task)

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/diagnostics", dependencies=[Depends(require_auth)])
    def diagnostics() -> dict[str, str]:
        return {
            "version": "0.1.0",
            "storage": "sqlite" if store_path else "memory",
            "execution_mode": "command" if os.getenv("CONTROL_API_HERMES_COMMAND") else "unconfigured",
            "websocket_path": "/ws/events",
        }

    @app.get("/tasks", dependencies=[Depends(require_auth)])
    def list_tasks() -> list[TaskSummary]:
        return projection.list_tasks()

    @app.post("/tasks", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth)])
    async def create_task(request: TaskCreateRequest) -> TaskSummary:
        task = await task_service.submit_task(request, on_update=broadcast_task_update)
        await connections.broadcast_task_created(task)
        task_service.start_task(task, request, on_update=broadcast_task_update)
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
