# Control API

FastAPI companion API for the Hermes Mobile Control app.

## Run locally

```bash
source .venv/Scripts/activate
CONTROL_API_TOKEN=dev-token CONTROL_API_DB_PATH=./data/control-api.db uvicorn services.control_api.main:app --host 0.0.0.0 --port 8787
```

## Endpoints

- `GET /health` — unauthenticated health check.
- `GET /tasks` — list tasks.
- `POST /tasks` — create a queued Hermes task shell.
- `GET /tasks/{task_id}` — task detail.
- `GET /projects` — project summaries.
- `GET /agents` — agent statuses.

All endpoints except `/health` require:

```text
Authorization: Bearer <CONTROL_API_TOKEN>
```

## Current integration boundary

`HermesTaskService` currently records queued tasks through the projection layer. Set `CONTROL_API_DB_PATH` to persist task state in SQLite across API restarts; omit it for in-memory development mode.

Real Hermes execution is still intentionally behind the `HermesTaskService` seam. A future adapter can call Hermes CLI, Hermes API Server, the gateway, or another local integration surface without changing mobile-facing contracts.
