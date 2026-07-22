# Native-store and route mapping

> **Status:** Repository-verified implementation contract, 2026-07-21.
>
> This document is the checked-in authority for the Control API's native-store
> boundary. It records what the source and native-schema fixtures prove. It is
> not a claim that a deployed service has been inspected.

## Scope and evidence limit

The implementation resolves the configured Hermes home from
`CONTROL_API_HERMES_HOME` (default: `~/.hermes`) and projects the two SQLite
files below. The schemas in this document are verified by the native SQLite
fixtures in `services/control_api/tests/test_native_project_integration.py` and
`services/control_api/tests/test_workspace.py`, not by an installed Hermes
profile.

**No live deployed profile or service-account inspection was available.** P0.1
therefore remains unverified and is deliberately not completed by this
specification. A deployment review must still establish the effective service
account, profile/home, file access, and diagnostics result before this mapping
can be asserted for a live service.

## Stores and ownership

| Store | Canonical owner | Repository-verified records | Control API use | Not authoritative for |
|---|---|---|---|---|
| Hermes `projects.db` | Hermes profile | `projects`; `project_folders` | Native project list/detail/create/update/archive/folder membership and selected-project containment | Task attempts, task events, Hermes sessions |
| Hermes `state.db` | Hermes profile | `sessions` | Session list and selected-project/session containment validation | Project identity or task lifecycle |
| Control API task store | Control API | `tasks`; `task_events` in configured `CONTROL_API_DB_PATH`, or in-memory projection when unset | Immutable task attempts, event/audit history, retry/continuation lineage, idempotency | Native project or session identity |
| Managed workspace filesystem | Workspace owner | workspace files and optional `hermes-project.yaml` | Managed-project bootstrap and recovery descriptor | Normal-operation native registration authority |

The managed-workspace manifest is portable recovery metadata. It does not
replace Hermes `projects.db` while the configured Hermes profile is available.

## Native fixture schema contract

The adapter in `services/control_api/workspace.py` currently reads these
columns. These are the supported repository contract; schema drift in a live
Hermes installation must be detected and reconciled separately.

### Hermes `projects.db`

| Table | Columns read/written by the adapter | Meaning in this API |
|---|---|---|
| `projects` | `id`, `slug`, `name`, `description`, `primary_path`, `created_at`, `archived` | `slug` is the public `project_id` when present; otherwise `id`. `primary_path` is the default execution folder. |
| `project_folders` | `project_id`, `path`, `label`, `is_primary`, `added_at` | Project folder membership. The adapter orders list results by `is_primary DESC, path`. |

The API accepts either the native row `id` or `slug` when locating a project,
but emits `slug` when it exists. New managed projects explicitly provide a
stable slug. A project must have an existing primary folder for task
submission.

### Hermes `state.db`

| Table | Columns read by the adapter | Meaning in this API |
|---|---|---|
| `sessions` | `id`, `title`, `source`, `started_at`, `ended_at`, `cwd`, `parent_session_id`, `archived` | A session is associated with a selected project only when its `cwd` is contained by one of that project's registered folders. Archived or out-of-project sessions cannot be resumed. |

`GET /sessions?project_id=…` filters by this containment relationship before
applying its limit. Session timestamps are converted from native epoch values
to API timestamps.

## Route-to-authority mapping

### Project and session routes

