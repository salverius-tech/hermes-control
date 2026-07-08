from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol

from .models import TaskSummary


class TaskStore(Protocol):
    def load_tasks(self) -> list[TaskSummary]: ...

    def save_task(self, task: TaskSummary) -> None: ...


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
