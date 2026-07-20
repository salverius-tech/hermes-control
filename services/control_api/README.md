# Control API

FastAPI companion API for the Hermes Mobile Control app.

## Run locally

```bash
source .venv/Scripts/activate
CONTROL_API_TOKEN=dev-token CONTROL_API_DB_PATH=./data/control-api.db uvicorn services.control_api.main:app --host 0.0.0.0 --port 8787
```

## Endpoints

- `GET /health` — unauthenticated health check.
- `GET /tasks?include_archived=true` — list tasks, optionally including archived history.
- `POST /tasks` — create a queued Hermes task shell.
- `GET /tasks/{task_id}` — task detail.
- `POST /tasks/{task_id}/archive` — remove a terminal task from active task lists while retaining its history.
- `POST /tasks/{task_id}/restore` — restore an archived task to task lists.
- `GET /projects` — project summaries.
- `GET /agents` — agent statuses.
- `WS /ws/events?token=...` — initial snapshot and live task events.

All endpoints except `/health` require:

```text
Authorization: Bearer <CONTR...KEN>
```

Only completed, failed, canceled, rejected, or blocked tasks can be archived. Archiving is reversible and retains the task timeline.

## Current integration boundary

`HermesTaskService` records task state through the projection layer. Set `CONTROL_API_DB_PATH` to persist task state in SQLite across API restarts; omit it for in-memory development mode.

Real Hermes execution is intentionally behind the `HermesTaskService` seam. Set
`CONTROL_API_HERMES_PLUGIN_SOCKET` to use the structured Hermes Control Extension
bridge. The bridge is a local newline-delimited JSON protocol over a Unix socket.
Set `CONTROL_API_HERMES_PLUGIN_TOKEN` when the plugin requires a shared local
bridge token.
If the socket is not configured, set `CONTROL_API_HERMES_COMMAND` to use the CLI
compatibility executor. The prompt is sent on stdin, stdout/stderr lines are recorded
as live task progress, and active subprocesses are terminated when the task is canceled.

## Long-running task supervision

Plugin-backed tasks do not fail merely because they run for a fixed duration. The bridge
emits heartbeats while the Hermes child process is alive, including an explicit `quiet`
state when it has not produced new output. After `CONTROL_API_TASK_STALL_SECONDS`
of quiet-but-alive heartbeats (600 seconds by default), the task becomes
`attention_required` rather than failed; new output automatically returns it to `running`.
A missing bridge heartbeat is reported as an actionable connectivity/stall error. Set
`HERMES_CONTROL_EXTENSION_HARD_TIMEOUT_SECONDS` only when an explicit operator safety cap
is required; leave it unset for normal activity-aware execution.

## More detail

- API contract: `../../docs/API.md`
- Architecture and layer rules: `../../ARCHITECTURE.md`
- Test strategy: `../../TESTING.md`
- Operations runbook: `../../docs/OPERATIONS.md`
- Proxmox LXC + Caddy deployment: `../../docs/DEPLOYMENT.md`
