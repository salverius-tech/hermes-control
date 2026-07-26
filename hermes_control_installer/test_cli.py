from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_control_installer import cli
from hermes_control_installer.core import Check, InstallConfig


pytestmark = pytest.mark.unit


def config(tmp_path: Path) -> InstallConfig:
    return InstallConfig(
        root=tmp_path,
        hermes_user="hermes",
        install_dir=tmp_path / "install",
        config_dir=tmp_path / "etc",
        state_dir=tmp_path / "state",
    )


def test_preflight_json_output_and_success_exit(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(cli, "default_config", lambda *args, **kwargs: config(tmp_path))
    monkeypatch.setattr(cli, "preflight", lambda _: [Check("Repository", "PASS", "ok")])

    result = cli.main(["--root", str(tmp_path), "--json", "preflight"])

    assert result == 0
    assert json.loads(capsys.readouterr().out) == [{"detail": "ok", "name": "Repository", "status": "PASS"}]


def test_install_dry_run_returns_failure_without_execute(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(cli, "default_config", lambda *args, **kwargs: config(tmp_path))
    monkeypatch.setattr(cli, "preflight", lambda _: [Check("Repository", "FAIL", "missing")])
    execute = lambda _: (_ for _ in ()).throw(AssertionError("execute_install must not run"))
    monkeypatch.setattr(cli, "execute_install", execute)
    monkeypatch.setattr(cli, "render_install_plan", lambda _: "PLAN")

    result = cli.main(["--root", str(tmp_path), "install", "--dry-run"])

    assert result == 2
    assert "FAIL  Repository: missing" in capsys.readouterr().out


def test_doctor_forwards_execute_probe(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli, "default_config", lambda *args, **kwargs: config(tmp_path))
    observed = {}

    def fake_doctor(_, *, execute_test_task):
        observed["execute_test_task"] = execute_test_task
        return [Check("Doctor", "PASS", "ok")]

    monkeypatch.setattr(cli, "doctor", fake_doctor)

    assert cli.main(["--root", str(tmp_path), "doctor", "--execute-test-task"]) == 0
    assert observed == {"execute_test_task": True}


def test_update_forwards_ref_and_dry_run(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli, "default_config", lambda *args, **kwargs: config(tmp_path))
    observed = {}

    def fake_update(_, ref, *, dry_run):
        observed.update(ref=ref, dry_run=dry_run)
        return 0

    monkeypatch.setattr(cli, "update_install", fake_update)

    assert cli.main(["--root", str(tmp_path), "update", "--ref", "abc123", "--dry-run"]) == 0
    assert observed == {"ref": "abc123", "dry_run": True}
