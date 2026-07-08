# Testing Strategy

Hermes Mobile Control is split into explicit layers and each layer has a matching verification target.

## Layers

### Backend companion API

- **Domain/contracts:** `services/control_api/models.py`
- **Projection/read model:** `services/control_api/projection.py`
- **Persistence adapter:** `services/control_api/storage.py`
- **Application boundary:** `services/control_api/hermes_client.py`
- **Transport/API:** `services/control_api/main.py`
- **Realtime transport:** `services/control_api/websocket.py`

The current `HermesTaskService` is the seam for real Hermes execution. The mobile-facing API is already shaped for task submission and monitoring; the service currently records tasks locally until a real Hermes API/gateway/CLI adapter is plugged in.

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

### Integration

In-process API/auth/websocket behavior across service boundaries.

```bash
python -m pytest services/control_api/tests -m integration -v
```

### E2E

Public companion API flow from mobile-style health check to authenticated task creation, websocket update, task detail, projects, and agents.

```bash
python -m pytest services/control_api/tests -m e2e -v
```

Android device review is also available as a heavier e2e verification path:

```bash
python scripts/verify.py --android --sideload
```

## Canonical verification

Run all non-device checks:

```bash
python scripts/verify.py
```

Run all checks including Android release build and connected-device sideload:

```bash
python scripts/verify.py --android --sideload
```
