# Mobile Hermes Control App Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a modern Android-first, iOS-ready mobile app that connects to the user's local Hermes infrastructure to monitor running tasks/projects and start new Hermes tasks from text or voice.

**Architecture:** Use a React Native/Expo mobile client for cross-platform Android/iOS. Add a local companion API service in this repo that exposes safe HTTPS/WebSocket endpoints to the app and integrates with Hermes-local control surfaces when those are defined. Do not assume any dependency on the separate Agent Queue project at this time.

**Tech Stack:** Expo React Native + TypeScript, Expo Router, React Query, Zustand, NativeWind/Tamagui or React Native Paper for UI, Expo AV/Speech or platform speech APIs for voice input, FastAPI + WebSocket/SSE backend, optional Hermes CLI/gateway/API integration.

---

## Current Context

This new mobile-control project lives at `C:\Dev\HermesMobileControl`.

The Agent Queue workspace at `C:\Dev\AgentQueue` is a separate project and is **not** a dependency of the Hermes Mobile App at this time. Do not import from it, reference its RabbitMQ exchange, or build the mobile app around Agent Queue assumptions unless that dependency is explicitly introduced later.

## Product Requirements

The canonical product requirements, MVP/later roadmap, current capability status, risks, and remaining work now live in `docs/PRD.md`.

This historical implementation plan is retained as build history and task breakdown only.

## Recommended High-Level Design

```text
Mobile App (Expo RN)
  ├─ REST: login, list projects, create task, task details
  ├─ WebSocket/SSE: live task/project/agent events
  └─ Voice: record/transcribe prompt, then submit task

Companion API (FastAPI)
  ├─ Auth/token validation
  ├─ Starts/prompts Hermes through the chosen local integration surface
  ├─ Tracks task/session/project status from Hermes-facing APIs/processes
  ├─ Maintains in-memory + optional SQLite task projection
  └─ Optional Hermes launcher: hermes chat -q / gateway API / local API bridge

Hermes Agent(s)
  ├─ CLI/gateway/API/server integration to be selected
  └─ Agents expose status/task progress through the companion API projection
```

## Open Design Decisions

Resolve these before coding beyond scaffolding:

1. **Direct Hermes startup mechanism:** Should the companion API actively run `hermes chat -q ...`, call a Hermes API/gateway, or use another local integration surface for each prompt?
2. **Network access:** LAN only, Tailscale/WireGuard, Cloudflare Tunnel, or Hermes gateway/API-server adapter?
3. **Auth model:** Static bearer token for home LAN MVP, or full user/password + rotating JWT?
4. **Persistent history:** In-memory MVP, SQLite projection, or persisted app DB?
5. **Voice transcription:** On-device speech recognition, cloud STT, or send audio to Hermes STT provider?
6. **Push notifications:** Expo push service, ntfy, or Hermes gateway platform delivery?

## Proposed Repository Layout

Add these paths under `C:\Dev\HermesMobileControl`:

```text
apps/mobile/                         # Expo React Native app
  app/                               # Expo Router screens
  src/
    api/                             # REST/WebSocket client
    components/                      # UI components
    features/tasks/                  # Task list/detail/create flows
    features/projects/               # Project list/status flows
    features/voice/                  # Voice capture/transcription
    state/                           # Zustand stores
    theme/                           # colors, typography, spacing
  package.json
  app.json
  tsconfig.json

services/control_api/                # FastAPI companion API
  __init__.py
  main.py                            # app factory + routes
  auth.py                            # bearer token/JWT validation
  hermes_client.py                   # abstraction for Hermes task/session integration
  models.py                          # Pydantic API models
  projection.py                      # task/project status read model
  websocket.py                       # live event fanout
  hermes_runner.py                   # optional subprocess/gateway starter
  tests/
    test_models.py
    test_task_submission.py
    test_projection.py

README.md                            # mobile/control-api setup
requirements.txt                     # backend Python dependencies
pyproject.toml                       # optional later: lint/test config
```

## Local API Schema

Standardize API payloads for mobile projections. These are app/backend contracts, not Agent Queue message contracts.

### Task created

```json
{
  "task_id": "uuid",
  "project_id": "default",
  "title": "Short generated title",
  "prompt": "User-provided instruction",
  "source": "mobile",
  "priority": "normal",
  "created_by": "mobile-user",
  "created_at": "ISO-8601"
}
```

