# Hermes Control Installation

This guide covers the current guided installer for a Debian/Ubuntu systemd host where Hermes is already installed and usable by a service account.

The supported runtime remains split into independent processes:

```text
Mobile app → private HTTPS proxy → Control API → Unix socket → bridge → Hermes
                                      ↘ SQLite state
Hermes gateway loads the plugin separately.
```

The installer does not replace Hermes gateway/profile management, rewrite arbitrary Caddy configuration, or remove an existing installation.

## Safety and support boundary

Before installing, confirm all of the following:

- You are working on a disposable Debian/Ubuntu systemd guest or an explicitly isolated host.
- The selected Hermes user already exists and can run `hermes status`.
- You have a reviewed immutable Git commit, tag, or release to install.
- You have a backup or other recovery path for any existing SQLite state.
- You know the private HTTPS hostname, if mobile access is required.

Do **not** use the current production host for destructive installation testing if doing so would require removing or replacing its existing Hermes Control installation.

The installer writes or manages `/opt/hermes-mobile-control`, `/etc/hermes-mobile-control`, `/var/lib/hermes-mobile-control`, and the two systemd units. Review the dry-run before allowing mutation.

## Prerequisites

Install the host packages:

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip sudo ca-certificates
```

Verify Hermes and systemd before proceeding:

```bash
hermes status
systemctl is-system-running
```

A `degraded` systemd state may be acceptable only when the unrelated degraded unit is understood. Do not proceed past a failing prerequisite without understanding it.

## Prepare the reviewed checkout

Use a clean checkout at the reviewed revision:

```bash
git clone https://github.com/salverius-tech/hermes-control.git /opt/src/hermes-control
cd /opt/src/hermes-control
git checkout --detach <reviewed-commit>
git status --short
```

The final status command must be empty. The installer records the resolved revision in:

```text
/var/lib/hermes-mobile-control/install-record.json
```

## Install the CLI

Create an isolated development/installer environment and install the CLI from the reviewed checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e .
```

Run read-only preflight first:

```bash
.venv/bin/hermes-control --root . preflight
```

For machine-readable output:

```bash
.venv/bin/hermes-control --root . --json preflight
```

Preflight must pass the Hermes executable/user, Python/venv/pip/Git, repository, and path checks before installation.

## Preview and install

Preview the mutation plan:

```bash
sudo .venv/bin/hermes-control --root . install --dry-run
```

Install from the reviewed checkout using the detected Hermes user:

```bash
sudo .venv/bin/hermes-control --root . install
```

Or specify the service user explicitly:

```bash
sudo .venv/bin/hermes-control --root . install --hermes-user hermes
```

The installer performs the following operations:

1. Runs preflight.
2. Creates or reuses the deployment virtualenv.
3. Copies the reviewed checkout to the deployment directory.
4. Installs runtime dependencies and the CLI.
5. Generates or preserves the API and bridge tokens.
6. Writes the protected compatibility environment file:
   `/etc/hermes-mobile-control/control-api.env`.
7. Renders and installs the API and bridge systemd units.
8. Installs/enables the plugin from the reviewed deployment checkout.
9. Reloads systemd and enables/starts both services.
10. Verifies `hermes_control` registration and records the revision.

The current first slice uses one shared environment file for API and bridge settings. Keep it protected; it contains both the mobile API token and internal bridge token.

Installation does not execute a model task by default.

## Verify the installation

Run the authoritative diagnostic command:

```bash
sudo .venv/bin/hermes-control --root /opt/hermes-mobile-control doctor
```

Request JSON output for automation:

```bash
sudo .venv/bin/hermes-control --root /opt/hermes-mobile-control --json doctor
```

Check the service state directly when diagnosing startup:

```bash
sudo systemctl status hermes-control-bridge --no-pager
sudo systemctl status hermes-mobile-control-api --no-pager
sudo journalctl -u hermes-control-bridge -n 100 --no-pager
sudo journalctl -u hermes-mobile-control-api -n 100 --no-pager
```

The doctor checks are separate: Hermes/plugin state, bridge service/socket, API service/authentication, native project discovery, WebSocket readiness, and executor readiness.

## Optional harmless task

Only run this after doctor reports the required services and authenticated API readiness as passing:

```bash
sudo .venv/bin/hermes-control --root /opt/hermes-mobile-control doctor --execute-test-task
```

This is explicit opt-in because it invokes the configured Hermes execution path and may consume provider resources. The expected harmless fixture response is:

```text
MOBILE-DEVICE-READY
```

Do not use production prompts or credentials for development verification.

## Update from an immutable revision

Updates require a clean Git checkout and an immutable reviewed ref:

```bash
cd /opt/src/hermes-control
git status --short
sudo .venv/bin/hermes-control --root . update --ref <new-reviewed-commit> --dry-run
sudo .venv/bin/hermes-control --root . update --ref <new-reviewed-commit>
```

The dry-run resolves the target revision without checkout or service mutation. The update path preserves the SQLite database and writes the installed revision record. Verify afterward:

```bash
sudo .venv/bin/hermes-control --root /opt/hermes-mobile-control doctor
sudo systemctl is-active hermes-control-bridge hermes-mobile-control-api
```

Component-aware restart decisions, token rotation, rollback execution, and uninstall are not part of this first slice.

## Existing private HTTPS proxy

The first release does not rewrite arbitrary Caddy configuration. Configure or review the existing private proxy separately, then validate:

```text
HTTPS /health                         → 200
HTTPS authenticated /diagnostics      → 200
HTTPS authenticated /ws/events         → WebSocket snapshot
Direct public access to API            → not exposed
```

Keep the API loopback-bound unless the deployment design explicitly changes and re-verifies the network boundary.

## Disposable verification

The repository has three relevant verification levels:

```bash
# Installer/unit and backend/mobile checks
.venv/bin/python scripts/verify.py

# Process-level API e2e only
.venv/bin/python -m pytest -q services/control_api/tests/test_process_e2e.py -m e2e

# Installer mutation/idempotence check in a disposable Debian container
# See the test fixture/history for the current deterministic runtime setup.
```

The process-level tests use a temporary API subprocess, SQLite database, WebSocket client, and deterministic fake executor. They do not prove real Hermes gateway/plugin behavior, Caddy/TLS reachability, or systemd supervision.

A clean-host systemd install remains a separate acceptance requirement. Do not report the installer as production-ready solely because the repository test suite passes.

## Failure handling

If preflight fails, stop and address the named prerequisite. If installation fails after mutation:

1. Do not delete the existing state directory.
2. Inspect the command failure and service journals.
3. Run `doctor` against the installed deployment.
4. Compare `/etc/hermes-mobile-control/control-api.env` and the install record with the reviewed revision.
5. Restore from the operator’s host backup/recovery procedure if state is affected.

Automatic rollback and uninstall are intentionally deferred.

## Secret handling

- Never commit `control-api.env`, tokens, provider keys, or private credentials.
- Never paste API or bridge tokens into logs or bug reports.
- The mobile app receives only the HTTPS URL and API token.
- The bridge token remains internal to the API/bridge path.
- Run the repository secret scan before publishing changes:

```bash
python3 scripts/secret_scan.py --all
```
