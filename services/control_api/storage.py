from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol

from .models import TaskEvent, TaskSummary


class TaskStore(Protocol):
    def load_tasks(self) -> list[TaskSummary]: ...

    def save_task(self, task: TaskSummary) -> None: ...

    def load_events(self) -> list[TaskEvent]: ...

    def save_event(self, event: TaskEvent) -> None: ...


class SQLiteTaskStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def load_tasks(self) -> list[TaskSummary]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM tasks ORDER BY created_at DESC").fetchall()
        return [TaskSummary.model_validate(json.loads(row[0])) for row in rows]

    def save_task(self, task: TaskSummary) -> None:
        payload = task.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (task_id, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    task.task_id,
                    payload["created_at"],
                    payload["updated_at"],
                    json.dumps(payload, separators=(",", ":")),
                ),
            )

    def load_events(self) -> list[TaskEvent]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM task_events ORDER BY created_at ASC").fetchall()
        return [TaskEvent.model_validate(json.loads(row[0])) for row in rows]

    def save_event(self, event: TaskEvent) -> None:
        payload = event.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_events (task_id, event_type, created_at, payload)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event.task_id,
                    event.event_type,
                    payload["created_at"],
                    json.dumps(payload, separators=(",", ":")),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id)")
