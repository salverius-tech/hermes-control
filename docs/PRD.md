# Product Requirements Document: Hermes Mobile Control

## 1. Summary

Hermes Mobile Control is an Android-first, iOS-ready mobile control surface for a local Hermes Agent installation. It pairs an Expo/React Native mobile app with a FastAPI companion Control API that runs near Hermes, typically in the same Proxmox LXC/container behind Caddy.

The product lets the user monitor Hermes task/project state, create new Hermes tasks from text or voice, review task progress/results, and manage connection settings from a phone without exposing lower-level infrastructure credentials to the mobile device.

## 2. Problem statement

Hermes Agent is powerful on a workstation/server, but mobile access currently requires direct terminal, desktop, or messaging-platform interaction. The user needs a dedicated mobile interface that can safely:

- reach the local Hermes installation over LAN/VPN/Tailscale/Caddy,
- submit tasks to Hermes,
- show task/project/agent status,
- provide live progress updates,
- support voice-to-task workflows,
- preserve a clean separation between mobile UX, control API, and Hermes execution internals.

## 3. Goals

### 3.1 Product goals

1. Provide a polished Android-first mobile app for controlling local Hermes infrastructure.
2. Keep the codebase iOS-ready where practical.
3. Support secure remote/local access through a companion Control API rather than direct mobile access to machine credentials.
4. Allow new Hermes tasks to be created from typed prompts and voice-derived prompts.
5. Show task lifecycle state, progress, results, projects, and agent status in an app-friendly UI.
6. Support live task updates through WebSockets with sensible fallback behavior.
7. Keep the backend layered so Hermes execution can evolve from CLI command execution to gateway/API integration without breaking mobile contracts.
8. Provide deployable infrastructure docs/examples for the user's Proxmox LXC + Caddy environment.

### 3.2 Engineering goals

1. Maintain explicit separation layers for backend domain, persistence, projection, application, transport, and mobile UI/state/API layers.
2. Preserve comprehensive verification across unit, integration, e2e, architecture-boundary, and physical-device paths.
3. Avoid dependency on the separate Agent Queue project unless explicitly introduced later.
4. Keep secrets out of source control and add pre-commit/pre-push secret gating.
5. Support autonomous incremental implementation with small, reviewable commits.

## 4. Non-goals

1. Do not make Agent Queue a dependency of this project.
2. Do not store infrastructure credentials, SSH keys, provider keys, Caddy credentials, or Proxmox credentials in the mobile app.
3. Do not expose raw Uvicorn publicly without TLS/reverse proxy and strong auth.
4. Do not require the mobile app to know Hermes internals or process-management details.
5. Do not require iOS production release support for the MVP, though the architecture should avoid Android-only assumptions where practical.
6. Do not build a full multi-user SaaS auth system for the MVP.

## 5. Users and primary scenarios

### 5.1 Primary user

A technical Hermes operator running Hermes Agent on local infrastructure and wanting phone-based control, monitoring, and task submission.

### 5.2 Core scenarios

1. **Configure connection:** User enters the Control API URL and token in mobile settings and verifies connectivity.
2. **Monitor system:** User opens the dashboard to see current task counts, agent/project status, and recent work.
3. **Create text task:** User types a prompt, chooses project/priority/options, submits it, and lands on the created task detail screen.
4. **Create voice task:** User records or dictates a prompt, edits the resulting text, then submits it as a Hermes task.
5. **Track execution:** User watches task status/progress/results update live without manual refresh.
6. **Handle approval:** User creates or receives tasks that require approval, then approves/rejects them from the control surface.
7. **Recover from failure:** User can view errors, retry tasks, cancel tasks where supported, and understand offline/token/network problems.
8. **Deploy backend:** User runs the Control API in the Hermes Proxmox LXC and exposes it privately/securely through Caddy.

## 6. Current capabilities

### 6.1 Mobile app

The current mobile app includes:

