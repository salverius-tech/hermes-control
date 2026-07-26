from __future__ import annotations

import os
import pwd
import secrets
import shutil
import subprocess
import tempfile
import time
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class InstallConfig:
    root: Path
    hermes_user: str
    install_dir: Path
    config_dir: Path
    state_dir: Path
    api_port: int = 8787
    hostname: str | None = None
    configure_caddy: bool = False
    require_approval: bool = True


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(command: Sequence[str], *, user: str | None = None) -> CommandResult:
    argv = list(command)
    if user and os.geteuid() == 0 and user != pwd.getpwuid(os.getuid()).pw_name:
        argv = ["sudo", "-u", user, *argv]
    try:
        completed = subprocess.run(argv, text=True, capture_output=True, check=False)
    except OSError as exc:
        return CommandResult(127, "", str(exc))
    return CommandResult(completed.returncode, completed.stdout.strip(), completed.stderr.strip())


def git_revision(root: Path, ref: str = "HEAD") -> str | None:
    result = run_command(["git", "-C", str(root), "rev-parse", "--verify", f"{ref}^{{commit}}"])
    return result.stdout if result.returncode == 0 and result.stdout else None


def git_is_clean(root: Path) -> bool:
    result = run_command(["git", "-C", str(root), "status", "--porcelain"])
    return result.returncode == 0 and not result.stdout


def write_install_record(config: InstallConfig, revision: str) -> None:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    record = {"revision": revision, "install_dir": str(config.install_dir), "require_approval": config.require_approval}
    path = config.state_dir / "install-record.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
    path.chmod(0o640)


def update_install(config: InstallConfig, ref: str, *, dry_run: bool = False) -> int:
    if not (config.root / ".git").exists():
        print("FAIL update: root is not a Git checkout")
        return 2
    if not git_is_clean(config.root):
        print("FAIL update: checkout has uncommitted changes")
        return 2
    current = git_revision(config.root)
    target = git_revision(config.root, ref)
    if target is None:
        fetched = run_command(["git", "-C", str(config.root), "fetch", "--ff-only", "origin", ref])
        if fetched.returncode:
            print("FAIL update: reviewed ref is unavailable")
            return 2
        target = git_revision(config.root, ref)
    if target is None:
        print("FAIL update: ref does not resolve to a commit")
        return 2
    print(f"Current revision: {current or 'unknown'}")
    print(f"Target revision: {target}")
    if dry_run:
        print("DRY-RUN update: no checkout or service mutation performed")
        return 0
    checkout = run_command(["git", "-C", str(config.root), "checkout", "--detach", target])
    if checkout.returncode:
        print("FAIL update: could not checkout reviewed revision")
        return checkout.returncode
    result = execute_install(config)
    if result == 0:
        write_install_record(config, target)
    return result


def detect_hermes_user() -> str | None:
    configured = os.getenv("HERMES_CONTROL_USER")
    candidates = [configured] if configured else []
    candidates.extend(["hermes", pwd.getpwuid(os.getuid()).pw_name])
    for candidate in dict.fromkeys(item for item in candidates if item):
        try:
            pwd.getpwnam(candidate)
        except KeyError:
            continue
        if run_command(["hermes", "status"], user=candidate).returncode == 0:
            return candidate
    return None


def default_config(root: Path, *, hermes_user: str | None = None, hostname: str | None = None) -> InstallConfig:
    user = hermes_user or detect_hermes_user() or pwd.getpwuid(os.getuid()).pw_name
    return InstallConfig(
        root=root,
        hermes_user=user,
        install_dir=Path(os.getenv("HERMES_CONTROL_INSTALL_DIR", "/opt/hermes-mobile-control")),
        config_dir=Path(os.getenv("HERMES_CONTROL_CONFIG_DIR", "/etc/hermes-mobile-control")),
        state_dir=Path(os.getenv("HERMES_CONTROL_STATE_DIR", "/var/lib/hermes-mobile-control")),
        hostname=hostname,
    )


