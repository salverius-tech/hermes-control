# Hermes Control Simplified Installation Plan

Status: proposed
Owner: Hermes Control maintainers
Scope: installer and operational lifecycle for the Control API, bridge, Hermes plugin, and private mobile access

## 1. Objective

Reduce backend setup from a multi-document manual procedure to one guided, idempotent workflow while preserving the current runtime separation:

```text
Mobile app → Caddy/private HTTPS → Control API → Unix socket → Control bridge → Hermes
                                               ↘ SQLite state
Hermes gateway loads the Hermes Control plugin separately.
```

The operator-facing workflow should become:

```bash
sudo hermes-control install
sudo hermes-control doctor
```

The internal services remain independently supervised so an API restart does not kill an active Hermes task, and gateway/plugin lifecycle remains distinct from bridge and API lifecycle.

## 2. Current runtime inventory

| Component | Runtime owner | Role | Repository artifact |
|---|---|---|---|
| Hermes gateway | Hermes installation | Loads enabled plugins and registers `hermes_control` | External to this repository |
| Control bridge | systemd | Owns the structured Unix-socket execution bridge and long-running Hermes work | `deploy/hermes-control-bridge.service` |
| Control API | systemd/Uvicorn | REST API, authenticated WebSocket, projects, tasks, approvals, persistence, diagnostics | `deploy/hermes-mobile-control-api.service` |
| Caddy | systemd | Private HTTPS termination and REST/WebSocket proxy | `deploy/Caddyfile.control-api.example` |
| SQLite store | Control API process | Durable tasks/events/audit/work-thread state | `CONTROL_API_DB_PATH` |
| Hermes CLI subprocess | Bridge child process | Executes an individual Hermes task; not a daemon | `services/hermes_extension/host.py` |

The plugin installer must not be represented as installing the API or bridge. Plugin installation, plugin loading, bridge readiness, API readiness, and proxy readiness are separate states.

## 3. Design decisions

### 3.1 Preserve process boundaries

Do not combine the gateway plugin, bridge, and API into one process. Keep:

- `hermes-control-bridge.service` as the restart-supervised task execution owner.
- `hermes-mobile-control-api.service` as the mobile-facing API and persistence owner.
- Hermes gateway as the plugin host.
- Caddy as the private network boundary.

### 3.2 One operator-facing installer

Add a guided CLI with these primary commands:

```bash
hermes-control preflight
hermes-control install
hermes-control doctor
hermes-control update
hermes-control rotate-token
hermes-control uninstall
```

The first implementation may be a reviewed executable/script entry point, but the interface must be stable enough for later packaging.

### 3.3 Safe defaults

Defaults:

- Auto-detect the Hermes service user and home.
- Structured bridge execution.
- Mandatory task approval enabled.
- API bound to loopback.
- SQLite under `/var/lib/hermes-mobile-control`.
- Configuration under `/etc/hermes-mobile-control`.
- Installation under `/opt/hermes-mobile-control`.
- Private HTTPS required for non-local/mobile use.

The command fallback remains available as a compatibility/recovery path but is not the normal install mode.

### 3.4 Secret separation

Generate and manage two independent secrets:

- External `CONTROL_API_TOKEN`: given to the mobile app.
- Internal bridge token: shared only by the API and bridge.

The mobile app receives only:

```text
API HTTPS URL
API bearer token
```

Never expose the bridge token, provider keys, SSH keys, Hermes credentials, or Proxmox credentials to the phone.

### 3.5 Idempotence and preservation

Repeated installation must:

- Preserve existing API and bridge tokens unless rotation is explicitly requested.
- Preserve the SQLite database and Hermes project/session data.
- Preserve existing project folders and repositories.
- Avoid overwriting an existing Caddy site without confirmation.
- Restart only components whose source/configuration changed.
- Detect and report conflicting existing units or ports before mutation.

## 4. Target user workflows

### 4.1 Guided first install

```bash
sudo hermes-control install
```

Prompt only for unresolved values:

- Hermes service user.
- Private hostname or local-only mode.
- Caddy mode: local, existing proxy, or managed Caddy.
- Approval policy, defaulting to enabled.

The installer then performs preflight, installation, plugin activation, service setup, proxy setup, verification, and mobile onboarding output.

### 4.2 Non-interactive install

```bash
sudo hermes-control install \
  --hermes-user hermes \
  --hostname control-api.example.ts.net \
  --configure-caddy \
  --require-approval
```

