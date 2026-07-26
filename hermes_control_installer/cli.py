from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import (
    Check,
    default_config,
    doctor,
    execute_install,
    format_checks,
    install_commands,
    preflight,
    preflight_ok,
    render_install_plan,
    rollback_install,
    rotate_tokens,
    uninstall,
    update_install,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-control", description="Install and diagnose Hermes Control.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Control repository checkout (default: current directory)")
    parser.add_argument("--hermes-user", help="Hermes service user (auto-detected by default)")
    parser.add_argument("--hostname", help="Private HTTPS hostname or base URL")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable check output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight", help="Run read-only prerequisite checks")
    preflight_parser.set_defaults(action="preflight")

    install_parser = subparsers.add_parser("install", help="Install or update the Control services")
    install_parser.add_argument("--dry-run", action="store_true", help="Print planned changes without mutating the host")
    install_parser.set_defaults(action="install")

    doctor_parser = subparsers.add_parser("doctor", help="Check installed runtime state")
    doctor_parser.add_argument("--execute-test-task", action="store_true", help="Run the harmless end-to-end task probe")
    doctor_parser.set_defaults(action="doctor")

    update_parser = subparsers.add_parser("update", help="Update from a reviewed immutable Git revision")
    update_parser.add_argument("--ref", required=True, help="Reviewed Git tag or commit")
    update_parser.add_argument("--dry-run", action="store_true", help="Resolve the revision without checkout or service mutation")
    update_parser.set_defaults(action="update")

    rollback_parser = subparsers.add_parser("rollback", help="Rollback to a reviewed immutable Git revision")
    rollback_parser.add_argument("--ref", required=True, help="Reviewed Git tag or commit")
    rollback_parser.add_argument("--dry-run", action="store_true", help="Resolve the revision without checkout or service mutation")
    rollback_parser.set_defaults(action="rollback")

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove managed Hermes Control resources")
    uninstall_parser.add_argument("--yes", action="store_true", help="Confirm service and resource removal")
    uninstall_parser.add_argument("--dry-run", action="store_true", help="Print removal plan without mutation")
    uninstall_parser.add_argument("--purge-config", action="store_true", help="Also remove protected configuration and tokens")
    uninstall_parser.add_argument("--purge-state", action="store_true", help="Also remove the SQLite database and install record")
    uninstall_parser.set_defaults(action="uninstall")

    rotate_parser = subparsers.add_parser("rotate-token", help="Rotate an API or internal bridge token")
    rotate_parser.add_argument(
        "--scope",
        choices=("api", "bridge", "both"),
        default="api",
        help="Token to rotate (default: api; bridge also restarts the API to reload shared credentials)",
    )
    rotate_parser.set_defaults(action="rotate-token")

    return parser


def _emit(checks: list[Check], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps([check.__dict__ for check in checks], sort_keys=True))
    else:
        print(format_checks(checks))


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    config = default_config(args.root.resolve(), hermes_user=args.hermes_user, hostname=args.hostname)

    if args.action == "preflight":
        checks = preflight(config)
        _emit(checks, as_json=args.json)
        return 0 if preflight_ok(checks) else 2
    if args.action == "install":
        if args.dry_run:
            checks = preflight(config)
            _emit(checks, as_json=args.json)
            print(render_install_plan(config))
            return 0 if preflight_ok(checks) else 2
        return execute_install(config)
    if args.action == "doctor":
        checks = doctor(config, execute_test_task=args.execute_test_task)
        _emit(checks, as_json=args.json)
        return 0 if not any(check.status == "FAIL" for check in checks) else 2
    if args.action == "update":
        return update_install(config, args.ref, dry_run=args.dry_run)
    if args.action == "rollback":
        return rollback_install(config, args.ref, dry_run=args.dry_run)
    if args.action == "uninstall":
        return uninstall(
            config,
            confirmed=args.yes,
            dry_run=args.dry_run,
            purge_config=args.purge_config,
            purge_state=args.purge_state,
        )
    if args.action == "rotate-token":
        return rotate_tokens(config, scope=args.scope)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