def preflight(config: InstallConfig) -> list[Check]:
    checks: list[Check] = []
    hermes = shutil.which("hermes")
    checks.append(Check("Hermes executable", "PASS" if hermes else "FAIL", hermes or "not found on PATH"))
    try:
        pwd.getpwnam(config.hermes_user)
    except KeyError:
        checks.append(Check("Hermes service user", "FAIL", f"user {config.hermes_user!r} does not exist"))
    else:
        checks.append(Check("Hermes service user", "PASS", config.hermes_user))
    python = shutil.which("python3") or shutil.which("python")
    checks.append(Check("Python", "PASS" if python else "FAIL", python or "not found"))
    checks.append(Check("Git", "PASS" if shutil.which("git") else "FAIL", shutil.which("git") or "not found"))
    checks.append(Check("systemd", "PASS" if shutil.which("systemctl") else "FAIL", shutil.which("systemctl") or "not found"))
    if config.configure_caddy:
        caddy = shutil.which("caddy")
        checks.append(Check("Caddy", "PASS" if caddy else "FAIL", caddy or "required by --configure-caddy"))
    if config.root.joinpath("requirements.txt").exists():
        checks.append(Check("Repository", "PASS", str(config.root)))
    else:
        checks.append(Check("Repository", "FAIL", f"requirements.txt missing under {config.root}"))
    return checks


def format_checks(checks: list[Check]) -> str:
    return "\n".join(f"{check.status:<5} {check.name}: {check.detail}" for check in checks)


def preflight_ok(checks: list[Check]) -> bool:
    return not any(check.status == "FAIL" for check in checks)


def install_commands(config: InstallConfig) -> list[list[str]]:
    source = config.root
    return [
        ["install", "-d", "-o", "root", "-g", config.hermes_user, "-m", "0750", str(config.config_dir)],
        ["install", "-d", "-o", config.hermes_user, "-g", config.hermes_user, "-m", "0750", str(config.state_dir)],
        ["install", "-d", "-o", config.hermes_user, "-g", config.hermes_user, "-m", "0750", str(config.install_dir)],
        ["cp", "-a", f"{source}/.", str(config.install_dir)],
        ["python3", "-m", "venv", str(config.install_dir / ".venv")],
        [str(config.install_dir / ".venv" / "bin" / "python"), "-m", "pip", "install", "-r", str(config.install_dir / "requirements.txt")],
        [str(config.install_dir / ".venv" / "bin" / "python"), "-m", "pip", "install", "-e", str(config.install_dir)],
        ["install", "-o", "root", "-g", "root", "-m", "0644", str(config.config_dir / "hermes-control-bridge.service"), "/etc/systemd/system/hermes-control-bridge.service"],
        ["install", "-o", "root", "-g", "root", "-m", "0644", str(config.config_dir / "hermes-mobile-control-api.service"), "/etc/systemd/system/hermes-mobile-control-api.service"],
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "hermes-control-bridge"],
        ["systemctl", "enable", "--now", "hermes-mobile-control-api"],
    ]


def _env_path(config: InstallConfig) -> Path:
    return config.config_dir / "control-api.env"


def _existing_env_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    prefix = f"{name}="
    for line in path.read_text().splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"') or None
    return None


def render_environment(config: InstallConfig, *, api_token: str, bridge_token: str) -> str:
    hermes_home = pwd.getpwnam(config.hermes_user).pw_dir
    return "\n".join(
        [
            f"CONTROL_API_TOKEN={api_token}",
            f"CONTROL_API_DB_PATH={config.state_dir / 'control-api.db'}",
            f"CONTROL_API_HERMES_HOME={hermes_home}/.hermes",
            f"CONTROL_API_WORKSPACE_ROOT={hermes_home}/.hermes/workspaces",
            f"CONTROL_API_PROJECT_ROOTS={hermes_home}/repos",
            "CONTROL_API_MAX_CONCURRENT_TASKS=4",
            "CONTROL_API_TASK_STALL_SECONDS=600",
            "CONTROL_API_RATE_LIMIT_PER_MINUTE=60",
            f"CONTROL_API_REQUIRE_TASK_APPROVAL={1 if config.require_approval else 0}",
            "CONTROL_API_HERMES_PLUGIN_SOCKET=/run/hermes/control-extension.sock",
            f"CONTROL_API_HERMES_PLUGIN_TOKEN={bridge_token}",
            "HERMES_CONTROL_EXTENSION_SOCKET=/run/hermes/control-extension.sock",
            f"HERMES_CONTROL_EXTENSION_TOKEN={bridge_token}",
            "HERMES_CONTROL_EXTENSION_MAX_CONCURRENT_TASKS=4",
            "HERMES_CONTROL_EXTENSION_HEARTBEAT_SECONDS=15",
            "",
        ]
    )