### Task claimed/running

```json
{
  "task_id": "uuid",
  "agent_id": "hermes-agent",
  "started_at": "ISO-8601"
}
```

### Task progress

```json
{
  "task_id": "uuid",
  "message": "Current operation",
  "percent": null,
  "updated_at": "ISO-8601"
}
```

### Task completed

```json
{
  "task_id": "uuid",
  "summary": "Final result summary",
  "artifact_urls": [],
  "completed_at": "ISO-8601"
}
```

### Task failed

```json
{
  "task_id": "uuid",
  "error": "Human-readable failure",
  "failed_at": "ISO-8601"
}
```

### Agent status

```json
{
  "agent_id": "hermes-agent",
  "status": "idle|busy|offline",
  "current_task_id": null,
  "project_id": "default",
  "last_seen_at": "ISO-8601"
}
```

## Implementation Tasks

### Task 1: Define API and event contracts

**Objective:** Create the backend model layer that formalizes task/project/agent payloads.

**Files:**
- Create: `services/control_api/__init__.py`
- Create: `services/control_api/models.py`
- Create: `services/control_api/tests/test_models.py`
- Create/Modify: `requirements.txt`

**Steps:**
1. Add dependencies: `fastapi`, `uvicorn[standard]`, `pydantic`, `pytest`, and `httpx`.
2. Define Pydantic models for `TaskCreateRequest`, `TaskSummary`, `TaskEvent`, `AgentStatus`, and `ProjectSummary`.
3. Write model validation tests for required task prompt, default project, and supported task statuses.
4. Run: `python -m pytest services/control_api/tests/test_models.py -v`.

### Task 2: Build FastAPI health/auth shell

**Objective:** Start a companion API with health endpoint and bearer-token auth.

**Files:**
- Create: `services/control_api/main.py`
- Create: `services/control_api/auth.py`
- Create: `services/control_api/tests/test_auth.py`

**Steps:**
1. Implement `GET /health` returning `{ "ok": true }`.
2. Implement bearer-token dependency reading `CONTROL_API_TOKEN` from env.
3. Protect all non-health endpoints.
4. Add tests with FastAPI `TestClient` for missing/invalid/valid token.
5. Run targeted tests.

### Task 3: Add Hermes task submission service

**Objective:** Let the API accept mobile task requests and hand them to the selected Hermes integration surface.

**Files:**
- Create: `services/control_api/hermes_client.py`
- Create: `services/control_api/tests/test_task_submission.py`
- Modify: `services/control_api/main.py`

**Steps:**
1. Create a `HermesClient`/`HermesTaskService` abstraction that can later call Hermes CLI, gateway API, or another local interface.
2. Create `POST /tasks` accepting a prompt/project and creating a local task record.
3. Return generated `task_id` immediately.
4. Mock the Hermes integration in tests so tests do not require a running Hermes instance.
5. Verify the request payload and returned task summary follow the schema above.

### Task 4: Add read-model projection for task/project/agent state

**Objective:** Provide app-friendly list/detail endpoints independent of the eventual Hermes integration mechanism.

**Files:**
- Create: `services/control_api/projection.py`
- Create: `services/control_api/tests/test_projection.py`
- Modify: `services/control_api/main.py`

**Steps:**
1. Implement an in-memory projection for MVP.
2. Apply events: created -> queued, claimed -> running, progress -> update log, completed -> completed, failed -> failed.
3. Add endpoints: `GET /tasks`, `GET /tasks/{task_id}`, `GET /projects`, `GET /agents`.
4. Add unit tests for event application order and status transitions.

### Task 5: Add WebSocket live event fanout

**Objective:** Push live task/agent updates to mobile clients.

**Files:**
- Create: `services/control_api/websocket.py`
- Modify: `services/control_api/main.py`
- Add tests if practical, otherwise add a manual smoke script.

**Steps:**
1. Implement `GET /ws/events` WebSocket requiring token in query param or subprotocol.
2. Add a broadcast manager with connect/disconnect/send methods.
3. Broadcast projection updates when events are applied.
4. Add a local smoke script that connects and prints events.