All required values must be supplied or have safe defaults. Ambiguous or unsafe existing configuration must fail rather than being guessed.

### 4.3 Update

```bash
sudo hermes-control update --ref <reviewed-ref>
```

Sequence:

```text
preflight
→ fetch/verify reviewed revision
→ install dependencies
→ refresh plugin
→ install changed units/configuration
→ restart bridge if bridge changed
→ restart API if API/dependencies changed
→ restart gateway if plugin changed
→ doctor
```

Support `--dry-run`. Record previous and new revisions and component restart results.

### 4.4 Troubleshooting

```bash
sudo hermes-control doctor
sudo hermes-control doctor --json
```

The doctor command is the canonical support entry point.

## 5. Implementation phases

## Phase 1 — CLI foundation and preflight

### Deliverables

- CLI entry point and command dispatch.
- Configuration model with defaults and explicit overrides.
- Read-only `preflight` command.
- Human-readable and machine-readable result types.
- Tests for detection, missing prerequisites, conflicts, and safe defaults.

### Preflight checks

- Hermes executable exists.
- Hermes version is captured.
- Selected service user can run `hermes status`.
- Hermes home exists and is readable.
- Native project/session stores are available.
- Python, venv, pip, and Git are available.
- Required directories and permissions are valid.
- API port is free or owned by this deployment.
- Caddy is present when requested.
- Existing units/config/database are detected.
- Current repository revision is identified.

### Acceptance evidence

- `hermes-control preflight` performs no mutations.
- Failure output identifies the concrete prerequisite and remediation.
- Tests cover a clean host, an existing installation, and a conflicting service/port.

## Phase 2 — Core installation and configuration

### Deliverables

- Versioned checkout/install directory management.
- Python virtualenv creation and dependency installation.
- Protected `/etc/hermes-mobile-control` and `/var/lib/hermes-mobile-control` setup.
- Generated API and bridge tokens.
- Rendered API and bridge environment files.
- Idempotent configuration updates.
- Dry-run support.

### Configuration direction

Initially preserve compatibility with `deploy/control-api.env.example`. Then add a generated operator configuration layer with component-specific environment files:

```text
/etc/hermes-mobile-control/config.yaml
/etc/hermes-mobile-control/api.env
/etc/hermes-mobile-control/bridge.env
```

The API environment owns API authentication, native Hermes integration, persistence, approval policy, and bridge client settings. The bridge environment owns bridge runtime and Hermes execution settings.

### Acceptance evidence

- Clean installation produces correct ownership/modes.
- Re-running installation preserves tokens and SQLite state.
- Secrets do not appear in stdout, logs, Git, or generated diagnostics.
- `pip check` passes after dependency installation.

## Phase 3 — Plugin installation and gateway activation

### Deliverables

- Installer integration with the supported Hermes plugin installer.
- `--force --enable` behavior against the reviewed checkout/ref.
- Installed-manifest verification.
- Gateway restart handling from an external process.
- Runtime plugin/tool registration verification.
- Clear distinction between installed, enabled, loaded, and registered.

### Acceptance evidence

The installer must independently verify:

```text
plugin installed: PASS
plugin enabled: PASS
gateway restarted: PASS
plugin loaded: PASS
hermes_control registered: PASS
```

A plugin that appears in `hermes plugins list` but fails under `HERMES_PLUGINS_DEBUG=1 hermes tools list` must fail installation verification.

## Phase 4 — Bridge and API service installation

### Deliverables

- Install and enable `hermes-control-bridge.service`.
- Install and enable `hermes-mobile-control-api.service`.
- Ensure `RuntimeDirectory=hermes` creates the socket parent correctly.
- Reload systemd only when required.
- Start services in dependency order.
- Verify service users, working directories, environment files, and PIDs.
- Verify a real Unix-socket request/response, not only socket-path existence.

### Acceptance evidence

```text
bridge service active: PASS
bridge socket connection: PASS
API service active: PASS
API /health: PASS
API authenticated /diagnostics: PASS
executor_ready: true
```

The structured bridge is the required production path. The command fallback remains testable and available for recovery.

## Phase 5 — Caddy/private proxy integration

### Deliverables

Support three explicit modes:

1. Local-only loopback.
2. Existing reverse proxy, with route instructions and validation.
3. Managed Caddy site configuration.

The installer must not assume one Caddy filesystem layout or overwrite an existing site silently.

### Acceptance evidence

