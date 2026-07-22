import { describe, expect, it } from 'vitest';

import type { TaskSummary, WorkThreadSummary } from '@/api/client';

import { attemptTimeline, availableRecoveryActions } from './task-detail-state';

function task(taskId: string, overrides: Partial<TaskSummary> = {}): TaskSummary {
  return {
    created_at: '2026-07-21T09:00:00Z',
    priority: 'normal',
    progress_log: [],
    project_id: 'ops',
    prompt: `Prompt ${taskId}`,
    requires_approval: false,
    source: 'mobile',
    status: 'failed',
    task_id: taskId,
    title: taskId,
    updated_at: '2026-07-21T09:00:00Z',
    ...overrides,
  };
}

describe('task detail state', () => {
  it('makes continuation primary only when the recoverable attempt has a session', () => {
    expect(availableRecoveryActions(task('with-session', { session_id: 'session-1' }))).toEqual([
      'check_environment', 'continue_session', 'edit_retry', 'start_new_session',
    ]);
    expect(availableRecoveryActions(task('without-session'))).toEqual([
      'check_environment', 'edit_retry', 'start_new_session',
    ]);
    expect(availableRecoveryActions(task('active', { status: 'running' }))).toEqual([]);
  });

  it('keeps immutable attempts in server order and labels their retry lineage', () => {
    const original = task('original', { status: 'failed' });
    const retry = task('retry', { relation: 'edited_retry', parent_task_id: 'original', root_task_id: 'original', status: 'completed' });
    const thread: WorkThreadSummary = {
      attempts: [original, retry],
      latest_attempt: retry,
      latest_outcome: 'completed',
      project_id: 'ops',
      root_task_id: 'original',
    };

    expect(attemptTimeline(thread, 'original')).toEqual([
      { task: original, label: 'Original request', isCurrent: true },
      { task: retry, label: 'Edited retry', isCurrent: false },
    ]);
  });
});
