# Native Hermes Projects & Mobile Operator Experience — Implementation Plan

> **Status:** In progress.
> **Progress:** 36 / 37 implementation tasks complete.
> **Tracking rule:** Update the task checkbox, evidence, and decision log immediately after each completed, verified slice. Do not mark a task complete based only on code written; record the command/test/device evidence.

## 1. Goal

Make Hermes Control a trustworthy remote extension of Hermes Agent:

- mobile **Projects** are authoritative native Hermes Projects, not task-derived labels;
- a managed project workspace may exist before any Git repository;
- the mobile experience organizes work as `Project → session/work thread → immutable task attempts`;
- the operator can see what needs attention, understand retry outcomes, continue sessions, create projects, optionally clone repositories, and safely recover projects after host restoration.

## 2. Product and architecture decisions

| Decision | Chosen direction |
|---|---|
| Mobile product role | Remote/mobile extension of Hermes Agent; not a parallel project/task product. |
| Project authority | Native Hermes Projects in the configured Hermes profile’s `projects.db`. |
| Project execution context | Server resolves a selected native project to a validated explicit folder; browsing never changes Hermes’ global active project. |
| Workspace root | `~/.hermes/workspaces/<project-slug>/` for new managed projects. |
| Repository requirement | Optional. A workspace-only project is valid. |
| Default native primary folder | Managed workspace root, including when a repository exists at `repo/`. |
| Repository location | Optional `<workspace>/repo/`, registered as an additional native project folder when present. |
| Recovery identity | `hermes-project.yaml` in each managed workspace. |
| Recovery behavior | Dry-run review plan followed by explicit user confirmation; no automatic re-registration. |
| Task UI unit | A work thread with linked immutable attempts; latest outcome is the default view. |
| Mobile navigation | Inbox, Projects, New, Activity, More. |
| Existing projects | Remain in their current locations; no forced/bulk migration. |

## 3. Domain model

```text
Native Hermes Project
  → managed workspace
    → notes / artifacts
    → optional repository
  → Hermes sessions
  → Control API work thread
    → immutable task attempts
      → events, output, approval, failure, result
```

### Data ownership

| Store | Owns |
|---|---|
| Hermes `projects.db` | Native project identity, name, slug, folders, primary folder, archive state. |
| Hermes `state.db` | Native sessions and their working directories. |
| Control API database | Mobile task attempts, events, retry/continuation lineage, audit records. |
| Workspace `hermes-project.yaml` | Portable recovery descriptor for a managed workspace. |
| Workspace filesystem | Project files, notes, artifacts, optional repositories. |

The recovery manifest is not a competing normal-operation source of truth. Native Hermes records remain authoritative while the host is operating.

## 4. Managed workspace and manifest contract

### Layout

```text
~/.hermes/workspaces/
  <slug>/
    hermes-project.yaml
    README.md
    notes/
    artifacts/
    repo/                  # optional
```

### Initial manifest schema

```yaml
schema_version: 1

identity:
  slug: new-mobile-client
  name: New Mobile Client
  description: Optional human description
  workspace_id: <stable UUID>

workspace:
  primary_folder: "."
  folders:
    - path: "."
      role: workspace
      primary: true
    - path: "repo"
      role: repository
      primary: false

repository:
  path: repo
  remote_url: git@github.com:example-org/new-mobile-client.git

lifecycle:
  managed_by: hermes-control
  native_registration: registered
```

`repository` and its folder entry are omitted for workspace-only projects.

### Manifest rules

- All stored paths are relative to the workspace root.
- `slug` is the stable Hermes-facing recovery key.
- `workspace_id` is stable across host restoration and is not the native Hermes database ID.
- Never write credentials, tokens, SSH keys, provider keys, hostnames, or absolute host paths.
- Writes are atomic.
- `native_registration` supports at least `pending`, `registered`, `registration_failed`, and `archived`.

## 5. Mobile information architecture

### Bottom navigation

```text
Inbox       Projects       New       Activity       More
```

