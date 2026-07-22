from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def enable_explicit_legacy_synthetic_project_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep legacy task-only fixtures explicit while production defaults to native projects."""
    monkeypatch.setenv("CONTROL_API_ALLOW_SYNTHETIC_PROJECTS", "1")
