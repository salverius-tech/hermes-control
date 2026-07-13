# Architecture

Hermes Mobile Control is a small layered system: an Expo mobile client talks to a FastAPI companion API, and the companion API owns the seam where real Hermes execution will be attached later.

## System view

```text
Android / future iOS app
  ├─ screens: apps/mobile/app/
  ├─ source layers: apps/mobile/src/
  └─ authenticated REST + WebSocket
        ↓
FastAPI companion API
  ├─ transport: services/control_api/main.py, websocket.py
  ├─ application seam: services/control_api/hermes_client.py
  ├─ projection/read model: services/control_api/projection.py
  ├─ persistence adapter: services/control_api/storage.py
  └─ contracts/domain models: services/control_api/models.py
        ↓
Future Hermes adapter
  └─ CLI, Hermes API Server, gateway, or another explicitly selected surface
```

Agent Queue is deliberately not part of this dependency graph.

## Backend layers

### Domain/contracts

`services/control_api/models.py`

Defines public data contracts shared by tests, persistence, API responses, and mobile TypeScript mirrors:

- `TaskCreateRequest`
- `TaskSummary`
- `ProjectSummary`
- `AgentStatus`
- status/priority enums

Rules:

- No FastAPI imports.
- No storage imports.
- No application-service imports.
- Validation belongs here when it is contract-level behavior.

### Persistence adapter

`services/control_api/storage.py`

Defines `TaskStore` and the SQLite adapter.

Rules:

- Depends only on domain contracts and Python persistence libraries.
- Does not know about FastAPI, WebSockets, mobile clients, or Hermes execution.
- Stores JSON payloads validated back into `TaskSummary` on load.

### Projection/read model

`services/control_api/projection.py`

Owns local task/project/agent state and optionally saves through a `TaskStore`.

Rules:

- Depends on domain contracts and the store protocol.
- Does not import FastAPI, WebSocket, or UI code.
- Is swappable if the backend later moves from local projection to a richer data service.

### Application seam

`services/control_api/hermes_client.py`

`HermesTaskService` is the seam for real Hermes execution. Today it records a queued task in the projection. Later it can delegate to a Hermes CLI/API/gateway adapter without changing mobile-facing REST/WebSocket contracts.

Rules:

- Mobile/API contracts stay stable.
- Real Hermes integration goes behind this seam, not in route handlers.
- Adapter-specific credentials/config must stay outside source control.

### Transport/composition

`services/control_api/main.py` and `services/control_api/websocket.py`

FastAPI routes authenticate requests, call the application/projection layers, and broadcast live events.

Rules:

- `main.py` is the composition root that wires environment config, persistence adapter, projection, service, and websocket manager.
- Route handlers should remain thin.
- Auth failures and missing resources are transport concerns; domain validation remains in models.

## Mobile layers

### Screens

`apps/mobile/app/`

Expo Router screens compose UI, settings state, and API calls. They should not own reusable business logic.

### API client

`apps/mobile/src/api/`

- `client.ts` contains companion API types and authenticated fetch helpers.
- `events.ts` contains WebSocket connection construction.
- `url.ts` contains pure URL-building logic.

### Feature/domain utilities

`apps/mobile/src/features/`

Pure feature behavior that is easy to unit test, such as voice transcript prompt composition.

### Navigation

`apps/mobile/src/navigation/`

- `items.ts` is pure route metadata and active-route behavior.
- `BottomNavigation.tsx` is UI and may import Expo Router/React Native.
- `constants.ts` centralizes bottom bar sizing used by screens.

### State/settings

`apps/mobile/src/state/`

Zustand + SecureStore wrapper for the companion API URL/token. Settings state is a mobile concern and does not know about backend implementation details.

### UI/theme

`apps/mobile/src/components/` and `apps/mobile/src/theme/`

Reusable presentational components and design tokens.

## Enforced boundaries

Boundary tests are part of the normal suites:

- Backend: `services/control_api/tests/test_architecture.py`
- Mobile: `apps/mobile/src/navigation/architecture.test.ts`

These tests guard against common erosion:

- domain models importing application/transport code,
- persistence importing API/websocket code,
- mobile `src` modules importing Expo Router app screens,
- pure mobile model helpers importing React Native UI packages.

## Current product status and limitations

Product-level status, limitations, roadmap, and remaining work are tracked in `docs/PRD.md`.

Architecture-specific notes:

- SQLite persistence stores local task projection and event data only; it is not a replacement for Hermes' own session/task history.
- The generated Android project is committed because native voice/plugin configuration and release build behavior are part of the current deliverable.