| Destination | Purpose |
|---|---|
| Inbox | Cross-project attention-required, active, and recently resolved work. It is a filtered operational view, not a competing hierarchy. |
| Projects | All native Hermes Projects, with workspace/session/work-thread context. |
| New | Task composer: select native project first, then compose and submit. |
| Activity | Searchable cross-project audit/history for sessions, work threads, and attempts. |
| More | Settings, connection/profile identity, diagnostics, offline queue, and project recovery. |

### Project detail order

1. Project header and workspace/repository state.
2. Needs Attention.
3. Active Work.
4. Recent Work.
5. Hermes Sessions.
6. Workspace/repository management.

Attention work threads expand by default. Ordinary completed threads remain collapsed by default.

## 6. Work-thread and recovery UX

A task attempt remains immutable, but the primary display is its work thread.

```text
Work thread: Add recovery manifest
Latest outcome: Completed after retry
Attempts: 3
  Original attempt → failed
  Retry → blocked
  Continuation → completed
```

### Required recovery actions

| Condition | Action |
|---|---|
| Session exists and work should continue | Continue current session |
| Prompt/input requires revision | Edit before retry |
| Independent attempt is appropriate | Start new session |
| Environment may be broken | Check environment |
| Operator wants to end work | Cancel task |

A historical failed attempt must display a visible link/banner to the newer attempt and its latest outcome. An environment check is distinct from automatically retrying work.

## 7. Reliability and diagnostics requirements

### Client synchronization

```text
WebSocket live events + authoritative REST snapshots + persisted offline queue
```

- Refresh authoritative state on launch, reopen, and WebSocket reconnect.
- Use reconnect backoff and stale-event protection.
- Detect event sequence gaps and trigger snapshot reconciliation.
- Generate an idempotency key before the first task submission and persist/reuse it for uncertain/offline retries.
- Show pending, retrying, submitted, and failed offline states with explicit retry/discard controls.

### Execution activity

Persist/display `run_started_at`, `last_heartbeat_at`, `last_output_at`, execution state, phase, detail, and structured terminal reason. A quiet but live task transitions to non-terminal attention state after a configured quiet threshold, and returns to running when output resumes.

### Diagnostics surface

Show non-secret state separately for:

- Control API reachability;
- authenticated WebSocket state;
- configured Hermes profile/native project store availability;
- workspace root readiness;
- bridge readiness;
- executor readiness;
- active queue and offline queue state.

A passing `/health` result must not be labelled as proof that Hermes execution is ready.

---

# 8. Implementation tracker

## Phase 0 — Specification and safety baseline

- [ ] **P0.1** Confirm the target Hermes profile/home and service account used by the deployed Control API.  
  **Evidence:** redacted deployment configuration review; authenticated diagnostics shows profile integration readiness.
- [ ] **P0.2** Audit live Hermes project/session schemas and map every existing `/projects`, `/sessions`, and task-submission route to its authoritative store.
  **Evidence:** `docs/NATIVE_STORE_ROUTE_MAPPING.md` and the native-schema fixtures map repository behavior; no live native-store/profile audit was possible, so this task remains open.
- [x] **P0.3** Define public API compatibility/migration behavior for synthetic task-derived project IDs.
  **Evidence:** `docs/API.md` and `docs/NATIVE_STORE_ROUTE_MAPPING.md` define strict-native rejection, development-only fixture mode, and client migration; `services/control_api/tests/test_native_project_integration.py` rejects legacy `default`, and `test_native_store_route_mapping_docs.py` guards the public contract.

## Phase 1 — Native Hermes Project correctness

- [x] **P1.1** Make the workspace projection explicitly use the configured Hermes home/profile; fail diagnostics clearly when it is unavailable.  
  **Files likely:** `services/control_api/main.py`, `workspace.py`, diagnostics models/tests.
- [x] **P1.2** Make `GET /projects` and `GET /projects/{id}` use the same authoritative native projection.  
  **Evidence:** regression test enumerates every list ID and verifies its detail route.