### Task 6: Decide and implement Hermes task execution path

**Objective:** Ensure a prompt submitted from mobile actually starts Hermes work.

**Recommended MVP Option:** Companion API launches a bounded Hermes one-shot process:

```bash
hermes chat -q "<prompt>"
```

and updates progress/completed/failed state in the companion API projection.

**Alternative:** Use a Hermes gateway/API-server integration if it provides the required task/session control APIs.

**Files:**
- Create: `services/control_api/hermes_runner.py`
- Modify: `services/control_api/main.py`
- Create tests with subprocess mocked.

**Steps:**
1. Implement a runner abstraction so launch strategy can be swapped later.
2. On task submission, enqueue/background a runner job.
3. Update local task state to claimed/running, progress, completed, or failed.
4. Prevent arbitrary shell injection: pass args as an array, never interpolate into shell.
5. Add a concurrency limit to avoid launching too many Hermes tasks.

### Task 7: Scaffold Expo mobile app

**Objective:** Create Android-first/iOS-ready app shell.

**Files:**
- Create: `apps/mobile/package.json`
- Create: `apps/mobile/app.json`
- Create: `apps/mobile/tsconfig.json`
- Create: `apps/mobile/app/_layout.tsx`
- Create: `apps/mobile/app/index.tsx`
- Create: `apps/mobile/src/theme/*`

**Steps:**
1. Initialize Expo with TypeScript.
2. Add navigation via Expo Router.
3. Add theme provider with light/dark palettes.
4. Add bottom tabs: Dashboard, Tasks, Projects, New Task, Settings.
5. Verify with `npx expo start` and Android emulator/device.

### Task 8: Build API client and connection settings

**Objective:** Let users configure companion API URL/token and verify connectivity.

**Files:**
- Create: `apps/mobile/src/api/client.ts`
- Create: `apps/mobile/src/state/settings.ts`
- Create: `apps/mobile/app/settings.tsx`

**Steps:**
1. Store API base URL and token locally using secure storage if available.
2. Implement typed `fetchJson` helper with auth header.
3. Add Settings screen with API URL/token fields and Test Connection button.
4. Show clear errors for unreachable LAN host, invalid token, and TLS/cert issues.

### Task 9: Build dashboard and task list screens

**Objective:** Show current running tasks, recent completions/failures, and agent health.

**Files:**
- Create: `apps/mobile/app/tasks/index.tsx`
- Create: `apps/mobile/app/tasks/[taskId].tsx`
- Create: `apps/mobile/app/projects/index.tsx`
- Create: `apps/mobile/src/features/tasks/*`
- Create: `apps/mobile/src/features/projects/*`

**Steps:**
1. Fetch `GET /tasks`, `GET /agents`, and `GET /projects`.
2. Render status cards with modern clean aesthetic.
3. Add pull-to-refresh.
4. Add task detail screen with status, prompt, progress log, result summary, artifacts.
5. Add empty/error/loading states.

### Task 10: Add live updates

**Objective:** Keep dashboard current without manual refresh.

**Files:**
- Create: `apps/mobile/src/api/events.ts`
- Modify task/project screens.

**Steps:**
1. Connect to `/ws/events` when app is foregrounded.
2. Reconcile incoming events into local query cache/store.
3. Display live connection state in UI.
4. Reconnect with exponential backoff.
5. Fall back to polling if WebSocket fails.

### Task 11: Add text prompt flow

**Objective:** Allow new Hermes tasks from typed instructions.

**Files:**
- Create: `apps/mobile/app/new-task.tsx`
- Create: `apps/mobile/src/features/tasks/NewTaskForm.tsx`

**Steps:**
1. Add multiline prompt input.
2. Add project selector and priority selector.
3. Submit to `POST /tasks`.
4. Navigate to task detail screen after successful submit.
5. Disable submit for empty prompt and show progress while submitting.

### Task 12: Add voice prompt flow

**Objective:** Allow new tasks from voice instructions.

**Files:**
- Create: `apps/mobile/src/features/voice/VoicePromptButton.tsx`
- Modify: `apps/mobile/app/new-task.tsx`

**Steps:**
1. Start with platform-supported speech-to-text or Expo-compatible voice package.
2. Add mic button with recording/listening states.
3. Fill the text prompt with transcribed speech.
4. Let the user edit before submitting.
5. Add permission prompts and graceful fallback when voice permissions are denied.

