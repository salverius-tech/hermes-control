# Testing Strategy

Hermes Mobile Control is split into explicit layers and each layer has a matching verification target. See `ARCHITECTURE.md` for dependency direction and the rationale behind each layer.

## Layers

### Backend companion API

- **Domain/contracts:** `services/control_api/models.py`
- **Persistence adapter:** `services/control_api/storage.py`
- **Projection/read model:** `services/control_api/projection.py`
- **Application boundary:** `services/control_api/hermes_client.py`
- **Transport/API:** `services/control_api/main.py`
- **Realtime transport:** `services/control_api/websocket.py`

The current `HermesTaskService` is the seam for real Hermes execution. The mobile-facing API is already shaped for task submission and monitoring; the service records tasks locally until a real Hermes API/gateway/CLI adapter is plugged in.

### Mobile app

- **Screens:** `apps/mobile/app/`
- **API client:** `apps/mobile/src/api/`
- **Feature/domain utilities:** `apps/mobile/src/features/`
- **Navigation model/bar:** `apps/mobile/src/navigation/`
- **Reusable UI:** `apps/mobile/src/components/`
- **State/settings:** `apps/mobile/src/state/`
- **Theme tokens:** `apps/mobile/src/theme/`

## Test levels

### Unit

Fast, isolated tests for pure logic.

```bash
# Backend unit tests
python -m pytest services/control_api/tests -m unit -v

# Mobile unit tests
cd apps/mobile
npm run test:unit
```

Unit coverage includes contract validation, read-model behavior, SQLite persistence adapter behavior, mobile URL construction, voice transcript prompt composition, navigation state, and architecture-boundary tests.

### Integration

In-process API/auth/websocket behavior across service boundaries.

```bash
python -m pytest services/control_api/tests -m integration -v
```

Integration coverage includes successful API paths and failure paths: missing/invalid auth, malformed auth scheme, invalid task payloads, unknown task ids, websocket token rejection, initial snapshots, and live `task.created` broadcasts.

### E2E

Public companion API flow from mobile-style health check to authenticated task creation, websocket update, task detail, projects, and agents.

```bash
python -m pytest services/control_api/tests -m e2e -v
```

E2E coverage includes the mobile-facing task flow and SQLite-backed persistence across app instances.

Android device review is also available as a heavier e2e verification path:

```bash
python scripts/verify.py --android --sideload
```

## Boundary tests

Architecture tests guard against accidental layer erosion:

```bash
python -m pytest services/control_api/tests/test_architecture.py -v

cd apps/mobile
npx vitest run src/navigation/architecture.test.ts
```

They enforce that backend domain/storage/projection/application layers do not import transport code and that mobile pure model helpers stay independent from screen/UI packages.

## Edge and error paths

Coverage is intentionally not limited to happy paths. Current negative-path checks include:

- blank prompts and blank project ids,
- unsupported priorities/statuses,
- missing, invalid, and malformed auth,
- unknown task ids,
- websocket missing/invalid token rejection,
- blank websocket URL origins,
- empty/whitespace voice transcripts,
- source-layer import boundary violations.

## Canonical verification

Run all non-device checks:

```bash
python scripts/verify.py
```

Run all checks including Android release build and connected-device sideload:

```bash
python scripts/verify.py --android --sideload
```