- [x] **P1.3** Remove production synthetic task-derived projects and synthetic Default project behavior; retain an explicitly labelled development-only mode only if needed.  
  **Evidence:** unknown project IDs cannot appear as valid production projects.
- [x] **P1.4** Validate submitted native project IDs, archive state, project folders, execution context, and continuation session containment server-side.  
  **Evidence:** tests for unknown, archived, out-of-project folder, and invalid-session rejection.
- [x] **P1.5** Expose truthful profile/project-store readiness in diagnostics without exposing host paths or secrets.  
  **Evidence:** authenticated diagnostics tests and live redacted verification.

## Phase 2 — Managed workspace and manifest foundation

- [x] **P2.1** Add explicit managed workspace-root configuration with containment/writability checks.  
  **Evidence:** configuration, diagnostics, and path-traversal/permission tests.
- [x] **P2.2** Define Pydantic/domain models for managed-project origin (`workspace`, `clone`, `adopt`) and manifest schema v1.  
  **Evidence:** schema validation tests including invalid relative paths and unknown versions.
- [x] **P2.3** Implement safe workspace slug allocation and atomic workspace/bootstrap file creation.  
  **Evidence:** collision, invalid slug, partial-write, and idempotence tests.
- [x] **P2.4** Implement workspace-only native Hermes Project creation: create workspace, write pending manifest, create native project with explicit slug/primary folder, verify, mark registered.  
  **Evidence:** integration test against native-project SQLite fixture.
- [x] **P2.5** Synchronize native project edits/folder/archive operations to a managed workspace manifest; do not create manifests for adopted legacy projects unless explicitly adopted later.  
  **Evidence:** update and archive synchronization tests.
- [x] **P2.6** Add repair-state behavior for workspace exists/native registration failed.  
  **Evidence:** failed-registration recovery test and clear API error/result contract.

## Phase 3 — Repository lifecycle

- [x] **P3.1** Add server-side Git adapter with argument-array execution, bounded output, timeout/cancellation, and sanitized diagnostics.  
  **Evidence:** adapter unit tests; no shell execution path.
- [x] **P3.2** Implement clone-backed project creation: bootstrap workspace, clone to `repo/`, register workspace primary plus repo folder, verify, update manifest.  
  **Evidence:** end-to-end clone fixture test.
- [x] **P3.3** Reject unsafe URLs, non-empty destinations, path collisions, and unauthorized/unavailable Git authentication cleanly.  
  **Evidence:** negative tests and sanitized error assertions.
- [x] **P3.4** Preserve successfully cloned files when later native registration fails; mark repairable state and expose an explicit repair action.  
  **Evidence:** partial-failure integration test.
- [x] **P3.5** Support attaching/cloning a repository into an existing workspace-only project.  
  **Evidence:** API/manifest/native-folder synchronization tests.

## Phase 4 — Reviewable recovery

- [x] **P4.1** Implement manifest discovery and validation confined to the managed workspace root.
  **Evidence:** valid, missing, malformed, duplicate-slug, and traversal fixtures.
- [x] **P4.2** Implement a read-only recovery-plan API that classifies entries as ready, already registered, missing repository, blocked, or conflict.
  **Evidence:** no mutation during dry-run test.
- [x] **P4.3** Implement explicit recovery apply requiring selected-plan confirmation/revalidation.
  **Evidence:** confirm/cancel tests; changed manifest after plan generation is revalidated.
- [x] **P4.4** Recreate missing native Hermes Projects with stable slug, workspace primary folder, and present optional repo folder; never overwrite existing records.

  **Evidence:** clean-profile restoration integration test.
- [x] **P4.5** Add durable recovery audit events and per-project result reporting.
  **Evidence:** persistence/reload and API timeline tests.

## Phase 5 — Work-thread projection and task recovery

- [x] **P5.1** Define a work-thread read model grouping root task and linked retries/continuations/follow-ups.
  **Evidence:** lineage projection tests across persisted reload.
