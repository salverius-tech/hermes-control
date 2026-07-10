# Hermes Mobile Control

Android-first, iOS-ready mobile control app for local Hermes infrastructure.

## Status

This repository is newly initialized and currently contains:

- `services/control_api/` — FastAPI companion API with token auth, optional SQLite task/event persistence, task/project/agent read models, diagnostics, and a configurable Hermes command executor.
- `apps/mobile/` — Expo React Native app shell with dashboard, bottom navigation, task timelines/results, projects, voice-capable new task, diagnostics, and settings screens.
- `scripts/verify.py` — canonical unit/integration/e2e verification runner.
- `ARCHITECTURE.md` — backend/mobile layer map, dependency rules, and integration seam.
- `TESTING.md` — layer map and test strategy.
- `docs/` — API contract, operations/deployment runbooks, and documentation index.
- `.hermes/plans/` — implementation plan used for this build.

Agent Queue is a separate project and is not a dependency of this app at this time.

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
curl -H 'Authorization: Bearer dev-token' http://localhost:8787/tasks
```

Create a task:

```bash
curl -X POST \
  -H 'Authorization: Bearer dev-token' \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Check Hermes status"}' \
  http://localhost:8787/tasks
```

## Mobile setup

```bash
cd apps/mobile
npm install
npm run typecheck
npm start
```

When testing from a physical Android device, use the PC's LAN IP or Tailscale hostname rather than `127.0.0.1`.

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
- `TESTING.md` — verification strategy and coverage map.
- `docs/API.md` — REST/WebSocket contract.
- `docs/OPERATIONS.md` — local runbook, Android build/sideload notes, troubleshooting.
- `docs/DEPLOYMENT.md` — Proxmox LXC + Caddy production deployment guide.
- `deploy/` — example systemd service, Caddy route, and environment file.
- `docs/README.md` — documentation index.

## Security notes

- Do not expose the control API publicly without TLS and strong auth.
- Keep `CONTROL_API_TOKEN` out of git.
- The mobile app stores only the companion API URL/token, not lower-level infrastructure credentials.
