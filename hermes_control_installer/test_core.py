from __future__ import annotations

import os
import pwd
from pathlib import Path

import pytest

from hermes_control_installer.core import (
    Check,
    InstallConfig,
    default_config,
    format_checks,
    install_commands,
    plugin_install_command,
    preflight,
    render_environment,
    render_install_plan,
    render_service_units,
    run_test_task,
    _websocket_check,
)


pytestmark = pytest.mark.unit


@pytest.fixture
def config(tmp_path: Path) -> InstallConfig:
    return InstallConfig(
        root=tmp_path,
        hermes_user=pwd.getpwuid(os.getuid()).pw_name,
        install_dir=tmp_path / "install",
        config_dir=tmp_path / "etc",
        state_dir=tmp_path / "state",
        hostname="https://control.example.test",
    )


def test_render_environment_separates_api_and_bridge_tokens(config: InstallConfig):
    rendered = render_environment(config, api_token="api-secret", bridge_token="bridge-secret")

    assert "CONTROL_API_TOKEN=api-secret" in rendered
    assert "CONTROL_API_HERMES_PLUGIN_TOKEN=bridge-secret" in rendered
    assert "HERMES_CONTROL_EXTENSION_TOKEN=bridge-secret" in rendered
    assert "CONTROL_API_REQUIRE_TASK_APPROVAL=1" in rendered


def test_install_plan_includes_units_and_plugin(config: InstallConfig):
    plan = render_install_plan(config)

    assert "hermes plugins install" in plan
    assert "hermes-control-bridge.service" in plan
    assert "hermes-mobile-control-api.service" in plan
    assert "api-secret" not in plan


def test_plugin_install_uses_reviewed_installed_checkout(config: InstallConfig):
    command = plugin_install_command(config)

    assert command == ["hermes", "plugins", "install", f"file://{config.install_dir}", "--force", "--enable"]


def test_preflight_reports_missing_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("hermes_control_installer.core.shutil.which", lambda name: "/usr/bin/" + name)
    config = InstallConfig(
        root=tmp_path,
        hermes_user="missing-user",
        install_dir=tmp_path / "install",
        config_dir=tmp_path / "etc",
        state_dir=tmp_path / "state",
    )

    checks = preflight(config)

    assert any(check.name == "Repository" and check.status == "FAIL" for check in checks)
    assert any(check.name == "Hermes service user" and check.status == "FAIL" for check in checks)


def test_render_service_units_use_selected_paths(config: InstallConfig):
    config.root.joinpath("deploy").mkdir()
    for name in ("hermes-control-bridge.service", "hermes-mobile-control-api.service"):
        config.root.joinpath("deploy", name).write_text(
            "WorkingDirectory=/opt/hermes-mobile-control\\nEnvironmentFile=/etc/hermes-mobile-control/control-api.env\\n"
        )

    bridge, api = render_service_units(config)

    assert str(config.install_dir) in bridge
    assert str(config.install_dir) in api
    assert str(config.config_dir / "control-api.env") in bridge
    assert "/opt/hermes-mobile-control" not in bridge


def test_run_test_task_fails_without_token(config: InstallConfig):
    assert run_test_task(config) == Check("Harmless task", "FAIL", "CONTROL_API_TOKEN is not configured")


def test_websocket_check_requires_token(config: InstallConfig):
    assert _websocket_check(config) == Check("Control API WebSocket", "FAIL", "CONTROL_API_TOKEN is not configured")


def test_format_checks_is_operator_readable():
    assert format_checks([Check("API", "PASS", "healthy")]) == "PASS  API: healthy"


def test_default_config_uses_explicit_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HERMES_CONTROL_INSTALL_DIR", str(tmp_path / "install"))
    monkeypatch.setenv("HERMES_CONTROL_CONFIG_DIR", str(tmp_path / "etc"))
    monkeypatch.setenv("HERMES_CONTROL_STATE_DIR", str(tmp_path / "state"))

    config = default_config(tmp_path, hermes_user="hermes")

    assert config.root == tmp_path
    assert config.install_dir == tmp_path / "install"
    assert config.config_dir == tmp_path / "etc"
    assert config.state_dir == tmp_path / "state"