- Expo/React Native Android-first app shell.
- Dashboard, Tasks, Task Detail, Projects, New Task, and Settings screens.
- Bottom navigation with centered icon/label stacks and Settings as a header gear action.
- Secure settings flow for Control API URL/token.
- Diagnostics/test-connection behavior.
- Task creation with prompt templates, priority, project, approval requirement, and draft persistence.
- Voice prompt input support at the UI/feature layer.
- Shared UI primitives such as action buttons, metric cards, and status pills.
- Mobile tests for URL construction, settings, draft/prompt/template behavior, navigation, and architecture boundaries.
- Android release build/sideload and Maestro smoke-flow support where a device is available.

### 6.2 Control API

The current FastAPI companion API includes:

- `GET /health` unauthenticated health check.
- Bearer-token authentication for protected endpoints.
- Diagnostics endpoint.
- Task create/list/detail APIs.
- Project and agent read-model APIs.
- SQLite-backed optional task/event persistence.
- Task event timelines.
- WebSocket event fanout with initial snapshot and task update events.
- Approval/rejection flow for approval-required tasks.
- Cancel and retry task controls.
- Configurable local Hermes command execution through `CONTROL_API_HERMES_COMMAND`.
- Discord webhook notifications for approval requests and terminal task states.
- Tests covering domain models, auth, diagnostics, persistence, projection, task submission, task controls, approvals, websocket behavior, and mobile-style e2e flow.

### 6.3 Deployment/docs

The repo includes:

- Proxmox LXC + Caddy deployment guide.
- Example systemd unit for the Control API.
- Example Caddy route for reverse proxy/WebSocket support.
- Example production env file.
- Local operations guide.
- API contract documentation.
- Canonical verification runner.

## 7. MVP requirements

### 7.1 Mobile requirements

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| M-1 | Android app launches locally and can be installed on a physical Android device. | Must | Implemented |
| M-2 | User can configure Control API base URL and bearer token. | Must | Implemented |
| M-3 | User can test connection/diagnostics from Settings. | Must | Implemented |
| M-4 | Dashboard shows task/project/agent summary state. | Must | Implemented |
| M-5 | Task list groups or visually distinguishes queued/running/completed/failed-like states. | Must | Partially implemented |
| M-6 | Task detail shows status, prompt, progress/event log, result summary, and errors where available. | Must | Implemented/needs polish |
| M-7 | User can create a task from typed prompt. | Must | Implemented |
| M-8 | User can choose project, priority, template, and approval requirement when creating a task. | Should | Implemented |
| M-9 | User can create a task from voice-derived prompt and edit before submission. | Should | Partially implemented; needs hardening |
| M-10 | Mobile app consumes WebSocket task events and reconciles local UI state. | Must | Remaining |
| M-11 | Mobile app displays live connection state and recovers with reconnect/fallback behavior. | Must | Remaining |
| M-12 | Mobile app has clear offline, invalid-token, unreachable-host, and server-error states. | Must | Remaining |
| M-13 | Mobile app persists useful drafts/settings safely. | Should | Implemented/needs offline polish |
| M-14 | Physical-device visual and Maestro verification covers core app navigation and task creation. | Should | Partially implemented; device required |

### 7.2 Control API requirements

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| A-1 | Expose health endpoint without auth. | Must | Implemented |
| A-2 | Protect control endpoints with bearer-token auth. | Must | Implemented |
| A-3 | Support task creation with validation. | Must | Implemented |
| A-4 | Persist task state/events optionally with SQLite. | Must | Implemented |
| A-5 | Expose task list/detail/event endpoints. | Must | Implemented |
| A-6 | Expose project and agent read models. | Must | Implemented |
| A-7 | Broadcast live events over WebSocket. | Must | Implemented |
| A-8 | Support approval-required tasks. | Should | Implemented |
| A-9 | Support task cancel/retry controls. | Should | Implemented |
| A-10 | Execute submitted tasks through configurable local Hermes command. | Must | Implemented |
| A-11 | Keep Hermes integration behind a replaceable application seam. | Must | Implemented |
| A-12 | Provide diagnostics for storage/execution/notification modes. | Should | Implemented |
| A-13 | Send optional Discord notifications for important task states. | Could | Implemented |
| A-14 | Enforce concurrency/rate limiting for multiple devices/users. | Should | Remaining |

