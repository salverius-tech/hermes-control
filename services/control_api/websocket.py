from __future__ import annotations

from fastapi import WebSocket

from .models import AgentStatus, ProjectSummary, TaskSummary


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._sequence = 0

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def send_snapshot(
        self,
        websocket: WebSocket,
        *,
        tasks: list[TaskSummary],
        projects: list[ProjectSummary],
        agents: list[AgentStatus],
    ) -> None:
        await websocket.send_json(
            {
                "type": "snapshot",
                "seq": self._sequence,
                "tasks": [task.model_dump(mode="json") for task in tasks],
                "projects": [project.model_dump(mode="json") for project in projects],
                "agents": [agent.model_dump(mode="json") for agent in agents],
            }
        )

    async def broadcast_task_created(self, task: TaskSummary) -> None:
        await self.broadcast({"type": "task.created", "task": task.model_dump(mode="json")})

    async def broadcast_task_updated(self, task: TaskSummary) -> None:
        await self.broadcast({"type": "task.updated", "task": task.model_dump(mode="json")})

    async def broadcast(self, message: dict) -> None:
        self._sequence += 1
        message = {**message, "seq": self._sequence}
        stale: list[WebSocket] = []
        for websocket in list(self._connections):
            try:
                await websocket.send_json(message)
            except RuntimeError:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)
