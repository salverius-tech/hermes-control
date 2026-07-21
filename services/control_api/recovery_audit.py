from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class RecoveryAuditStore:
    """Append-only audit log for recovery-plan apply results."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS recovery_audit (created_at TEXT NOT NULL, slug TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)")

    def record(self, slug: str, status: str) -> None:
        payload = {"slug": slug, "status": status}
        with self._connect() as connection:
            connection.execute("INSERT INTO recovery_audit VALUES (?, ?, ?, ?)", (datetime.now(timezone.utc).isoformat(), slug, status, json.dumps(payload)))

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)
