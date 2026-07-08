# Companion API Contract

Base URL defaults to `http://127.0.0.1:8787` for local development. Physical Android devices usually need the Windows host LAN IP or Tailscale hostname instead of loopback.

## Authentication

All endpoints except `GET /health` require a bearer token:

```text
Authorization: Bearer <CONTROL_API_TOKEN>
```

WebSocket clients pass the same token as a query parameter:

```text
/ws/events?token=<CONTROL_API_TOKEN>
```

Do not commit real token values. `.env.example` uses placeholders only.

## REST endpoints

### `GET /health`

Unauthenticated health check.

Response:

```json
{ "ok": true }
```

### `GET /tasks`

Returns tasks sorted by newest creation time first.

Auth: required.

Response:

```json
[
  {
    "task_id": "task-...",
    "title": "Check Hermes status",
    "prompt": "Check Hermes status",
    "status": "queued",
    "project_id": "default",
    "source": "mobile",
    "priority": "normal",
    "created_at": "2026-07-08T00:00:00Z",
    "updated_at": "2026-07-08T00:00:00Z",
    "progress_log": [],
    "result_summary": null,
    "error": null
  }
]
```

### `POST /tasks`

Creates a queued task shell.

Auth: required.

Request:

```json
{
  "prompt": "Check Hermes status",
  "project_id": "default",
  "source": "mobile",
  "priority": "normal"
}
```

Validation:

- `prompt` must not be blank.
- `project_id` must not be blank.
- `priority` must be `low`, `normal`, or `high`.

Response: `201 Created` with a `TaskSummary`.

### `GET /tasks/{task_id}`

Returns a task by id.

Auth: required.

Errors:

- `404` when the task id is unknown.

### `GET /projects`

Returns project summaries derived from task counts. If no tasks exist, returns a default project shell.

Auth: required.

### `GET /agents`

Returns known companion-agent status. Current MVP returns a local `hermes-agent` placeholder until real Hermes execution is wired.

Auth: required.

## WebSocket events

### Connect

```text
GET ws://<host>/ws/events?token=<CONTROL_API_TOKEN>
```

Invalid or missing tokens are rejected with policy violation close code `1008`.

### Initial snapshot

Sent immediately after connect:

```json
{
  "type": "snapshot",
  "tasks": [],
  "projects": [],
  "agents": []
}
```

### Task created

Broadcast after successful `POST /tasks`:

```json
{
  "type": "task.created",
  "task": { "task_id": "task-..." }
}
```

## Persistence mode

By default, tasks are in-memory and disappear when the API process restarts.

Set `CONTROL_API_DB_PATH` to enable SQLite persistence:

```bash
CONTROL_API_DB_PATH=./data/control-api.db
```

The database path is runtime data and is ignored by git.
