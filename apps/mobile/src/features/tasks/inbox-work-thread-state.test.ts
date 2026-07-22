import { describe, expect, it } from 'vitest';

import type { TaskStatus, TaskSummary, WorkThreadSummary } from '@/api/client';

import { inboxWorkThreadState } from './inbox-work-thread-state';

function attempt(taskId: string, status: TaskStatus, updatedAt: string, archivedAt: string | null = null): TaskSummary {
  return {
    archived_at: archivedAt,
    created_at: updatedAt,
    priority: 'normal',
    progress_log: [],
    project_id: 'mobile-control',
    prompt: `Prompt for ${taskId}`,
    requires_approval: false,
    source: 'mobile',
    status,
    task_id: taskId,
    title: taskId,
    updated_at: updatedAt,
  };
}

function thread(rootTaskId: string, latest: TaskSummary, attempts: TaskSummary[] = [latest]): WorkThreadSummary {
  return {
    attempts,
    latest_attempt: latest,
    latest_outcome: latest.status,
    project_id: latest.project_id,
    root_task_id: rootTaskId,
  };
}

describe('inboxWorkThreadState', () => {
  it('uses each thread latest attempt so a resolved retry is not kept in attention', () => {
    const originalFailure = attempt('original-failure', 'failed', '2026-07-20T09:00:00Z');
    const resolvedRetry = attempt('resolved-retry', 'completed', '2026-07-20T11:00:00Z');
    const state = inboxWorkThreadState([
      thread('resolved-root', resolvedRetry, [originalFailure, resolvedRetry]),
      thread('failed-root', attempt('failed-latest', 'failed', '2026-07-20T12:00:00Z')),
      thread('approval-root', attempt('approval-latest', 'awaiting_approval', '2026-07-20T10:00:00Z')),
      thread('quiet-root', attempt('quiet-latest', 'attention_required', '2026-07-20T13:00:00Z')),
      thread('running-root', attempt('running-latest', 'running', '2026-07-20T14:00:00Z')),
      thread('queued-root', attempt('queued-latest', 'queued', '2026-07-20T15:00:00Z')),
    ]);

    expect(state.attentionRequired.map((item) => item.root_task_id)).toEqual(['quiet-root', 'failed-root', 'approval-root']);
    expect(state.active.map((item) => item.root_task_id)).toEqual(['queued-root', 'running-root']);
    expect(state.recentlyResolved.map((item) => item.root_task_id)).toEqual(['resolved-root']);
  });

  it('shows unarchived terminal latest attempts as recent work and excludes archived threads', () => {
    const state = inboxWorkThreadState([
      thread('canceled-root', attempt('canceled-latest', 'canceled', '2026-07-20T12:00:00Z')),
      thread('rejected-root', attempt('rejected-latest', 'rejected', '2026-07-20T13:00:00Z')),
      thread('blocked-root', attempt('blocked-latest', 'blocked', '2026-07-20T14:00:00Z')),
      thread('archived-root', attempt('archived-latest', 'completed', '2026-07-20T15:00:00Z', '2026-07-20T16:00:00Z')),
    ]);

    expect(state.attentionRequired.map((item) => item.root_task_id)).toEqual(['blocked-root']);
    expect(state.recentlyResolved.map((item) => item.root_task_id)).toEqual(['rejected-root', 'canceled-root']);
  });
});
