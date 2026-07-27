from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from hermes_control_installer import cli
from hermes_control_installer.core import (
    Check,
    CommandResult,
    InstallConfig,
    _api_check,
    _websocket_check,
    api_request,
    changed_components,
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
    restart_services_for_components,
    rollback_install,
    run_command,
    run_test_task,
    rotate_tokens,
    uninstall,
    update_install,
    validate_install_paths,
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
            "User=hermes\\nGroup=hermes\\nWorkingDirectory=/opt/hermes-mobile-control\\nEnvironmentFile=/etc/hermes-mobile-control/control-api.env\\n"
        )

    bridge, api = render_service_units(config)

    assert str(config.install_dir) in bridge
    assert str(config.install_dir) in api
    assert str(config.config_dir / "control-api.env") in bridge
    assert "User=hermes" not in bridge
    assert f"User={config.hermes_user}" in bridge
    assert "/opt/hermes-mobile-control" not in bridge


def test_run_command_sets_target_home_for_privileged_user(monkeypatch):
    observed = {}
    monkeypatch.setattr("hermes_control_installer.core.os.geteuid", lambda: 0)
    monkeypatch.setattr("hermes_control_installer.core.pwd.getpwuid", lambda _: type("User", (), {"pw_name": "root"})())

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("hermes_control_installer.core.subprocess.run", lambda argv, **kwargs: (observed.setdefault("argv", argv), Completed())[1])
    run_command(["hermes", "tools", "list"], user="anvil")

    assert observed["argv"][:4] == ["sudo", "-H", "-u", "anvil"]


def test_validate_install_paths_rejects_same_source_and_destination(config: InstallConfig):
    same = InstallConfig(
        root=config.install_dir,
        hermes_user=config.hermes_user,
        install_dir=config.install_dir,
        config_dir=config.config_dir,
        state_dir=config.state_dir,
    )

    assert validate_install_paths(same) == "source checkout and install directory must be different"


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

    assert result.returncode == 127
    if os.name == "nt":
        assert result.stderr == "[WinError 2] The system cannot find the file specified"
    else:
        assert result.stderr == "[Errno 2] No such file or directory: '/path/that/does/not/exist'"


def test_write_environment_is_atomic_preserves_api_token_and_restricts_mode(config: InstallConfig):
    config.config_dir.mkdir()
    env_path = config.config_dir / "control-api.env"
    env_path.write_text("CONTROL_API_TOKEN=existing-api-token\nCONTROL_API_HERMES_PLUGIN_TOKEN=existing-bridge-token\n")

    api_token, created = write_environment(config)

    assert api_token == "existing-api-token"
    assert created is False
    if os.name != "nt":
        assert env_path.stat().st_mode & 0o777 == 0o640
    assert "existing-bridge-token" in env_path.read_text()