| Route | Primary authority | Projection/validation | Behaviour when native store is unavailable or record is unknown |
|---|---|---|---|
| `GET /projects` | Hermes `projects.db` | `TaskProjection` overlays Control API task counts on native project IDs only. | `503` in normal mode when the native project store is unavailable. |
| `GET /projects/{project_id}` | Hermes `projects.db` plus task-count projection | The detail must be one of the native projection's IDs. | `404` for an unknown ID. |
| `POST /projects` | Hermes `projects.db`; managed workspace filesystem for `workspace`/`clone` origins | Validates project roots; managed flows write a recovery manifest and register native folders. | `400` for invalid/native creation errors; `503` when managed root is required but unavailable. |
| `PATCH /projects/{project_id}` | Hermes `projects.db` | Managed manifest is synchronized only for an existing managed workspace. | `404` if project is unknown. |
| `POST /projects/{project_id}/repository` | Managed workspace filesystem and Hermes `projects.db` | Clones into `repo/`, registers it as an additional native folder, and synchronizes the manifest. | `503` without managed root; `400` for invalid/failed operation. |
| `POST` / `DELETE /projects/{project_id}/folders` | Hermes `projects.db` | Folder path must be valid and within configured approved roots; managed manifest mirrors an existing managed project. | `404` if project is unknown; `400` for invalid operation. |
| `GET /projects/{project_id}/metrics` | Control API task store | Native project existence is checked through the native-backed project projection first. | `404` if project is unknown. |
| `GET /projects/{project_id}/events` | Control API task store | Native project existence is checked first; returns events for attempts associated with that project. | `404` if project is unknown. |
| `GET /projects/{project_id}/files` | Workspace filesystem under folders from Hermes `projects.db` | `path` must stay within each registered project folder; endpoint is read-only. | `404` if project is unknown; `400` for traversal/non-directory path. |
| `GET /sessions` | Hermes `state.db` | Optional `project_id` is resolved through Hermes `projects.db` and uses `cwd` containment. | `503` if native project integration is unavailable; empty list when `state.db` does not exist. |

### Task-submission and linked-attempt routes

| Route | Attempt/event authority | Native authority consulted before submission | Resulting context |
|---|---|---|---|
| `POST /tasks` | Control API task store/projection | Hermes `projects.db` validates the submitted project, archive state, primary/folder containment; Hermes `state.db` validates an optional session. | Saves an immutable task attempt with canonical native `project_id`, validated `execution_folder`, and optional `session_id`. |
| `POST /tasks/{task_id}/retry` | Existing and new attempts in Control API task store | Re-resolves the original project's native project/session context. | New linked attempt preserves prompt/project/priority/source/approval/session where valid. |
| `POST /tasks/{task_id}/continue` | Existing and new attempts in Control API task store | Requires and re-validates the original Hermes session and its `cwd`. | New `continuation` attempt uses the same native session and its validated working directory. |
| `POST /tasks/{task_id}/edit-retry` | Existing and new attempts in Control API task store | Re-resolves the original native project and a valid execution folder. | New `edited_retry` attempt deliberately has no session unless a later executor establishes one. |
| `POST /tasks/{task_id}/new-session` | Existing and new attempts in Control API task store | Re-resolves the original native project and execution folder. | New independent `retry` attempt has no prior session. |
| `POST /tasks/{task_id}/approve` | Control API task store/events | No new project lookup at route entry; execution request uses the stored canonical context. | Records `approval.audit` and starts the existing attempt. |
| `POST /tasks/{task_id}/reject`, `/cancel`, `/archive`, `/restore` | Control API task store/events | No native mutation. | Update only Control API attempt state and events. |
| `GET /tasks/{task_id}/environment` | Control API task store plus live native/executor checks | Re-validates the stored task's native project/session context. | Read-only readiness result; it never retries execution. |

An `Idempotency-Key` on a creation or linked-attempt submission is stored with
the Control API attempt. Reusing it returns that same attempt and does not
write another task record or invoke another submission.

## Synthetic task-derived project-ID compatibility

Normal and deployed operation is **strict native mode**:

- `CONTROL_API_ALLOW_SYNTHETIC_PROJECTS` is unset or not `1`.
- `/projects` only exposes records from Hermes `projects.db` (with task counts
overlaid by the Control API projection).
- `default`, task-derived IDs, and any other ID absent from the native project
store are not materialized as projects.
- Task submission with one of those IDs returns `400` with an `Unknown Hermes
project: <id>` detail. It does not silently select an active project, create a
project, or migrate stored work.

`CONTROL_API_ALLOW_SYNTHETIC_PROJECTS=1` is a development-only fixture
compatibility mode. It may expose task-derived projection entries only when no
native workspace is configured. It is not a deployment migration mechanism and
must not be enabled in a deployed service.

### Client migration protocol

1. On upgrade, discard any cached selection that is not returned by fresh
   authenticated `GET /projects`.
2. Require the operator to select a returned non-archived native `project_id`.
3. Submit new work with that ID. Preserve legacy task history as historical
   Control API attempts; do not relabel it automatically.
4. If a submission returns `400 Unknown Hermes project`, refresh `/projects`
   and ask for a new selection. Treat `503` as a native integration outage,
   not an empty project list.

There is no server-side automatic ID migration or fallback because choosing a
replacement project could execute work in an unintended filesystem context.