### 7.3 Deployment requirements

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| D-1 | Provide LXC-friendly install/deployment guide. | Must | Implemented |
| D-2 | Provide systemd service example. | Must | Implemented |
| D-3 | Bind Uvicorn locally and expose through Caddy. | Must | Documented |
| D-4 | Support WebSocket reverse proxy through Caddy. | Must | Documented |
| D-5 | Document token generation/rotation. | Must | Implemented |
| D-6 | Validate real phone → Caddy → LXC → Hermes flow. | Must | Deferred; requires user's device/LXC access |

### 7.4 Security/release requirements

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| S-1 | Keep real tokens, webhooks, keys, and env files out of git. | Must | Partially implemented with `.gitignore`; needs gating |
| S-2 | Add pre-commit/pre-push secret scanning gate. | Must | Remaining |
| S-3 | Use placeholders in docs/examples instead of real token-shaped values. | Must | In progress |
| S-4 | Run secret scanner before first push/publish. | Must | Process requirement |
| S-5 | Mobile stores only Control API URL/token. | Must | Implemented by design |
| S-6 | Production exposure uses TLS/private network guidance. | Must | Documented |


### 7.5 Enhancement requirements

These requirements extend the MVP into a richer mobile operator console. They should be implemented after the immediate safety and live-update work unless they are prerequisites for a selected slice.

#### 7.5.1 Real-time streaming integration

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| E-STREAM-1 | Implement full-duplex streaming between Control API and Hermes Agent. | Should | Proposed |
| E-STREAM-2 | Support token-level output streaming for chat/task execution. | Should | Proposed |
| E-STREAM-3 | Stream Hermes tool events, state transitions, and intermediate outputs. | Should | Proposed |
| E-STREAM-4 | Add a mobile live console view for running tasks. | Should | Proposed |
| E-STREAM-5 | Render token streams incrementally in the mobile task detail UI. | Should | Proposed |
| E-STREAM-6 | Merge token, event, and state streams into the task event timeline. | Should | Proposed |
| E-STREAM-7 | Persist stream events in SQLite for task replay/history. | Should | Proposed |

Implementation direction:

- Add a `/stream` WebSocket endpoint with multiplexed logical channels:
  - `tokens`
  - `events`
  - `state`
- Use a message envelope shaped as:

```json
{ "type": "tokens", "task_id": "task-...", "payload": {}, "ts": "2026-07-12T00:00:00Z" }
```

- Keep stream payloads typed and versionable.
- Mobile reconciliation should merge stream messages with existing task state without requiring a full refetch after every token.

#### 7.5.2 Offline-first task queue

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| E-OFFLINE-1 | Allow tasks to be created while the phone is offline. | Should | Proposed |
| E-OFFLINE-2 | Maintain a local task queue with `pending`, `retrying`, and `submitted` states. | Should | Proposed |
| E-OFFLINE-3 | Automatically retry queued tasks when connectivity returns. | Should | Proposed |
| E-OFFLINE-4 | Use exponential backoff with jitter for submission retries. | Should | Proposed |
| E-OFFLINE-5 | Reconcile local queued tasks with the server task list after reconnect. | Should | Proposed |
| E-OFFLINE-6 | Show clear UI indicators for locally pending/retrying/submitted tasks. | Should | Proposed |
| E-OFFLINE-7 | Store drafts and queued task metadata in appropriate local storage, with sensitive values kept in secure storage. | Should | Proposed |

Conflict resolution direction:

- Local optimistic state is temporary.
- Server-created task records become authoritative once a task is accepted.
- If submission outcome is unknown after reconnect, reconcile by client-generated idempotency key before creating duplicates.