### Task 13: Polish modern UI

**Objective:** Make the app feel clean and production-quality.

**Files:**
- Modify: mobile screens/components/theme.

**Design direction:**
- Dark-first dashboard with subtle gradients.
- Card-based status widgets.
- Clear status colors: queued gray/blue, running violet/green, completed green, failed red.
- Large New Task CTA.
- Monospace task logs in collapsible panels.
- Minimal settings screen.

**Steps:**
1. Create shared `StatusPill`, `TaskCard`, `AgentCard`, `ProjectCard`, `EmptyState`, `ErrorState` components.
2. Apply consistent spacing, typography, and shadows.
3. Test on a small Android phone viewport and a tablet/large viewport.

### Task 14: Add local deployment docs

**Objective:** Make the system easy to run on the user's infrastructure.

**Files:**
- Modify: `README.md`
- Create: `services/control_api/README.md`
- Create: `apps/mobile/README.md`

**Steps:**
1. Document backend startup for `C:\Dev\HermesMobileControl`.
2. Document control API env vars: `CONTROL_API_TOKEN` and Hermes launch/integration mode.
3. Document Android local testing with LAN IP/Tailscale hostname.
4. Document iOS future build notes.
5. Include security warning not to expose control API publicly without TLS/auth.

## Verification Plan

### Backend

Run targeted tests:

```bash
python -m pytest services/control_api/tests -v
```

Manual smoke:

```bash
# In C:\Dev\HermesMobileControl
CONTROL_API_TOKEN=dev-token uvicorn services.control_api.main:app --host 0.0.0.0 --port 8787
curl http://localhost:8787/health
curl -H 'Authorization: Bearer <CONTROL_API_TOKEN>' http://localhost:8787/tasks
curl -X POST -H 'Authorization: Bearer <CONTROL_API_TOKEN>' -H 'Content-Type: application/json' \
  -d '{"prompt":"Say hello from Hermes mobile MVP","project_id":"default"}' \
  http://localhost:8787/tasks
```

### Mobile

Run:

```bash
cd apps/mobile
npm install
npx expo start
```

Verify on Android device/emulator:

1. Settings -> enter API URL/token -> Test Connection succeeds.
2. Dashboard loads agents/tasks/projects.
3. New Task -> type prompt -> task appears in task list.
4. Voice -> transcribe prompt -> edit -> submit.
5. WebSocket updates task detail without pull-to-refresh.

## Security Notes

1. Do not expose local Hermes control endpoints directly to the public internet.
2. Do not store infrastructure credentials in the mobile app.
3. Require an API token from the first backend task.
4. Prefer Tailscale/WireGuard for remote access.
5. Use HTTPS before exposing beyond trusted LAN/VPN.
6. Avoid sending secrets in task payloads or mobile logs.
7. Add rate/concurrency limits before allowing multiple devices/users.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Mobile device cannot reach `localhost` | Use host LAN IP/Tailscale name; document clearly. |
| Hermes launch from API is unsafe | Use subprocess arg arrays, token auth, prompt logging controls, concurrency limit. |
| Hermes APIs do not expose every UI state needed | Add a local projection store; migrate from memory to SQLite if needed. |
| Voice package differences between Android/iOS | Abstract voice provider behind `VoicePromptButton`; test Android first. |
| iOS local-network permissions | Add iOS-specific notes/config later. |
| Push notification complexity | Defer until MVP live WebSocket works. |

## Suggested MVP Milestone Split

1. **Milestone 1: Backend control API** — health/auth, task submission, projection, WebSocket.
2. **Milestone 2: Android app shell** — settings, dashboard, task list/detail.
3. **Milestone 3: Task creation** — text prompt flow end-to-end.
4. **Milestone 4: Voice input** — voice-to-text prompt submission.
5. **Milestone 5: Hermes execution integration** — robust task runner/worker path.
6. **Milestone 6: Polish/security** — UI polish, docs, TLS/VPN guidance, tests.

## Immediate Next Step

Start with Task 1 and Task 2. They create the stable API contract and authentication boundary needed before the mobile app or Hermes runner can safely build on top of it.