- [x] **P5.2** Add latest-attempt/latest-outcome semantics and visible historical-to-latest links.
  **Evidence:** API and mobile filtering tests for failed-then-completed lineage.
- [x] **P5.3** Implement guarded Continue current session, Edit before retry, Start new session, Check environment, and Cancel flows.
  **Evidence:** state-transition, session-validation, and idempotency tests.
- [x] **P5.4** Capture/validate Hermes session identifiers and use supported continuation behavior.
  **Evidence:** continuation integration test and native session containment test.
- [x] **P5.5** Add activity-aware task state fields/events and distinguish quiet-but-alive, missing-heartbeat, interrupted, blocked, failed, and completed outcomes.
  **Evidence:** targeted bridge/API tests for each transition.

## Phase 6 — Mobile information architecture and screens

- [x] **P6.1** Replace the competing Home/Tasks/Projects/Attention model with Inbox, Projects, New, Activity, and More, preserving deep links and accessible navigation.
  **Evidence:** navigation unit tests and rendered mobile smoke test.
- [x] **P6.2** Build Inbox around attention-required, active, and recently resolved work threads.
  **Evidence:** state/filter tests plus populated-state physical-device Maestro validation using the disposable local-only native-store sandbox.
- [x] **P6.3** Rebuild Project detail as attention → active work → recent work → sessions → workspace/repository management.
  **Evidence:** stable screen selectors plus populated-state physical-device Maestro validation using the disposable local-only native-store sandbox.
- [x] **P6.4** Replace the current manual-folder-first project form with workspace, clone, and adopt modes; show progress/error/repair states.
  **Evidence:** API-client and form-state tests; failed managed workspace/clone creation retains the exact request for an explicit native-registration repair action.
- [x] **P6.5** Add work-thread task detail UI with latest outcome, attempt timeline, retry lineage, and recovery actions.
  **Evidence:** mobile lineage/unit tests plus a populated-state physical-device task-detail flow asserting timeline and retry, edit-retry, and continuation actions.
- [x] **P6.6** Add Activity search/history and More diagnostics/recovery-plan screens.
  **Evidence:** API contract and screen-state tests; recovery restoration requires a fresh reviewed ready plan plus explicit mobile confirmation.

## Phase 7 — Sync, offline behavior, and validation

- [x] **P7.1** Centralize client REST/WebSocket reconciliation with reconnect snapshot, stale-event handling, sequence-gap refresh, and connection status.
  **Evidence:** mocked store lifecycle tests cover snapshots, ordered updates, stale/duplicate event and snapshot suppression, forward gaps, reconnect, and cleanup.
- [x] **P7.2** Implement persisted offline submission queue with stable pre-request idempotency keys, backoff, reconcile, retry, and discard controls.
  **Evidence:** client tests plus repeated-key API integration test.
- [x] **P7.3** Add approval audit metadata where supported and surface approval work in Inbox.
  **Evidence:** durable event payload tests and mobile screen test.
- [x] **P7.4** Run full backend, mobile, canonical, secret-scan, and diff checks after each completed phase.
  **Evidence:** final `python scripts/verify.py --maestro`, `python scripts/secret_scan.py --all`, and `git diff --check` passed.