#### 7.5.3 Mobile approval workflow

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| E-APPROVAL-1 | Send push notifications for tasks requiring approval. | Could | Proposed |
| E-APPROVAL-2 | Support quick approval/rejection actions from the notification shade. | Could | Proposed |
| E-APPROVAL-3 | Support lock-screen approval/rejection where platform policy allows. | Could | Proposed |
| E-APPROVAL-4 | Store an approval audit trail in Control API task events. | Should | Partially implemented; needs richer actor/device metadata |
| E-APPROVAL-5 | Add an approval subscription channel for mobile clients. | Could | Proposed |

Implementation direction:

- Add an `/approvals/subscribe` WebSocket channel or fold approval notifications into the multiplexed `/stream` model.
- Integrate FCM/Expo push notifications with deep links to the task detail screen.
- Mobile quick actions should call existing approval endpoints:
  - `POST /tasks/{task_id}/approve`
  - `POST /tasks/{task_id}/reject`
- Control API should log approval actor, device/source, timestamp, and reason/comment where available.

#### 7.5.4 Project-level operator UX

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| E-PROJECT-1 | Add a project dashboard with task grouping and project metrics. | Should | Proposed |
| E-PROJECT-2 | Show recent project events. | Should | Proposed |
| E-PROJECT-3 | Show per-project health indicators. | Should | Proposed |
| E-PROJECT-4 | Provide a safe read-only file/log browser for project artifacts/logs. | Could | Proposed |

Implementation direction:

- Extend Control API with:
  - `GET /projects/{project_id}/metrics`
  - `GET /projects/{project_id}/events`
  - `GET /projects/{project_id}/files`
- File/log browsing must be read-only, path-confined, and safe against traversal.
- Mobile UI should reuse list, timeline, and metric-card primitives.

#### 7.5.5 Hermes-side plugin architecture

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| E-PLUGIN-1 | Replace or augment CLI wrapping with a structured Hermes-side plugin. | Could | Proposed |
| E-PLUGIN-2 | Emit structured task lifecycle events directly to Control API. | Could | Proposed |
| E-PLUGIN-3 | Emit structured tool-call reporting and intermediate outputs. | Could | Proposed |
| E-PLUGIN-4 | Keep CLI execution mode as fallback. | Must | Required for compatibility |

Implementation direction:

- Implement a Hermes plugin that hooks into task lifecycle events and emits JSON envelopes.
- Control API should receive plugin events via a local IPC mechanism, pipe, or local authenticated callback.
- The mobile-facing API should remain stable whether events originate from CLI wrapping or the plugin.

#### 7.5.6 WebSocket reconciliation model

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| E-RECON-1 | Deterministically merge local optimistic state, server authoritative state, and stream events. | Must | Remaining |
| E-RECON-2 | Handle out-of-order events and partial connectivity. | Must | Remaining |
| E-RECON-3 | Use monotonic sequence numbers, vector clocks, or another explicit ordering model. | Should | Proposed |
| E-RECON-4 | Provide a unified mobile reducer for task state. | Must | Remaining |
| E-RECON-5 | Replace local optimistic updates when server confirmation arrives. | Must | Remaining |

Reconciliation rules:

- Server snapshots and explicit server state are authoritative.
- Stream events append to the timeline when not duplicated.
- Local optimistic updates are marked pending until confirmed/rejected.
- Out-of-order events are ordered by server sequence when available and by timestamp only as a fallback.
- Refetch is the recovery path when sequence gaps are detected.

#### 7.5.7 End-to-end deployment validation

| ID | Requirement | Priority | Status |
|---|---|---:|---|
| E-E2E-1 | Validate full chain: Mobile -> Caddy -> LXC -> Control API -> Hermes. | Must | Deferred; requires user's phone/LXC environment |
| E-E2E-2 | Validate TLS behavior through the production/private hostname. | Must | Deferred; requires environment |
| E-E2E-3 | Validate token auth through Caddy. | Must | Deferred; requires environment |
| E-E2E-4 | Validate WebSocket stability through Caddy. | Must | Deferred; requires environment |
| E-E2E-5 | Validate real task execution through Hermes. | Must | Deferred; requires environment |
| E-E2E-6 | Validate approval flow and Discord notifications in deployed mode. | Should | Deferred; requires environment |

Implementation direction:

- Add a `verify_e2e.py` script or extend `scripts/verify.py` with a deployment target mode.
- The script should run synthetic tasks, validate event flow, and check WebSocket continuity.
- Add Maestro flows for offline mode, approval notifications, and stream rendering once a physical device is available.

## 8. Later requirements / roadmap

1. iOS build and physical-device validation.
2. Full-duplex streaming with token-level output, tool events, state transitions, and replayable event history.
3. Offline-first mobile task queue with retry/reconciliation.
4. Push notifications for completed/failed/approval-needed tasks, including approval quick actions where supported.
5. Richer project switching, saved task templates, and project-level operator dashboard.
6. Safe read-only project file/log browser.
7. Live interactive chat sessions with a Hermes agent.
8. File/image/audio attachments to prompts.
9. Pairing flow similar to Hermes gateway approval/pairing.
10. Multi-agent orchestration dashboard.
11. Multiple users/devices with stronger auth, rate limits, and audit logs.
12. Rich artifact browsing for generated files, links, screenshots, and media.
13. Structured Hermes-side plugin in place of or alongside CLI command execution.
14. Optional integration with future Hermes API/gateway surfaces in place of CLI command execution.

## 9. UX requirements

1. Dark-first, modern, card-based interface with readable typography.
2. Bottom navigation should avoid redundant controls and keep icon/label stacks centered and evenly spaced.
3. Settings should be reachable from a gear-only header action rather than duplicative bottom navigation controls.
4. New Task should feel like a primary action and support fast typed or voice capture.
5. Status should be visually obvious with consistent color tokens:
   - queued: neutral/blue,
   - awaiting approval: amber/purple,
   - running: violet/green,
   - completed: green,
   - failed/rejected/canceled: red/neutral as appropriate.
6. Error messages should distinguish invalid token, unreachable host, TLS/cert issue, server error, and offline state.
7. Task detail should make progress logs/results readable on small phones.
8. UI polish should be physically reviewed on an actual Android device before treating mobile UX work as complete.

## 10. Architecture requirements

1. Mobile screens compose UI, state, and API calls but should not own reusable business logic.
2. Mobile API helpers should remain typed and isolated under `apps/mobile/src/api/`.
3. Pure task/request/template helpers should remain testable outside React Native UI.
4. Backend domain models must not import FastAPI, storage, WebSocket, or UI concerns.
5. Persistence must not know about transport or mobile clients.
6. Projection/read-model logic must remain separate from route handlers.
7. Hermes execution must remain behind `HermesTaskService`/adapter seams.
8. Route handlers should remain thin composition/transport boundaries.
9. Boundary tests must guard the dependency rules.
10. Agent Queue remains outside the dependency graph unless explicitly introduced later.

See `../ARCHITECTURE.md` for the detailed layer map.

## 11. API/product contract requirements

The mobile-facing API must continue to support:

- health and diagnostics,
- task create/list/detail,
- task event timeline,
- project summaries,
- agent summaries,
- approval/reject,
- cancel/retry,
- WebSocket snapshot and task update events.

Future streaming contracts should support multiplexed messages with an envelope of:

```json
{ "type": "events", "task_id": "task-...", "payload": {}, "ts": "2026-07-12T00:00:00Z" }
```

If ordering semantics are added, the envelope should also include a server-issued sequence field such as `seq`.

The API contract is documented in `API.md`. Contract-breaking changes require corresponding mobile updates and tests in the same change set.

## 12. Verification requirements

Every implementation slice should run the narrow relevant checks plus canonical verification when practical.

Required non-device checks:

```bash
python scripts/verify.py
```

Backend-focused checks:

```bash
python -m pytest services/control_api/tests -v
```

Mobile-focused checks:

```bash
cd apps/mobile
npm run typecheck
npm run test:unit
```

Device/deployment checks, deferred until the user can provide phone/LXC access:

```bash
python scripts/verify.py --android --sideload
python scripts/verify.py --maestro
```

Production end-to-end validation must eventually prove:

```text
physical phone → Caddy HTTPS/private hostname → Proxmox LXC Control API → Hermes command/API → task status/result back to phone
```