def write_environment(config: InstallConfig) -> tuple[str, bool]:
    path = _env_path(config)
    api_token = _existing_env_value(path, "CONTROL_API_TOKEN")
    bridge_token = _existing_env_value(path, "CONTROL_API_HERMES_PLUGIN_TOKEN")
    created_api_token = api_token is None
    api_token = api_token or secrets.token_urlsafe(48)
    bridge_token = bridge_token or secrets.token_urlsafe(48)
    config.config_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=config.config_dir, delete=False) as temporary:
        temporary.write(render_environment(config, api_token=api_token, bridge_token=bridge_token))
        temporary.flush()
        os.fchmod(temporary.fileno(), 0o640)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)
    try:
        hermes_gid = pwd.getpwnam(config.hermes_user).pw_gid
        os.chown(path, 0, hermes_gid)
    except (KeyError, PermissionError):
        pass
    return api_token, created_api_token


def render_service_units(config: InstallConfig) -> tuple[str, str]:
    substitutions = {
        "/opt/hermes-mobile-control": str(config.install_dir),
        "/etc/hermes-mobile-control/control-api.env": str(_env_path(config)),
    }
    rendered: list[str] = []
    for filename in ("hermes-control-bridge.service", "hermes-mobile-control-api.service"):
        content = (config.root / "deploy" / filename).read_text()
        for source, target in substitutions.items():
            content = content.replace(source, target)
        rendered.append(content)
    return rendered[0], rendered[1]


def write_service_units(config: InstallConfig) -> tuple[Path, Path]:
    bridge, api = render_service_units(config)
    config.config_dir.mkdir(parents=True, exist_ok=True)
    paths = (config.config_dir / "hermes-control-bridge.service", config.config_dir / "hermes-mobile-control-api.service")
    for path, content in zip(paths, (bridge, api), strict=True):
        path.write_text(content)
        path.chmod(0o644)
    return paths


def plugin_install_command(config: InstallConfig) -> list[str]:
    return ["hermes", "plugins", "install", f"file://{config.install_dir}", "--force", "--enable"]


def plugin_verify_command() -> list[str]:
    return ["hermes", "tools", "list"]


def verify_plugin(config: InstallConfig) -> Check:
    result = run_command(plugin_verify_command(), user=config.hermes_user)
    if result.returncode:
        return Check("Hermes plugin loaded", "FAIL", "tools list failed")
    if "hermes_control" not in result.stdout:
        return Check("Hermes plugin loaded", "FAIL", "hermes_control tool not registered")
    return Check("Hermes plugin loaded", "PASS", "hermes_control registered")


def render_install_plan(config: InstallConfig) -> str:
    lines = [
        f"Install revision source: {config.root}",
        f"Hermes user: {config.hermes_user}",
        "Generate or preserve protected API and bridge tokens",
        "Render service units for the selected install/config paths",
        f"Install and enable plugin from file://{config.root}",
        "$ " + " ".join(plugin_install_command(config)),
    ]
    lines.extend("$ " + " ".join(command) for command in install_commands(config))
    return "\n".join(lines)


def execute_install(config: InstallConfig) -> int:
    checks = preflight(config)
    print(format_checks(checks))
    if not preflight_ok(checks):
        return 2
    if os.geteuid() != 0:
        print("FAIL install: run with sudo", flush=True)
        return 2
    api_token, created_api_token = write_environment(config)
    write_service_units(config)
    for command in install_commands(config):
        result = run_command(command)
        if result.returncode:
            print(f"FAIL command: {' '.join(command)}\\n{result.stderr}")
            return result.returncode
    plugin_result = run_command(plugin_install_command(config), user=config.hermes_user)
    if plugin_result.returncode:
        print(f"FAIL plugin install: {plugin_result.stderr or plugin_result.stdout}")
        return plugin_result.returncode
    gateway_state = run_command(["systemctl", "is-active", "hermes-gateway"])
    if gateway_state.returncode == 0 and gateway_state.stdout == "active":
        gateway_restart = run_command(["systemctl", "restart", "hermes-gateway"])
        if gateway_restart.returncode:
            print("FAIL gateway restart")
            return gateway_restart.returncode
    plugin_check = verify_plugin(config)
    if plugin_check.status == "FAIL":
        print(f"FAIL {plugin_check.name}: {plugin_check.detail}")
        return 2
    revision = git_revision(config.root)
    if revision:
        write_install_record(config, revision)
    print("PASS install: services enabled and plugin loaded")
    if created_api_token:
        print(f"Mobile API token (store securely): {api_token}")
    else:
        print("Mobile API token preserved; use the existing token")
    if config.hostname:
        print(f"Mobile API URL: {config.hostname}")
    return 0


