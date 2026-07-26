# Hermes Control Simplified Installation Plan

Status: approved design
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
```

The first implementation is a CLI-first operator tool with a clean non-interactive interface so an infrastructure role can invoke it later. It must not become a second, conflicting source of production configuration.

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

### 3.6 Locked deployment decisions

- First supported target: Debian/Ubuntu systemd hosts, with the current Proxmox LXC as the first tested deployment.
- Production source: a reviewed immutable GitHub release, tag, or commit; never a floating branch.
- The installed revision must be recorded and displayed by `doctor`.
- The first release validates an existing private HTTPS proxy; it does not rewrite arbitrary Caddy configurations.
- The plugin is installed and verified where appropriate, but native plugin task execution is not a hard dependency until a stable Hermes lifecycle implementation exists.
- Installation does not execute a model task by default. End-to-end execution is explicit via `doctor --execute-test-task`.
- QR onboarding, managed Caddy editing, rollback, uninstall, device enrollment, and native Hermes task callbacks are deferred.
- The installer must expose stable automation-friendly commands and exit codes so an Ansible/infrastructure role can wrap it later.

## 4. Target user workflows

### 4.1 Guided first install

```bash
sudo hermes-control install
```

Prompt only for unresolved values:

- Hermes service user.
- Private hostname or local-only mode.
- Caddy mode: local-only or existing private proxy.
- Approval policy, defaulting to enabled.

The installer then performs preflight, installation, plugin activation, service setup, existing-proxy validation, verification, and mobile onboarding output. It does not execute a model task unless explicitly requested.

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

The first release supports two explicit modes:

1. Local-only loopback.
2. Existing reverse proxy, with route instructions and validation.

Managed Caddy site configuration is deferred. The installer must not assume one Caddy filesystem layout or overwrite an existing site silently.

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
Optional harmless task (`--execute-test-task`)
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
- Record the previous revision for future rollback support, but do not implement rollback in the first release.

### Acceptance evidence

- Update from one reviewed revision to another succeeds without data loss.
- Unchanged components are not unnecessarily restarted.
- Token rotation invalidates the old API token and preserves bridge operation when API-only rotation is selected.
- Existing SQLite and Hermes project data remain preserved during update operations.

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
- Provide QR onboarding in the first release.
- Provide device enrollment in the first release.
- Depend on a native Hermes task/lifecycle callback that is not yet available and verified.

## 8. Approved first implementation slice

The design decisions above are locked for implementation. The first slice is:

```text
Python CLI foundation
+ Debian/Ubuntu systemd preflight
+ immutable checkout/revision handling
+ idempotent venv/config/secret setup
+ bridge and API systemd installation
+ plugin install/load verification
+ existing HTTPS proxy validation
+ doctor
+ explicit --execute-test-task verification
+ URL/token mobile onboarding output
```

The first slice must be tested on a clean disposable Debian/Ubuntu systemd guest before production use. Defer managed Caddy, rollback execution, QR onboarding, device enrollment, and uninstall until the install/doctor path is proven.

## 9. Implementation progress

Completed in the current implementation branch:

- CLI package and console entry point.
- Read-only preflight checks.
- Idempotent configuration/token rendering primitives.
- Dry-run install plan.
- Virtualenv and dependency installation commands.
- Plugin installation command from the reviewed checkout.
- API and bridge systemd installation commands.
- API health, authentication, native-project, and opt-in harmless-task doctor checks.
- Installer unit tests included in canonical verification.
- README quick-start documentation.

- Secure update command and immutable revision enforcement: implemented and verified.

Remaining before this slice is production-ready:

- Clean-host Debian/Ubuntu systemd integration test.
- Existing HTTPS proxy/WebSocket validation against a real private endpoint.
