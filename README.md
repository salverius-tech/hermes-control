# Hermes Mobile Control

Android-first, iOS-ready mobile control app for local Hermes infrastructure.

## Status

This repository is newly initialized and currently contains:

- `services/control_api/` — FastAPI companion API with token auth, optional SQLite task persistence, task/project/agent read models, and task submission shell.
- `apps/mobile/` — Expo React Native app shell with dashboard, bottom navigation, tasks, projects, voice-capable new task, and settings screens.
- `scripts/verify.py` — canonical unit/integration/e2e verification runner.
- `ARCHITECTURE.md` — backend/mobile layer map, dependency rules, and integration seam.
- `TESTING.md` — layer map and test strategy.
- `docs/` — API contract, operations runbook, and documentation index.
- `.hermes/plans/` — implementation plan used for this build.

Agent Queue is a separate project and is not a dependency of this app at this time.

## Backend setup

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
CONTROL_API_TOKEN=dev-token CONTROL_API_DB_PATH=./data/control-api.db uvicorn services.control_api.main:app --host 0.0.0.0 --port 8787
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

See `TESTING.md` for the unit, integration, e2e, edge-path, and architecture-boundary test map.

## Documentation map

- `ARCHITECTURE.md` — layer boundaries and dependency direction.
- `TESTING.md` — verification strategy and coverage map.
- `docs/API.md` — REST/WebSocket contract.
- `docs/OPERATIONS.md` — local runbook, Android build/sideload notes, troubleshooting.
- `docs/README.md` — documentation index.

## Security notes

- Do not expose the control API publicly without TLS and strong auth.
- Keep `CONTROL_API_TOKEN` out of git.
- The mobile app stores only the companion API URL/token, not lower-level infrastructure credentials.
