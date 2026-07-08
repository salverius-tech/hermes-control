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

```json
{ "ok": true }
```

### `GET /diagnostics`

Returns operational metadata for the companion API.

Auth: required.

```json
{
  "version": "0.1.0",
  "storage": "sqlite",
  "execution_mode": "command",
  "websocket_path": "/ws/events"
}
```

### `GET /tasks`

Returns tasks sorted by newest creation time first.

Auth: required.

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

Creates a queued task and starts execution through the configured Hermes adapter. If `CONTROL_API_HERMES_COMMAND` is unset, the task completes through an explicit unconfigured adapter so clients can exercise the full lifecycle.

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

Response: `201 Created` with the initial queued `TaskSummary`.

### `GET /tasks/{task_id}`

Returns a task by id.

Auth: required.

Errors:

- `404` when the task id is unknown.

### `GET /tasks/{task_id}/events`

Returns the persisted event timeline for a task.

Auth: required.

```json
[
  {
    "task_id": "task-...",
    "event_type": "task.created",
    "status": "queued",
    "message": "Task queued",
    "created_at": "2026-07-08T00:00:00Z"
  }
]
```

Errors:

- `404` when the task id is unknown.

### `GET /projects`

Returns project summaries derived from task counts. If no tasks exist, returns a default project shell.

Auth: required.

### `GET /agents`

Returns known companion-agent status. Current response includes the local `hermes-agent` until deeper Hermes agent discovery is configured.

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

Broadcast after successful `POST /tasks` before execution updates:

```json
{
  "type": "task.created",
  "task": { "task_id": "task-...", "status": "queued" }
}
```

### Task updated

Broadcast when execution starts, records progress, completes, or fails:

```json
{
  "type": "task.updated",
  "task": { "task_id": "task-...", "status": "running" }
}
```

## Persistence mode

By default, tasks and events are in-memory and disappear when the API process restarts.

Set `CONTROL_API_DB_PATH` to enable SQLite persistence:

```bash
CONTROL_API_DB_PATH=./data/control-api.db
```

The database path is runtime data and is ignored by git.

## Hermes execution mode

Set `CONTROL_API_HERMES_COMMAND` to run a local Hermes command for submitted tasks. The prompt is sent on stdin rather than interpolated into the command line.

```bash
CONTROL_API_HERMES_COMMAND='hermes chat -q'
```

When unset, the API uses an unconfigured adapter that records a completed lifecycle explaining that real Hermes execution has not been configured.
