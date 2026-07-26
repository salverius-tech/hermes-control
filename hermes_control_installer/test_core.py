from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from hermes_control_installer.core import (
    Check,
    CommandResult,
    InstallConfig,
    _api_check,
    _websocket_check,
    api_request,
    default_config,
    doctor,
    execute_install,
    format_checks,
    install_commands,
    plugin_install_command,
    preflight,
    render_environment,
    render_install_plan,
    render_service_units,
    run_command,
    run_test_task,
    update_install,
    write_environment,
)


pytestmark = pytest.mark.unit


@pytest.fixture
def config(tmp_path: Path) -> InstallConfig:
    return InstallConfig(
        root=tmp_path,
        hermes_user=getpass.getuser(),
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


def test_run_command_returns_sanitized_os_failure():
    result = run_command(["/path/that/does/not/exist"])

    assert result == CommandResult(127, "", "[Errno 2] No such file or directory: '/path/that/does/not/exist'")


def test_write_environment_is_atomic_preserves_api_token_and_restricts_mode(config: InstallConfig):
    config.config_dir.mkdir()
    env_path = config.config_dir / "control-api.env"
    env_path.write_text("CONTROL_API_TOKEN=existing-api-token\nCONTROL_API_HERMES_PLUGIN_TOKEN=existing-bridge-token\n")

    api_token, created = write_environment(config)

    assert api_token == "existing-api-token"
    assert created is False
    assert env_path.stat().st_mode & 0o777 == 0o640
    assert "existing-bridge-token" in env_path.read_text()


def test_api_request_encodes_authenticated_json(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    env_path = config.config_dir / "control-api.env"
    config.config_dir.mkdir()
    env_path.write_text("CONTROL_API_TOKEN=test-token\n")
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps({"ok": True}).encode()
    opener = Mock(return_value=response)
    monkeypatch.setattr("hermes_control_installer.core.urlopen", opener)

    payload = api_request(config, "/tasks", method="POST", body={"prompt": "safe"})

    assert payload == {"ok": True}
    request = opener.call_args.args[0]
    assert request.full_url == "https://control.example.test/tasks"
    assert request.get_header("Authorization") == "Bearer test-token"
    assert json.loads(request.data) == {"prompt": "safe"}


def test_api_check_sanitizes_network_error(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    monkeypatch.setattr("hermes_control_installer.core.api_request", Mock(side_effect=OSError("secret detail")))

    check = _api_check(config, "/health", "Control API health")

    assert check == Check("Control API health", "FAIL", "OSError")
    assert "secret detail" not in check.detail


def test_doctor_reports_services_and_authenticated_readiness(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    monkeypatch.setattr("hermes_control_installer.core.preflight", lambda _: [Check("Repository", "PASS", "ok")])
    monkeypatch.setattr(
        "hermes_control_installer.core.run_command",
        lambda command, **kwargs: CommandResult(0, "active", "") if command[:2] == ["systemctl", "is-active"] else CommandResult(0, "", ""),
    )
    monkeypatch.setattr("hermes_control_installer.core._api_token", lambda _: "test-token")
    monkeypatch.setattr("hermes_control_installer.core._api_check", lambda _, path, name: Check(name, "PASS", "reachable"))
    monkeypatch.setattr("hermes_control_installer.core._websocket_check", lambda _: Check("Control API WebSocket", "PASS", "snapshot"))

    checks = doctor(config)

    assert {check.name for check in checks} == {
        "Repository",
        "hermes-control-bridge service",
        "hermes-mobile-control-api service",
        "Control API health",
        "Control API authentication",
        "Native project discovery",
        "Control API WebSocket",
    }
    assert all(check.status == "PASS" for check in checks)


def test_run_test_task_creates_approves_and_waits_for_completion(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    monkeypatch.setattr("hermes_control_installer.core._api_token", lambda _: "test-token")
    requests = []

    def fake_request(_, path, *, method="GET", body=None):
        requests.append((path, method, body))
        if path == "/projects":
            return [{"project_id": "project-one", "archived": False}]
        if path == "/tasks":
            return {"task_id": "task-one"}
        if path == "/tasks/task-one":
            return {"status": "completed"}
        return {}

    monkeypatch.setattr("hermes_control_installer.core.api_request", fake_request)
    monkeypatch.setattr("hermes_control_installer.core.time.sleep", lambda _: None)

    check = run_test_task(config)

    assert check == Check("Harmless task", "PASS", "MOBILE-DEVICE-READY completed")
    assert requests[1][0:2] == ("/tasks", "POST")
    assert requests[2][0:2] == ("/tasks/task-one/approve", "POST")


def test_update_rejects_dirty_checkout_without_mutation(monkeypatch: pytest.MonkeyPatch, config: InstallConfig, capsys: pytest.CaptureFixture[str]):
    config.root.joinpath(".git").mkdir()
    monkeypatch.setattr("hermes_control_installer.core.git_is_clean", lambda _: False)
    execute = Mock(return_value=0)
    monkeypatch.setattr("hermes_control_installer.core.execute_install", execute)

    result = update_install(config, "deadbeef")

    assert result == 2
    execute.assert_not_called()
    assert "uncommitted changes" in capsys.readouterr().out


def test_execute_install_stops_on_first_failed_command(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    monkeypatch.setattr("hermes_control_installer.core.preflight", lambda _: [Check("Repository", "PASS", "ok")])
    monkeypatch.setattr("hermes_control_installer.core.os.geteuid", lambda: 0)
    monkeypatch.setattr("hermes_control_installer.core.write_environment", lambda _: ("api", True))
    monkeypatch.setattr("hermes_control_installer.core.write_service_units", lambda _: None)
    monkeypatch.setattr("hermes_control_installer.core.install_commands", lambda _: [["first"], ["second"]])
    calls = []

    def fail_first(command, **kwargs):
        calls.append(command)
        return CommandResult(17, "", "failed")

    monkeypatch.setattr("hermes_control_installer.core.run_command", fail_first)

    assert execute_install(config) == 17
    assert calls == [["first"]]
