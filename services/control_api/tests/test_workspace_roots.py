from __future__ import annotations

from services.control_api.workspace import HermesWorkspaceStore


def test_project_roots_uses_the_host_path_separator(monkeypatch, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("CONTROL_API_PROJECT_ROOTS", f"{first};{second}")

    roots = HermesWorkspaceStore().project_roots()

    assert roots == [first.resolve(), second.resolve()]