def test_rotate_api_token_preserves_bridge_token_and_restarts_api(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    config.config_dir.mkdir()
    env_path = config.config_dir / "control-api.env"
    env_path.write_text("CONTROL_API_TOKEN=old-api\nCONTROL_API_HERMES_PLUGIN_TOKEN=old-bridge\n")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return CommandResult(0, "active", "") if command[:2] == ["systemctl", "is-active"] else CommandResult(0, "", "")

    monkeypatch.setattr("hermes_control_installer.core.run_command", fake_run)

    assert rotate_tokens(config, scope="api") == 0
    contents = env_path.read_text()
    assert "CONTROL_API_TOKEN=old-api" not in contents
    assert "CONTROL_API_HERMES_PLUGIN_TOKEN=old-bridge" in contents
    assert calls == [["systemctl", "restart", "hermes-mobile-control-api"], ["systemctl", "is-active", "hermes-mobile-control-api"]]


def test_rotate_bridge_token_restarts_bridge_before_api_and_never_prints_bridge(
    monkeypatch: pytest.MonkeyPatch, config: InstallConfig, capsys: pytest.CaptureFixture[str]
):
    config.config_dir.mkdir()
    env_path = config.config_dir / "control-api.env"
    env_path.write_text("CONTROL_API_TOKEN=old-api\nCONTROL_API_HERMES_PLUGIN_TOKEN=old-bridge\n")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return CommandResult(0, "active", "") if command[:2] == ["systemctl", "is-active"] else CommandResult(0, "", "")

    monkeypatch.setattr("hermes_control_installer.core.run_command", fake_run)

    assert rotate_tokens(config, scope="bridge") == 0
    contents = env_path.read_text()
    assert "CONTROL_API_TOKEN=old-api" in contents
    assert "CONTROL_API_HERMES_PLUGIN_TOKEN=old-bridge" not in contents
    assert calls == [
        ["systemctl", "restart", "hermes-control-bridge"],
        ["systemctl", "is-active", "hermes-control-bridge"],
        ["systemctl", "restart", "hermes-mobile-control-api"],
        ["systemctl", "is-active", "hermes-mobile-control-api"],
    ]
    assert "old-bridge" not in capsys.readouterr().out


def test_rotate_token_restores_environment_when_restart_fails(
    monkeypatch: pytest.MonkeyPatch, config: InstallConfig, capsys: pytest.CaptureFixture[str]
):
    config.config_dir.mkdir()
    env_path = config.config_dir / "control-api.env"
    original = b"CONTROL_API_TOKEN=old-api\nCONTROL_API_HERMES_PLUGIN_TOKEN=old-bridge\n"
    env_path.write_bytes(original)

    monkeypatch.setattr(
        "hermes_control_installer.core.run_command",
        lambda command, **kwargs: CommandResult(17, "", "failed") if command[:2] == ["systemctl", "restart"] else CommandResult(0, "", ""),
    )

    assert rotate_tokens(config, scope="api") == 17
    assert env_path.read_bytes() == original
    assert "previous token environment restored" in capsys.readouterr().out


def test_rotate_token_cli_forwards_scope(monkeypatch, config: InstallConfig):
    monkeypatch.setattr(cli, "default_config", lambda *args, **kwargs: config)
    observed = {}

    def fake_rotate(_, *, scope):
        observed["scope"] = scope
        return 0

    monkeypatch.setattr(cli, "rotate_tokens", fake_rotate)

    assert cli.main(["--root", str(config.root), "rotate-token", "--scope", "both"]) == 0
    assert observed == {"scope": "both"}


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


def test_changed_components_maps_runtime_paths(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "hermes_control_installer.core.run_command",
        lambda command: CommandResult(0, "services/control_api/main.py\nservices/hermes_extension/host.py\nREADME.md", ""),
    )

    assert changed_components(tmp_path, "old", "new") == {"api", "bridge"}


def test_restart_services_for_components_orders_bridge_api_and_gateway(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return CommandResult(0, "active", "") if command[:2] == ["systemctl", "is-active"] else CommandResult(0, "", "")

    monkeypatch.setattr("hermes_control_installer.core.run_command", fake_run)

    assert restart_services_for_components({"bridge", "plugin"}) == 0
    assert calls == [
        ["systemctl", "restart", "hermes-control-bridge"],
        ["systemctl", "is-active", "hermes-control-bridge"],
        ["systemctl", "restart", "hermes-mobile-control-api"],
        ["systemctl", "is-active", "hermes-mobile-control-api"],
        ["systemctl", "is-active", "hermes-gateway"],
        ["systemctl", "restart", "hermes-gateway"],
    ]


def test_install_record_keeps_revision_history_and_components(config: InstallConfig):
    from hermes_control_installer.core import write_install_record

    write_install_record(config, "new", previous_revision="old", restarted_components={"api"})

    record = json.loads((config.state_dir / "install-record.json").read_text())
    assert record["revision"] == "new"
    assert record["previous_revision"] == "old"
    assert record["restarted_components"] == ["api"]


def test_rollback_requires_install_record(config: InstallConfig, capsys: pytest.CaptureFixture[str]):
    assert rollback_install(config, "old-ref") == 2
    assert "no install record" in capsys.readouterr().out


def test_rollback_delegates_to_update_and_records_operation(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    config.state_dir.mkdir()
    (config.state_dir / "install-record.json").write_text(json.dumps({"revision": "current"}))
    monkeypatch.setattr("hermes_control_installer.core.git_revision", lambda _: "current")
    update = Mock(return_value=0)
    monkeypatch.setattr("hermes_control_installer.core.update_install", update)

    assert rollback_install(config, "old-ref", dry_run=True) == 0
    update.assert_called_once_with(config, "old-ref", dry_run=True, operation="rollback")


def test_uninstall_requires_confirmation_and_dry_run_is_read_only(config: InstallConfig, capsys: pytest.CaptureFixture[str]):
    config.install_dir.mkdir(parents=True)
    marker = config.install_dir / "keep"
    marker.write_text("data")

    assert uninstall(config) == 2
    assert uninstall(config, dry_run=True) == 0
    assert marker.exists()
    assert "DRY-RUN uninstall" in capsys.readouterr().out


def test_update_failure_after_checkout_restores_previous_revision(monkeypatch: pytest.MonkeyPatch, config: InstallConfig, capsys: pytest.CaptureFixture[str]):
    config.root.joinpath(".git").mkdir()
    config.config_dir.mkdir()
    env = config.config_dir / "control-api.env"
    env.write_text("CONTROL_API_TOKEN=old\\n")
    bridge_unit = config.config_dir / "hermes-control-bridge.service"
    bridge_unit.write_text("User=anvil\\n")
    config.state_dir.mkdir()
    record = config.state_dir / "install-record.json"
    record.write_text('{"operation":"update","revision":"old"}\\n')
    before = {path: path.read_bytes() for path in (env, bridge_unit, record)}
    monkeypatch.setattr("hermes_control_installer.core.git_is_clean", lambda _: True)
    revisions = iter(["old", "new"])
    monkeypatch.setattr("hermes_control_installer.core.git_revision", lambda *args: next(revisions))
    monkeypatch.setattr("hermes_control_installer.core.changed_components", lambda *_: {"api"})
    commands = []

    def fake_run(command):
        commands.append(command)
        return CommandResult(0, "", "")

    monkeypatch.setattr("hermes_control_installer.core.run_command", fake_run)
    monkeypatch.setattr("hermes_control_installer.core.execute_install", Mock(return_value=7))

    assert update_install(config, "reviewed-ref") == 7
    assert any(
        command[:5] == ["git", "-c", f"safe.directory={config.install_dir}", "-C", str(config.install_dir)]
        and command[-3:] == ["checkout", "--detach", "old"]
        for command in commands
    )
    assert {path: path.read_bytes() for path in before} == before
    assert "previous installed revision restored" in capsys.readouterr().out


def test_uninstall_plugin_failure_preserves_resources(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    config.install_dir.mkdir(parents=True)
    config.state_dir.mkdir(parents=True)
    marker = config.install_dir / "keep"
    marker.write_text("data")
    state_marker = config.state_dir / "state"
    state_marker.write_text("data")
    monkeypatch.setattr("hermes_control_installer.core.os.geteuid", lambda: 0)

    def fake_run(command, **kwargs):
        if command[:3] == ["hermes", "plugins", "uninstall"]:
            return CommandResult(1, "", "plugin unavailable")
        return CommandResult(0, "", "")

    monkeypatch.setattr("hermes_control_installer.core.run_command", fake_run)

    assert uninstall(config, confirmed=True, purge_state=True) == 1
    assert marker.exists()
    assert state_marker.exists()


def test_uninstall_is_retryable_after_transient_plugin_failure(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    monkeypatch.setattr("hermes_control_installer.core.os.geteuid", lambda: 0)
    removed = []
    monkeypatch.setattr("hermes_control_installer.core._remove_path", removed.append)
    attempts = iter([1, 0])

    def fake_run(command, **kwargs):
        if command[:3] == ["hermes", "plugins", "uninstall"]:
            return CommandResult(next(attempts), "", "plugin unavailable")
        return CommandResult(0, "", "")

    monkeypatch.setattr("hermes_control_installer.core.run_command", fake_run)

    assert uninstall(config, confirmed=True) == 1
    assert removed == []
    assert uninstall(config, confirmed=True) == 0
    assert len(removed) == 3


def test_update_records_previous_revision_and_selected_restarts(monkeypatch: pytest.MonkeyPatch, config: InstallConfig):
    config.root.joinpath(".git").mkdir()
    monkeypatch.setattr("hermes_control_installer.core.git_is_clean", lambda _: True)
    revisions = iter(["old", "new"])
    monkeypatch.setattr("hermes_control_installer.core.git_revision", lambda *args: next(revisions))
    monkeypatch.setattr("hermes_control_installer.core.changed_components", lambda *_: {"api"})
    monkeypatch.setattr("hermes_control_installer.core.run_command", lambda command: CommandResult(0, "", ""))
    execute = Mock(return_value=0)
    restart = Mock(return_value=0)
    record = Mock()
    monkeypatch.setattr("hermes_control_installer.core.execute_install", execute)
    monkeypatch.setattr("hermes_control_installer.core.restart_services_for_components", restart)
    monkeypatch.setattr("hermes_control_installer.core.write_install_record", record)

    assert update_install(config, "reviewed-ref") == 0
    execute.assert_called_once()
    staged_config = execute.call_args.args[0]
    assert staged_config.root != config.root
    assert staged_config.root.name.startswith(".hermes-control-revision-")
    assert staged_config.install_dir == config.install_dir
    assert execute.call_args.kwargs == {
        "restart_components": {"api"},
        "start_services": False,
        "write_record": False,
        "preserve_existing": True,
    }
    restart.assert_called_once_with({"api"})
    record.assert_called_once_with(config, "new", previous_revision="old", restarted_components={"api"}, operation="update")


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
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr("hermes_control_installer.core.preflight", lambda _: [Check("Repository", "PASS", "ok")])
    monkeypatch.setattr("hermes_control_installer.core.write_environment", lambda _: ("api", True))
    monkeypatch.setattr("hermes_control_installer.core.write_service_units", lambda _: None)
    monkeypatch.setattr("hermes_control_installer.core.install_commands", lambda _, **kwargs: [["first"], ["second"]])
    calls = []

    def fail_first(command, **kwargs):
        calls.append(command)
        return CommandResult(17, "", "failed")

    monkeypatch.setattr("hermes_control_installer.core.run_command", fail_first)

    assert execute_install(config) == 17
    assert calls == [["first"]]