- [ ] **P7.5** Perform physical-device validation: native project list, workspace creation, repository clone, task execution, retry/continuation, WebSocket reconnect, offline queue, and recovery-plan confirmation.
  **Completed device evidence:** loopback-only, marker-protected sandboxes on the authorized Android device verified native-project discovery/selection; task submission, detail, and fixture completion; managed workspace creation; clone-backed project creation from a committed local dumb-HTTP Git remote; retry/Continue action creating a linked completed attempt visible in the immutable two-attempt timeline; and explicit recovery-plan Restore confirmation with API postflight for registration, reclassification, and append-only audit data. Each run used fixture-only runtime settings, owned `adb reverse` mappings, and explicit app/server/sandbox cleanup.
  **Open validation blockers:**
  - **Offline queue:** the physical device retained cached projects and showed an enabled selected-project task form after the fixture listener and owned reverse mapping were removed, but tapping **Start Hermes task** produced neither the expected queued-task notice/card nor a submission error. A 10-second `apiFetch` deadline and automated unreachable-request regression test were added, but the rebuilt release APK still did not render the queue fallback. Do not count offline queue/retry/discard/reconciliation as validated until this interaction is root-caused and a device flow observes the queued card and controls.
  - **WebSocket reconnect:** device-to-loopback WebSocket traffic was observed, and mocked lifecycle tests cover reconnect snapshot/reconciliation, but a deliberate physical disconnect → reconnect → rendered-state assertion remains flaky after clean app resets. Do not count physical reconnect/reconciliation as validated until the device flow observes disconnected then connected/current state after server restoration.
  **Exit criterion:** leave this item unchecked until both blocker flows pass on the physical device and their postflight cleanup is recorded.

---

## 9. Verification record

Add entries here only after running the command against the current relevant revision.