- Caddy configuration validates.
- HTTPS `/health` works.
- Authenticated HTTPS `/diagnostics` works.
- Authenticated WebSocket upgrade works.
- API remains loopback-bound.
- No public direct API listener is introduced.

## Phase 6 — Doctor and mobile onboarding

### Deliverables

Implement `doctor` checks for:

```text
Hermes installation
Hermes profile
Plugin installed
Plugin enabled
Plugin loaded
Bridge service
Bridge socket
API service
API authentication
Native projects
Caddy route
WebSocket upgrade
Executor readiness
Approval policy
Harmless task
```

Support:

```bash
hermes-control doctor
hermes-control doctor --json
```

Print a one-time mobile onboarding block containing only the API URL and API token. QR onboarding is optional and deferred until the text workflow is stable.

### Acceptance evidence

- Doctor distinguishes `WARN` from `FAIL`.
- JSON output is stable and secret-free.
- Mobile can use the printed URL/token to authenticate, discover projects, receive WebSocket events, and complete an approval-gated harmless task.

## Phase 7 — Lifecycle operations

### Deliverables

- `update --ref <immutable-ref>`.
- `update --dry-run`.
- Previous/new revision recording.
- Component-aware restart decisions.
- Token rotation.
- Bridge-token rotation with coordinated API/bridge restart.
- Safe uninstall that requires explicit confirmation and preserves data by default.
- Optional rollback metadata and previous-release retention.

### Acceptance evidence

- Update from one reviewed revision to another succeeds without data loss.
- Unchanged components are not unnecessarily restarted.
- Token rotation invalidates the old API token and preserves bridge operation when API-only rotation is selected.
- Uninstall does not delete SQLite or Hermes project data unless explicitly requested.

## Phase 8 — Documentation and packaging

### Deliverables

- New `docs/INSTALL.md` quick-start guide.
- Existing low-level procedure moved/reframed as `docs/OPERATIONS.md`.
- Troubleshooting guide based on `doctor` output.
- Upgrade/rollback documentation.
- Packaging/release artifact for the CLI or installer.
- CI coverage for installer source contracts and safe configuration behavior.

The user-facing documentation should center on:

```text
install
→ doctor
→ mobile setup
```

Manual systemd/Caddy instructions remain available as recovery documentation, not the primary path.

## 6. Verification matrix

| Layer | Required evidence |
|---|---|
| CLI | Unit tests for configuration, detection, rendering, idempotence, and error handling |
| Installer | Disposable host/container integration test where practical |
| Plugin | Installed/enabled/loaded/tool registration checks |
| Bridge | Real socket request/response and restart/readiness checks |
| API | Full backend pytest suite and authenticated diagnostics |
| Proxy | HTTPS REST and WebSocket validation |
| Persistence | API restart preserves tasks/events/projects |
| Security | Secret scan, restrictive file modes, no credential-bearing logs |
| Mobile | TypeScript, unit tests, physical-device task/reload validation |
| Release | Clean-host install from reviewed immutable revision |

Canonical repository verification remains:

```bash
.venv/bin/python scripts/verify.py
```

Any installer change that spans Python, systemd, plugin, proxy, and mobile boundaries must report evidence per layer rather than treating a backend test pass as full deployment verification.

## 7. Non-goals

The first installer version will not:

- Replace Hermes gateway or Hermes profile management.
- Provision Proxmox/LXC infrastructure.
- Manage provider credentials.
- Manage SSH keys or repository credentials.
- Perform automatic repository cloning for recovery projects.
- Expose the API publicly by default.
- Collapse API, bridge, and gateway into one process.
- Add mobile push notifications.
- Build a new APK as part of backend installation.
- Automatically rewrite arbitrary existing Caddy configurations.

## 8. Implementation gate

Before implementation begins, confirm:

- Target install hosts: Debian/Ubuntu LXC, VM, or both.
- Supported Hermes service-user model: auto-detect/reuse existing user or create `hermes`.
- Whether the first release must manage Caddy or only validate an existing proxy.
- Whether the installer is a Python CLI, shell wrapper, or packaged executable.
- Whether QR onboarding is in the first release or deferred.
- Whether update/rollback belongs in the first release or follows the initial installer.

Recommended first implementation slice:

```text
Phase 1 preflight
+ Phase 2 core installation
+ Phase 4 systemd service setup
+ Phase 6 doctor
```

Defer managed Caddy, rollback, QR onboarding, and uninstall until the install/doctor path is proven on a clean host.