Enhanced deployment validation should additionally cover TLS validation, token auth, WebSocket continuity, streaming output, approval flow, Discord notifications, and offline/reconnect behavior.

## 13. Open decisions

1. Should the long-term Hermes integration remain CLI-based, or migrate to a Hermes API/gateway/server interface once stable?
2. What private network model should be preferred for normal use: LAN, Tailscale, WireGuard, Caddy-only hostname, or a combination?
3. Should MVP auth stay static-token based, or move to a pairing/rotating-token model before broader use?
4. Which voice transcription provider/package should be the long-term default across Android and iOS?
5. Should notifications be handled through Expo push, Discord, ntfy, Hermes gateway delivery, or several adapters?
6. What task concurrency limit is appropriate for the user's Hermes LXC resources?
7. What data retention policy should apply to task prompts, logs, events, and results?
8. Should `/approvals/subscribe` be a separate WebSocket channel or part of a unified multiplexed `/stream` endpoint?
9. Should stream ordering use global monotonic sequence numbers, per-task sequence numbers, vector clocks, or another model?
10. Which mobile push path should be preferred: native FCM, Expo notifications, Hermes gateway delivery, or an adapter layer?
11. What project directories/log paths are safe to expose through a read-only browser, and how should path allowlists be configured?
12. What IPC mechanism should a future Hermes-side plugin use to emit structured events to the Control API?

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Mobile device cannot reach `localhost` | Use LAN IP/Tailscale/private Caddy hostname; document clearly. |
| Control API exposure creates infrastructure risk | Bind Uvicorn locally, use Caddy/TLS/private network, strong token, and avoid storing infrastructure credentials in mobile. |
| Secrets accidentally enter git history | Add pre-commit/pre-push gitleaks or equivalent gate and run scans before publishing. |
| Hermes CLI execution blocks or overloads host | Keep execution behind adapter seam; add concurrency/rate limits and timeouts. |
| WebSocket is unreliable on mobile networks | Add reconnect/backoff, visible connection state, and polling fallback. |
| Stream events arrive out of order or duplicate | Add server sequence numbers, deduplication keys, gap detection, and authoritative snapshot refetch. |
| Offline submissions create duplicate tasks | Use client idempotency keys and reconcile local queued tasks with server state on reconnect. |
| Notification quick actions accidentally approve the wrong task | Use explicit task ids, confirmation affordances where practical, audit logs, and deep links to review state. |
| Read-only file/log browser exposes sensitive files | Restrict to explicit project allowlists, block traversal, redact secrets where possible, and test denial paths. |
| Hermes plugin API changes or is unavailable | Keep CLI mode as a compatibility fallback and keep mobile-facing contracts stable. |
| Voice packages differ across Android/iOS | Abstract voice provider and verify Android first; treat iOS as later milestone. |
| Product docs drift from implementation | Keep PRD status table updated when significant capabilities land. |
| Physical-device issues are missed by unit tests | Defer device-required tasks until phone is available, then run release sideload and Maestro flows. |

## 15. Immediate remaining work

The remaining non-device implementation priorities are:

1. Add pre-commit/pre-push secret scanning gate.
2. Implement deterministic mobile WebSocket reconciliation and connection state UI.
3. Improve mobile offline/error-state behavior, including the first version of a local pending-task queue.
4. Add stream/reconciliation data-model foundations so future token/event/state streaming does not require rewriting task state management.
5. Harden voice UX permissions, unavailable-provider handling, and edit-before-submit states.
6. Continue mobile UI polish and shared component cleanup.
7. Add backend concurrency/rate-limit guardrails for submitted Hermes tasks.
8. Add richer approval audit metadata in Control API events.

Deferred until the user can provide the phone/LXC environment:

1. Physical phone visual QA.
2. Maestro/device flows that require a connected phone.
3. Real phone → Caddy → LXC → Hermes end-to-end validation.
4. Push notification quick actions and lock-screen approval validation.
5. Deployed streaming/WebSocket stability validation through Caddy.