| Date | Phase/task | Command or procedure | Result | Notes |
|---|---|---|---|
| 2026-07-21 | P1.1–P1.5 | `.venv/bin/python -m pytest services/control_api/tests -q` | 95 passed | Native projection, strict production mode, task-context validation, and diagnostics coverage. |
| 2026-07-21 | P1.1–P1.5 | `git diff --check` | passed | No whitespace errors. |
| 2026-07-21 | P2.1, P2.4 (partial Phase 2) | `.venv/bin/python -m pytest services/control_api/tests -q` | 97 passed | Managed workspace configuration, manifest creation, collision handling, and native registration. |
| 2026-07-21 | P2.2 | `.venv/bin/python -m pytest services/control_api/tests -q` | 98 passed | Schema-version, extra-field, and relative-path manifest validation. |
| 2026-07-21 | P2.3 | `.venv/bin/python -m pytest services/control_api/tests -q` | 99 passed | Collision, staged workspace creation, and recoverable native-registration failure handling. |
| 2026-07-21 | P2.5 | `.venv/bin/python -m pytest services/control_api/tests -q` | 100 passed | Managed-manifest edit/archive synchronization. |
| 2026-07-21 | P2.6 | `.venv/bin/python -m pytest services/control_api/tests -q` | 100 passed | Failed native registration is repairable by reissuing the workspace-create request. |
| 2026-07-21 | P3.1–P3.5 | `.venv/bin/python -m pytest services/control_api/tests -q` | 105 passed | Managed repository lifecycle, clone failure repair, and repository attachment coverage. |
| 2026-07-21 | P5.1 | `.venv/bin/python -m pytest services/control_api/tests -q` | 109 passed | Work-thread projection, read APIs, root/retry latest-outcome behavior, and SQLite reload lineage coverage. |
| 2026-07-21 | P4.5 | `.venv/bin/python -m pytest services/control_api/tests/test_managed_workspace_api.py -q` | 13 passed | Append-only audit persistence/reload and authenticated per-slug timeline coverage. |
| 2026-07-21 | P4.4 | `.venv/bin/python -m pytest -q services/control_api/tests` | 125 passed | Clean-profile restore preserves the manifest slug, makes the workspace primary, registers a present declared repository folder, and blocks an existing native record without replacement. |
| 2026-07-21 | P5.4 | `.venv/bin/python -m pytest services/control_api/tests/test_native_project_integration.py services/control_api/tests/test_hermes_client.py -q` | 21 passed | Native session containment, stale-session rejection, and supported command continuation behavior. |
| 2026-07-21 | P5.3 | `.venv/bin/python -m pytest services/control_api/tests -q` | 127 passed | Guarded active/archived recovery actions, session continuation validation, idempotent retry/continue/edit/new-session attempts, non-mutating environment checks, and cancellation coverage. |
| 2026-07-21 | P6.1 | `pnpm run typecheck`; `pnpm run test:unit`; `python scripts/verify.py --maestro` | passed; 68 mobile tests; 3 Maestro flows | Corrected navigation contract and verified current-device Inbox/Projects/New/Activity/More navigation plus settings deep link. |
| 2026-07-21 | P7.2 | `python -m pytest -q`; `pnpm run test:unit` | 155 passed, 12 skipped; 68 mobile tests passed | Persisted queue/backoff/retry/discard helper tests and repeated-idempotency backend integration coverage passed. |
| 2026-07-21 | P6.4, P6.6 | `pnpm run typecheck`; `pnpm run test:unit`; `python -m pytest services/control_api/tests/test_managed_workspace_api.py -q`; `pnpx expo config --type public`; `git diff --check` | passed; 76 mobile tests; 24 API tests | Explicit managed-project registration repair, diagnostics readiness state, authenticated reviewed recovery apply, Activity search coverage, and Expo config validation. |
| 2026-07-21 | P7.1 | `pnpm exec vitest run src/state/data-store.test.ts`; `pnpm run typecheck`; `python -m pytest -q` | 9 store tests passed; typecheck passed; 156 passed, 12 skipped | Reconnect snapshot, ordered events, stale/duplicate suppression, gap refresh, reconnect, and cleanup are covered with mocked sockets and fake timers. |
| 2026-07-21 | P6.2, P6.3 | Prepared disposable native-store sandbox; release APK; physical-device Maestro populated Inbox/project-detail flow | passed | Verified attention, active, and recent work threads; native project card; project-detail ordering through sessions and workspace/repository management. Sandbox server, device app data, and reverse mapping were removed after validation. |
| 2026-07-21 | P6.5 | Prepared disposable native-store sandbox; release APK; physical-device Maestro task-detail flow | passed | Verified task-detail navigation from Inbox, current-attempt timeline row, and retry, edit-retry, and continuation controls. Sandbox server, device app data, and reverse mapping were removed after validation. |
| 2026-07-21 | P7.4 | `python scripts/verify.py --maestro`; `python scripts/secret_scan.py --all`; `git diff --check` | passed | Canonical verifier passed backend unit/integration/e2e checks, mobile typecheck/unit tests, Expo configuration, release APK build/sideload/launch, and smoke/settings/new-task Maestro flows; secret scan and whitespace check passed. |
| 2026-07-21 | P5.2, P7.3 | `python -m pytest -q services/control_api/tests/test_task_controls.py::test_work_thread_contract_uses_completed_retry_as_latest_for_historical_root services/control_api/tests/test_task_approvals.py`; `pnpm exec vitest run src/features/tasks/task-detail-state.test.ts src/features/tasks/inbox-work-thread-state.test.ts src/features/tasks/approval-audit.test.ts`; `pnpm run typecheck` | 8 backend tests passed; 6 mobile tests passed; typecheck passed | The work-thread API resolves historical failures to the latest completed retry; the mobile state preserves retry lineage and routes only the latest attempt to Inbox. Approval actor/device/reason metadata survives SQLite reload and approval-required work is included in the Inbox attention state. |
| 2026-07-21 | P7.5 (partial) | Physical Android device: loopback-only disposable API + `adb reverse`; `.maestro/p7-device-task.yaml`; authenticated task query | passed | The release APK saved temporary sandbox settings, submitted an actual task, opened task detail, and server state confirmed exactly one completed mobile task. Cleared app data, removed reverse mapping, and stopped the sandbox afterward. |
| 2026-07-21 | P7.5 workspace/clone (attempted) | Fresh release APK sideload; disposable loopback API and committed dumb-HTTP Git remote; live `/projects` and `/work-threads`; `.maestro/p7-workspace-clone.yaml` | blocked | Fixture/API/Git preflight passed, but Maestro could not begin because the Android device became locked and then `adb` changed to `unauthorized` (device confirmation required). No workspace or clone was created by this attempt. The flow now self-configures its fixture-only runtime API URL/token so it does not depend on another P7.5 flow's state. Stopped both fixture servers and destroyed the marker-protected fixture; reverse-mapping/device app cleanup could not be observed after authorization was lost. P7.5 remains open. |
| 2026-07-21 | P0.3 | `python -m pytest services/control_api/tests -q`; local Markdown link scan; `git diff --check` | 134 passed, 4 skipped; links/diff passed | Synthetic-ID migration contract is documented and guarded; existing native integration coverage rejects the legacy `default` ID. |
| 2026-07-21 | P7.5 recovery confirmation | Fresh release APK sideload; disposable loopback-only API + owned `adb reverse`; `.maestro/p7-recovery-plan.yaml`; authenticated `/projects`, `/recovery-plan`, and `/recovery-audit` postflight | passed | The physical-device flow configured only fixture settings, opened the ready recovery plan, explicitly selected Android `Restore`, and rendered `Restored: sandbox-recovery-ready.`. Live API then confirmed the new native project, `already_registered` reclassification, and append-only `restored` audit record. Cleared app data, removed the owned reverse mapping, stopped the fixture listener, and destroyed the marker-protected sandbox. |
| 2026-07-21 | P7.5 workspace/clone and retry/continuation | Fresh release APK; disposable loopback API; committed local dumb-HTTP Git remote; `.maestro/p7-workspace-clone.yaml`; task-detail action flow | passed | Physical device created managed workspace and clone-backed projects (both API creates returned 201); detail UI showed primary and repository folders. Continue created a linked completed attempt visible in a two-attempt immutable timeline. Owned servers/mappings, app state, and marked fixtures were removed. |
| 2026-07-21 | P7.5 offline queue | Cached fixture project list, then stopped listener and removed owned `adb reverse`; rebuilt release APK; `.maestro/p7-offline-queue.yaml` | blocked | Cached project selection remained available, but enabled Start Hermes task produced neither queue notice/card nor submission error. Added a 10-second request deadline with a test for an indefinitely pending fetch (`7` focused client tests passed), but the physical queue fallback still did not render. Requires root-cause reproduction before retry/discard/reconciliation can be credited. |
| 2026-07-21 | P7.5 WebSocket reconnect | Loopback device WebSocket connection plus mocked data-store lifecycle suite | partial | Device WebSocket traffic was observed; lifecycle tests cover reconnect snapshot/reconciliation. The clean-reset physical interruption/reconnect rendered-state assertion is flaky, so this is not completion evidence. |

