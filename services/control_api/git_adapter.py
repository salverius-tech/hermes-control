from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitCloneError(ValueError):
    message: str

    def __str__(self) -> str:
        return self.message


class GitAdapter:
    """Narrow, no-shell Git boundary for managed workspaces."""

    def __init__(self, *, timeout_seconds: int = 300, output_limit: int = 4_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.output_limit = output_limit

    def clone(self, remote_url: str, destination: Path) -> None:
        try:
            completed = subprocess.run(
                ["git", "clone", "--", remote_url, str(destination)],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitCloneError("repository clone failed") from exc
        if completed.returncode:
            detail = completed.stderr.strip().replace("\n", " ")[: self.output_limit]
            raise GitCloneError(f"repository clone failed (exit {completed.returncode}): {detail or 'git error'}")
