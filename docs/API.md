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
  "schema_version": "1",
  "execution_mode": "command",
  "notification_mode": "discord",
  "websocket_path": "/ws/events",
  "hermes_home_available": "true",
  "bridge_configured": "true",
  "bridge_socket_available": "true",
  "executor_ready": "true"
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

Creates a queued task and starts execution through the configured Hermes adapter. When neither `CONTROL_API_HERMES_COMMAND` nor `CONTROL_API_HERMES_PLUGIN_SOCKET` is configured, the task becomes blocked with a configuration blocker instead of being reported as completed.

Auth: required.

Request:

```json
{
  "prompt": "Check Hermes status",
  "project_id": "default",
  "source": "mobile",
  "priority": "normal",
  "requires_approval": false
}
```

Validation:

- `prompt` must not be blank.
- `project_id` must not be blank.
- `priority` must be `low`, `normal`, or `high`.
- `requires_approval` defaults to `false`; when `true`, the task starts as `awaiting_approval` and is not executed until approved.

Response: `201 Created` with the initial queued `TaskSummary`.

### `POST /tasks/{task_id}/approve`

Approves a task in `awaiting_approval`, records `task.approved`, broadcasts `task.updated`, and starts execution through the configured adapter.

Auth: required.

Response: `200 OK` with the updated `TaskSummary` whose status moves back to `queued` before execution begins.

Errors:

- `404` when the task id is unknown.

### `POST /tasks/{task_id}/reject`

Rejects an approval-required task, records `task.rejected`, and broadcasts `task.updated`.

Auth: required.

Response: `200 OK` with the updated `TaskSummary` whose `status` is `rejected`.

Errors:

- `404` when the task id is unknown.

### `GET /tasks/{task_id}`

Returns a task by id.

Auth: required.

Errors:

- `404` when the task id is unknown.

### `POST /tasks/{task_id}/cancel`

Marks an existing task as canceled, records a `task.canceled` event, and broadcasts `task.updated`.

Auth: required.

Response: `200 OK` with the updated `TaskSummary` whose `status` is `canceled`.

Errors:

- `404` when the task id is unknown.

### `POST /tasks/{task_id}/retry`

Creates a new task using the original task prompt, project, priority, source, and approval requirement. Tasks that still require approval remain `awaiting_approval`; other tasks start through the configured execution adapter.

Auth: required.

Response: `201 Created` with the new queued `TaskSummary`.

Errors:

- `404` when the original task id is unknown.

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

### `GET /attention`

Returns tasks requiring operator attention: approval requests, blockers, and failures.

Auth: required.

The response is a list of `TaskSummary` objects. Clients may persist local read state keyed by `task_id` and `updated_at`; the API currently exposes task attention state, not notification read state.

### `GET /projects`

Returns Hermes-native project summaries when `CONTROL_API_HERMES_HOME` is configured. Task-derived projects are retained as a fallback for development and tests.

Auth: required.

Use `?include_archived=true` to include archived Hermes projects.

Project selection is request context only. It does not call `hermes project use` or modify Hermes' global active project.

### `GET /projects/{project_id}`

Returns one Hermes-native project, including its primary folder and folder membership.

### `POST /projects`

Creates a Hermes-native project. Folder paths are validated against `CONTROL_API_PROJECT_ROOTS`.

### `PATCH /projects/{project_id}`

Renames, archives/restores, or changes the primary folder for a project.

### `POST /projects/{project_id}/folders`

Adds a validated folder to a project.

### `DELETE /projects/{project_id}/folders`

Removes a validated folder from a project.

### `GET /folders`

Lists directories available under the configured approved roots. Pass `path` to browse a permitted directory.

### `GET /sessions`

Returns Hermes session summaries. Pass `project_id` to filter sessions by project context.
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

Broadcast when execution starts, records progress, completes, fails, waits for approval, is approved/rejected, or is canceled:

```json
{
  "type": "task.updated",
  "task": { "task_id": "task-...", "status": "running" }
}
```

## Hermes Control Extension bridge

The preferred structured integration is the Hermes Control Extension. The
Control API connects to its local Unix-socket bridge when
`CONTROL_API_HERMES_PLUGIN_SOCKET` is set. The bridge uses versioned
newline-delimited JSON and carries task submissions plus structured progress,
completion, failure, and future tool/lifecycle events.

The extension is one installable operator-facing bundle, but the Hermes-side
plugin and Control API normally run as separate supervised processes. This
keeps mobile auth, persistence, and WebSocket handling out of the Hermes
process. The CLI executor remains available as a fallback.

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

## Notifications

Set `CONTROL_API_DISCORD_WEBHOOK_URL` to send best-effort Discord webhook notifications for approval requests, task completions, task failures, cancellations, and rejections.

```bash
CONTROL_API_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/[REDACTED]'
```

Webhook URLs are secrets. Keep them out of source control. Notification failures are swallowed so task execution and API responses are not blocked by Discord availability.