## 10. Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-07-21 | Mobile Projects are native Hermes Projects. | The mobile app is a remote extension of Hermes Agent, not an app-owned hierarchy. |
| 2026-07-21 | New managed projects use `~/.hermes/workspaces/<slug>/`. | Workspaces can exist before repositories and are included in the active Hermes backup scope. |
| 2026-07-21 | Workspace root remains project primary folder; `repo/` is optional/additional. | Project-level planning/artifacts should remain valid execution context without assuming code exists. |
| 2026-07-21 | A portable `hermes-project.yaml` belongs in each managed workspace. | It enables reconstruction of native project registration after host loss without embedding secrets or host paths. |
| 2026-07-21 | Recovery requires a reviewable dry-run plan and explicit confirmation. | Avoid destructive/surprising re-registration and surface conflicts before mutation. |
| 2026-07-21 | Work threads, not task attempts, are the default mobile browsing unit. | Users need the latest outcome and retry lineage while retaining immutable diagnostic attempts. |

## 11. Out of scope for this plan

- Forced migration or automatic relocation of existing repositories/projects.
- Collecting or storing Git credentials in the mobile app.
- Automatic repository cloning during restoration.
- Replacing Hermes’ native project/session persistence with Control API persistence.
- Public internet exposure, multi-user SaaS identity, or infrastructure backup implementation.
- Promising background mobile notifications without a separately designed push/background delivery transport.

## 12. Implementation gate

Before beginning **P0.1**, obtain explicit approval to implement this plan. Execute one logical safety slice at a time: inspect exact code, add tests first where practical, make the minimal change, run targeted verification, run the canonical relevant verifier, inspect `git diff --check`, update this document’s evidence/progress, then commit the verified slice.