def _api_base_url(config: InstallConfig) -> str:
    return (config.hostname or os.getenv("CONTROL_API_URL") or "http://127.0.0.1:8787").rstrip("/")


def _api_token(config: InstallConfig) -> str | None:
    return _existing_env_value(_env_path(config), "CONTROL_API_TOKEN") or os.getenv("CONTROL_API_TOKEN")


def api_request(config: InstallConfig, path: str, *, method: str = "GET", body: dict | None = None) -> dict | list:
    headers = {"Accept": "application/json"}
    token = _api_token(config)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    encoded = None
    if body is not None:
        encoded = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    with urlopen(Request(f"{_api_base_url(config)}{path}", data=encoded, headers=headers, method=method), timeout=10) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, (dict, list)):
        raise ValueError("API returned an invalid JSON payload")
    return payload


def _api_check(config: InstallConfig, path: str, name: str) -> Check:
    try:
        api_request(config, path)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
        return Check(name, "FAIL", type(exc).__name__)
    return Check(name, "PASS", "reachable")


def _websocket_check(config: InstallConfig) -> Check:
    token = _api_token(config)
    if not token:
        return Check("Control API WebSocket", "FAIL", "CONTROL_API_TOKEN is not configured")
    base = _api_base_url(config)
    websocket_url = ("wss://" + base[8:] if base.startswith("https://") else "ws://" + base[7:] if base.startswith("http://") else base)
    websocket_url = f"{websocket_url}/ws/events?token={token}"

    async def receive_snapshot() -> None:
        import websockets

        async with websockets.connect(websocket_url, open_timeout=10, close_timeout=10) as socket:
            await socket.recv()

    try:
        asyncio.run(receive_snapshot())
    except (ImportError, OSError, TimeoutError, ValueError):
        return Check("Control API WebSocket", "FAIL", "authenticated WebSocket unavailable")
    return Check("Control API WebSocket", "PASS", "authenticated snapshot received")


def run_test_task(config: InstallConfig) -> Check:
    if not _api_token(config):
        return Check("Harmless task", "FAIL", "CONTROL_API_TOKEN is not configured")
    try:
        projects = api_request(config, "/projects")
        if not isinstance(projects, list) or not projects:
            return Check("Harmless task", "FAIL", "no native Hermes project is available")
        project = next((item for item in projects if isinstance(item, dict) and not item.get("archived")), projects[0])
        project_id = project.get("project_id") or project.get("id") or project.get("slug")
        if not isinstance(project_id, str) or not project_id:
            return Check("Harmless task", "FAIL", "project response has no usable ID")
        task = api_request(
            config,
            "/tasks",
            method="POST",
            body={"prompt": "Reply with exactly MOBILE-DEVICE-READY and do not use tools.", "project_id": project_id, "requires_approval": True},
        )
        if not isinstance(task, dict) or not isinstance(task.get("task_id"), str):
            return Check("Harmless task", "FAIL", "task creation returned no task ID")
        task_id = task["task_id"]
        api_request(config, f"/tasks/{task_id}/approve", method="POST", body={"reason": "installer doctor probe"})
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            current = api_request(config, f"/tasks/{task_id}")
            status = current.get("status") if isinstance(current, dict) else None
            if status == "completed":
                return Check("Harmless task", "PASS", "MOBILE-DEVICE-READY completed")
            if status in {"failed", "cancelled", "rejected"}:
                return Check("Harmless task", "FAIL", f"task ended {status}")
            time.sleep(1)
        return Check("Harmless task", "FAIL", "task did not complete within 90 seconds")
    except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
        return Check("Harmless task", "FAIL", type(exc).__name__)


def doctor(config: InstallConfig, *, execute_test_task: bool = False) -> list[Check]:
    checks = preflight(config)
    for service in ("hermes-control-bridge", "hermes-mobile-control-api"):
        result = run_command(["systemctl", "is-active", service])
        checks.append(Check(f"{service} service", "PASS" if result.returncode == 0 and result.stdout == "active" else "FAIL", result.stdout or result.stderr or "inactive"))
    checks.append(_api_check(config, "/health", "Control API health"))
    if _api_token(config):
        checks.append(_api_check(config, "/diagnostics", "Control API authentication"))
        checks.append(_api_check(config, "/projects", "Native project discovery"))
        checks.append(_websocket_check(config))
    else:
        checks.append(Check("Control API authentication", "FAIL", "CONTROL_API_TOKEN is not configured"))
    if execute_test_task:
        checks.append(run_test_task(config))
    return checks
