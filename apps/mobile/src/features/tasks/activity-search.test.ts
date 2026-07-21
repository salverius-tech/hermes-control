import { describe, expect, it } from 'vitest';

import type { TaskStatus, TaskSummary, WorkThreadSummary } from '@/api/client';

import { filterActivityThreads } from './activity-search';

function attempt(
  taskId: string,
  status: TaskStatus,
  updatedAt: string,
  overrides: Partial<TaskSummary> = {},
): TaskSummary {
  return {
    archived_at: null,
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
    ...overrides,
  };
}

function thread(rootTaskId: string, attempts: TaskSummary[]): WorkThreadSummary {
  const latestAttempt = attempts.at(-1)!;
  return {
    attempts,
    latest_attempt: latestAttempt,
    latest_outcome: latestAttempt.status,
    project_id: latestAttempt.project_id,
    root_task_id: rootTaskId,
  };
}

describe('filterActivityThreads', () => {
  it('searches immutable activity history while retaining the current lifecycle filter', () => {
    const originalFailure = attempt('original', 'failed', '2026-07-20T09:00:00Z', {
      error: 'Permission denied while opening deployment logs',
    });
    const completedRetry = attempt('retry', 'completed', '2026-07-20T11:00:00Z');
    const activeThread = thread('active-root', [attempt('active', 'running', '2026-07-20T12:00:00Z')]);
    const resolvedThread = thread('resolved-root', [originalFailure, completedRetry]);

    expect(filterActivityThreads([activeThread, resolvedThread], 'all', 'deployment logs').map((item) => item.root_task_id))
      .toEqual(['resolved-root']);
    expect(filterActivityThreads([activeThread, resolvedThread], 'inbox', 'deployment logs')).toEqual([]);
  });

  it('searches result, blocker, progress, status, and project metadata', () => {
    const completed = thread('completed-root', [attempt('completed', 'completed', '2026-07-20T11:00:00Z', {
      progress_log: ['Downloaded release artifact'],
      project_id: 'release-tools',
      result_summary: 'Published version 1.2.3',
    })]);
    const blocked = thread('blocked-root', [attempt('blocked', 'blocked', '2026-07-20T12:00:00Z', {
      blocker_category: 'connectivity',
      blocker_message: 'Bridge is unavailable',
    })]);

    expect(filterActivityThreads([completed, blocked], 'all', 'published version').map((item) => item.root_task_id))
      .toEqual(['completed-root']);
    expect(filterActivityThreads([completed, blocked], 'all', 'release artifact').map((item) => item.root_task_id))
      .toEqual(['completed-root']);
    expect(filterActivityThreads([completed, blocked], 'inbox', 'connectivity').map((item) => item.root_task_id))
      .toEqual(['blocked-root']);
    expect(filterActivityThreads([completed, blocked], 'all', 'completed').map((item) => item.root_task_id))
      .toEqual(['completed-root']);
    expect(filterActivityThreads([completed, blocked], 'all', 'release-tools').map((item) => item.root_task_id))
      .toEqual(['completed-root']);
  });
});
