# Hermes Mobile Control

Android-first, iOS-ready mobile control app for local Hermes infrastructure.

## Status

This repository is newly initialized and currently contains:

- `services/control_api/` — FastAPI companion API with token auth, optional SQLite task/event persistence, task/project/agent read models, diagnostics, and a configurable Hermes command executor.
- `apps/mobile/` — Expo React Native app shell with dashboard, bottom navigation, task timelines/results, projects, voice-capable new task, diagnostics, and settings screens.
- `scripts/verify.py` — canonical unit/integration/e2e verification runner.
- `docs/PRD.md` — canonical product requirements, roadmap, status, risks, and remaining work.
- `ARCHITECTURE.md` — backend/mobile layer map, dependency rules, and integration seam.
- `TESTING.md` — layer map and test strategy.
- `docs/` — API contract, operations/deployment runbooks, and documentation index.
- `.hermes/plans/` — implementation plan used for this build.

Agent Queue is a separate project and is not a dependency of this app at this time.

## Toolchain requirements

- Python 3.13+ with a project virtualenv and `requirements.txt` installed.
- Node.js 20+.
- pnpm 10.12.1, pinned by `apps/mobile/package.json`.

The mobile workspace uses pnpm exclusively. Install the mobile dependencies with
`pnpm install` from `apps/mobile`; do not use npm or commit a second lockfile.

## Backend setup

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
CONTROL_API_TOKEN=dev-token CONTROL_API_DB_PATH=./data/control-api.db uvicorn services.control_api.main:app --host 0.0.0.0 --port 8787
```

Optional local Hermes command execution:

```bash
CONTROL_API_HERMES_COMMAND='hermes chat -q'
```

The Hermes Control Extension is also a standalone Hermes plugin. Its root
`plugin.yaml` and `__init__.py` register the `hermes_control` tool and start the
local structured bridge. The plugin-side compatibility command is configured
separately from the Control API:

```bash
HERMES_CONTROL_EXTENSION_SOCKET=/run/hermes/control-extension.sock
HERMES_CONTROL_EXTENSION_TOKEN='replace-with-local-bridge-token'
HERMES_CONTROL_EXTENSION_HERMES_COMMAND='hermes chat -q'
```

Optional Discord webhook notifications:

```bash
CONTROL_API_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/[REDACTED]'
```

Health check:

```bash
curl http://localhost:8787/health
```

Authenticated task list:

```bash
curl -H 'Authorization: Bearer <CONTROL_API_TOKEN>' http://localhost:8787/tasks
```

Create a task:

```bash
curl -X POST \
  -H 'Authorization: Bearer <CONTROL_API_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Check Hermes status"}' \
  http://localhost:8787/tasks
```

## Mobile setup

```bash
cd apps/mobile
pnpm install
pnpm run typecheck
pnpm start
```

When testing from a physical Android device, use the PC's LAN IP or Tailscale hostname rather than `127.0.0.1`.

## Extension bundle

Build a distributable Hermes plugin bundle from the repository root:

```bash
python3 scripts/build_extension_bundle.py --output /tmp/hermes-control-extension.tar.gz
tar -xzf /tmp/hermes-control-extension.tar.gz -C /opt/hermes/plugins
sudo install -m 0644 /opt/hermes/plugins/hermes-control-extension-0.1.0/deploy/hermes-control-bridge.service /etc/systemd/system/hermes-control-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-control-bridge
```

The Hermes plugin installer installs/enables plugin files only. The bridge is a
separate systemd service and must use the same service account, environment
file, socket path, and bridge token as the Control API. Its `RuntimeDirectory`
creates `/run/hermes` with the bridge service account's ownership at boot.

Configure the same socket path and bridge token for the bridge service and
Control API. The bridge requires `HERMES_CONTROL_EXTENSION_TOKEN` by default;
only set `HERMES_CONTROL_EXTENSION_ALLOW_UNAUTHENTICATED=1` for local development.

## Verification

Canonical verification:

```bash
source .venv/Scripts/activate
python scripts/verify.py
```

Connected Android release build/sideload verification:

```bash
python scripts/verify.py --android --sideload
```

Connected Android release build/sideload plus Maestro UI smoke flow:

```bash
python scripts/verify.py --maestro
```

Maestro is installed from the official Windows-compatible ZIP release under `C:\Users\jthol\.maestro\maestro`; `scripts/verify.py` adds Android Studio's bundled JBR and Maestro to the verification environment.

GitHub Actions can also build and retain a release APK from the **verify** workflow. Run it manually with `build_android=true`; the workflow uploads `hermes-mobile-control-release-apk` containing `app-release.apk`.

See `TESTING.md` for the unit, integration, e2e, edge-path, and architecture-boundary test map.

## Documentation map

- `ARCHITECTURE.md` — layer boundaries and dependency direction.
- `docs/PRD.md` — product requirements, status, roadmap, risks, and remaining work.
- `TESTING.md` — verification strategy and coverage map.
- `docs/API.md` — REST/WebSocket contract.
- `docs/NATIVE_STORE_ROUTE_MAPPING.md` — repository-verified native Hermes store ownership, schema fixture, and API route mapping.
- `docs/OPERATIONS.md` — local runbook, Android build/sideload notes, troubleshooting.
- `docs/DEPLOYMENT.md` — Proxmox LXC + Caddy production deployment guide.
- `deploy/` — example systemd service, Caddy route, and environment file.
- `docs/README.md` — documentation index.

## Security notes

- Do not expose the control API publicly without TLS and strong auth.
- Keep `CONTROL_API_TOKEN` out of git.
- The mobile app stores only the companion API URL/token, not lower-level infrastructure credentials.
- Install repository hooks with `scripts/install-git-hooks.sh`; pre-commit scans staged files and pre-push scans all tracked files.
- Run `python3 scripts/secret_scan.py --all` before publishing.
