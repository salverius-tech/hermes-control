# Native Hermes Projects & Mobile Operator Experience — Implementation Plan

> **Status:** Proposed; implementation has not been approved.  
> **Progress:** 7 / 31 implementation tasks complete.  
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
  **Evidence:** checked-in technical specification plus native-schema fixtures.
- [ ] **P0.3** Define public API compatibility/migration behavior for synthetic task-derived project IDs.  
  **Evidence:** documented API migration decision and negative-route tests.

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
- [ ] **P2.2** Define Pydantic/domain models for managed-project origin (`workspace`, `clone`, `adopt`) and manifest schema v1.  
  **Evidence:** schema validation tests including invalid relative paths and unknown versions.
- [ ] **P2.3** Implement safe workspace slug allocation and atomic workspace/bootstrap file creation.  
  **Evidence:** collision, invalid slug, partial-write, and idempotence tests.
- [x] **P2.4** Implement workspace-only native Hermes Project creation: create workspace, write pending manifest, create native project with explicit slug/primary folder, verify, mark registered.  
  **Evidence:** integration test against native-project SQLite fixture.
- [ ] **P2.5** Synchronize native project edits/folder/archive operations to a managed workspace manifest; do not create manifests for adopted legacy projects unless explicitly adopted later.  
  **Evidence:** update and archive synchronization tests.
- [ ] **P2.6** Add repair-state behavior for workspace exists/native registration failed.  
  **Evidence:** failed-registration recovery test and clear API error/result contract.

## Phase 3 — Repository lifecycle

- [ ] **P3.1** Add server-side Git adapter with argument-array execution, bounded output, timeout/cancellation, and sanitized diagnostics.  
  **Evidence:** adapter unit tests; no shell execution path.
- [ ] **P3.2** Implement clone-backed project creation: bootstrap workspace, clone to `repo/`, register workspace primary plus repo folder, verify, update manifest.  
  **Evidence:** end-to-end clone fixture test.
- [ ] **P3.3** Reject unsafe URLs, non-empty destinations, path collisions, and unauthorized/unavailable Git authentication cleanly.  
  **Evidence:** negative tests and sanitized error assertions.
- [ ] **P3.4** Preserve successfully cloned files when later native registration fails; mark repairable state and expose an explicit repair action.  
  **Evidence:** partial-failure integration test.
- [ ] **P3.5** Support attaching/cloning a repository into an existing workspace-only project.  
  **Evidence:** API/manifest/native-folder synchronization tests.

## Phase 4 — Reviewable recovery

- [ ] **P4.1** Implement manifest discovery and validation confined to the managed workspace root.  
  **Evidence:** valid, missing, malformed, duplicate-slug, and traversal fixtures.
- [ ] **P4.2** Implement a read-only recovery-plan API that classifies entries as ready, already registered, missing repository, blocked, or conflict.  
  **Evidence:** no mutation during dry-run test.
- [ ] **P4.3** Implement explicit recovery apply requiring selected-plan confirmation/revalidation.  
  **Evidence:** confirm/cancel tests; changed manifest after plan generation is revalidated.
- [ ] **P4.4** Recreate missing native Hermes Projects with stable slug, workspace primary folder, and present optional repo folder; never overwrite existing records.  
  **Evidence:** clean-profile restoration integration test.
- [ ] **P4.5** Add durable recovery audit events and per-project result reporting.  
  **Evidence:** persistence/reload and API timeline tests.

## Phase 5 — Work-thread projection and task recovery

- [ ] **P5.1** Define a work-thread read model grouping root task and linked retries/continuations/follow-ups.  
  **Evidence:** lineage projection tests across persisted reload.
- [ ] **P5.2** Add latest-attempt/latest-outcome semantics and visible historical-to-latest links.  
  **Evidence:** API and mobile filtering tests for failed-then-completed lineage.
- [ ] **P5.3** Implement guarded Continue current session, Edit before retry, Start new session, Check environment, and Cancel flows.  
  **Evidence:** state-transition, session-validation, and idempotency tests.
- [ ] **P5.4** Capture/validate Hermes session identifiers and use supported continuation behavior.  
  **Evidence:** continuation integration test and native session containment test.
- [ ] **P5.5** Add activity-aware task state fields/events and distinguish quiet-but-alive, missing-heartbeat, interrupted, blocked, failed, and completed outcomes.  
  **Evidence:** targeted bridge/API tests for each transition.

## Phase 6 — Mobile information architecture and screens

- [ ] **P6.1** Replace the competing Home/Tasks/Projects/Attention model with Inbox, Projects, New, Activity, and More, preserving deep links and accessible navigation.  
  **Evidence:** navigation unit tests and rendered mobile smoke test.
- [ ] **P6.2** Build Inbox around attention-required, active, and recently resolved work threads.  
  **Evidence:** state/filter tests and manual visual review.
- [ ] **P6.3** Rebuild Project detail as attention → active work → recent work → sessions → workspace/repository management.  
  **Evidence:** mobile component/screen tests and device review.
- [ ] **P6.4** Replace the current manual-folder-first project form with workspace, clone, and adopt modes; show progress/error/repair states.  
  **Evidence:** API-client and form-state tests.
- [ ] **P6.5** Add work-thread task detail UI with latest outcome, attempt timeline, retry lineage, and recovery actions.  
  **Evidence:** mobile unit tests plus device flow.
- [ ] **P6.6** Add Activity search/history and More diagnostics/recovery-plan screens.  
  **Evidence:** API contract and screen-state tests.

## Phase 7 — Sync, offline behavior, and validation

- [ ] **P7.1** Centralize client REST/WebSocket reconciliation with reconnect snapshot, stale-event handling, sequence-gap refresh, and connection status.  
  **Evidence:** store tests using ordered/out-of-order/disconnected event sequences.
- [ ] **P7.2** Implement persisted offline submission queue with stable pre-request idempotency keys, backoff, reconcile, retry, and discard controls.  
  **Evidence:** client tests plus repeated-key API integration test.
- [ ] **P7.3** Add approval audit metadata where supported and surface approval work in Inbox.  
  **Evidence:** durable event payload tests and mobile screen test.
- [ ] **P7.4** Run full backend, mobile, canonical, secret-scan, and diff checks after each completed phase.  
  **Evidence:** exact commands/pass counts recorded below.
- [ ] **P7.5** Perform physical-device validation: native project list, workspace creation, repository clone, task execution, retry/continuation, WebSocket reconnect, offline queue, and recovery-plan confirmation.  
  **Evidence:** device model-independent test record; redact infrastructure identifiers and credentials.

---

## 9. Verification record

Add entries here only after running the command against the current relevant revision.

| Date | Phase/task | Command or procedure | Result | Notes |
|---|---|---|---|
| 2026-07-21 | P1.1–P1.5 | `.venv/bin/python -m pytest services/control_api/tests -q` | 95 passed | Native projection, strict production mode, task-context validation, and diagnostics coverage. |
| 2026-07-21 | P1.1–P1.5 | `git diff --check` | passed | No whitespace errors. |
| 2026-07-21 | P2.1, P2.4 (partial Phase 2) | `.venv/bin/python -m pytest services/control_api/tests -q` | 97 passed | Managed workspace configuration, manifest creation, collision handling, and native registration. |

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
