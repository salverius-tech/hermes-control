# Mobile UX Remediation Implementation Plan

> **For Hermes:** Execute this plan task-by-task with test-first changes and logical commits.

**Goal:** Make the mobile control app easier to operate by adding safe task removal, a task-first navigation model, clearer action hierarchy, and accessible responsive controls.

**Architecture:** Retain task history through a soft archive rather than destructive deletion. The FastAPI API and `TaskProjection` own archive state; the Expo app consumes it as a list filter and provides confirmation plus read-only/offline safeguards. Navigation remains Expo Router based, with a persistent Tasks destination and settings gear on workspace roots.

**Tech Stack:** Python/FastAPI/Pydantic/SQLite; Expo Router/React Native/TypeScript/Vitest.

---

### Task 1: Add archived-task lifecycle model and projection behavior

**Files:**
- Modify: `services/control_api/models.py`
- Modify: `services/control_api/projection.py`
- Test: `services/control_api/tests/test_projection.py`

1. Add a nullable `archived_at` field to `TaskSummary`.
2. Add projection archive/restore methods, requiring terminal task states and writing a timeline event.
3. Add failing projection tests for terminal archive, active-task rejection, restore, event persistence, and default visibility.
4. Run focused tests before and after implementation.

### Task 2: Add authenticated archive API and persistence coverage

**Files:**
- Modify: `services/control_api/main.py`
- Modify: `services/control_api/tests/test_task_controls.py`
- Modify: `services/control_api/tests/test_persistence.py`

1. Add explicit command endpoints for archiving/restoring a task.
2. Return 404 for unknown tasks and a clear 409 for non-terminal task archive attempts.
3. Broadcast updated task snapshots so open clients reconcile.
4. Test endpoint responses and persisted archive state across projection recreation.
5. Commit backend lifecycle work.

### Task 3: Add task filter model and archive actions in Expo

**Files:**
- Create: `apps/mobile/src/features/tasks/filters.ts`
- Test: `apps/mobile/src/features/tasks/filters.test.ts`
- Modify: `apps/mobile/src/api/client.ts`
- Modify: `apps/mobile/app/tasks/index.tsx`
- Modify: `apps/mobile/app/tasks/[taskId].tsx`

1. Write filter tests covering inbox, active, history, archived, and search semantics.
2. Add the `archived_at` contract and archive filter helper.
3. Show Inbox by default and offer clear task state filters including Archived.
4. Add archive/restore action in task detail with confirmation and clear state-change feedback.
5. Disable mutating actions if detail is cached/stale.
6. Commit task lifecycle UX work.

### Task 4: Make Tasks a primary destination and Settings consistently reachable

**Files:**
- Modify: `apps/mobile/src/navigation/items.ts`
- Modify: `apps/mobile/src/navigation/items.test.ts`
- Modify: `apps/mobile/src/navigation/BottomNavigation.tsx`
- Modify: `apps/mobile/app/_layout.tsx`
- Modify: `apps/mobile/app/index.tsx`

1. Write/update nav tests for Home, Tasks, New, Projects, and Attention.
2. Make Tasks reachable persistently, preserve all routes with tab history replacement, and add explicit stack titles.
3. Apply the gear-only Settings action to workspace-root stack headers.
4. Convert Home’s attention/active summary cards into direct routes and remove redundant metrics/technical clutter.
5. Commit navigation/dashboard work.

### Task 5: Simplify project/task detail, feedback, and accessibility

**Files:**
- Modify: `apps/mobile/app/projects/[projectId].tsx`
- Modify: `apps/mobile/app/projects/manage.tsx`
- Modify: `apps/mobile/app/new-task.tsx`
- Modify: `apps/mobile/app/settings.tsx`
- Modify: `apps/mobile/src/components/ExpandableDetails.tsx`

1. Reduce project detail to work threads with filters and collapse raw identifiers/session lists into details.
2. Remove duplicate body headers where a stack header provides the title.
3. Replace operation-critical alerts with inline accessible feedback.
4. Add accessibility label/state/hint support and minimum touch targets to filters, chips, and action controls.
5. Add/update focused unit tests where logic is extracted.
6. Commit polish work.

### Task 6: Verify and review

1. Run focused backend tests after each backend slice, then `python -m pytest services/control_api/tests -q`.
2. Run mobile `pnpm run typecheck`, `pnpm run test:unit`, Expo config validation, and `git diff --check`.
3. Run the repository verifier if available.
4. Inspect device tooling; if no authorized device/ADB is available, record it as the physical-validation limitation rather than overstating evidence.
5. Review staged diffs, run a secret scan, and commit logical slices without pushing.

**Risks and decisions:**
- Soft archive is deliberately chosen over destructive deletion to preserve task/event audit trails and immutable retry chains.
- Archive only terminal tasks; active work must be canceled before it can be hidden.
- The existing uncommitted title-removal changes are in scope and will be included in the relevant navigation/polish commit after verification.
