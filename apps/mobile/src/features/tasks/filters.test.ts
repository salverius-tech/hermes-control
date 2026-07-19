import { describe, expect, it } from 'vitest';

import type { TaskSummary } from '@/api/client';
import { filterTasks, taskFilters } from './filters';

function task(overrides: Partial<TaskSummary>): TaskSummary {
  return {
    archived_at: null,
    created_at: '2026-07-19T09:00:00Z',
    priority: 'normal',
    progress_log: [],
    project_id: 'default',
    prompt: 'Investigate the task',
    requires_approval: false,
    source: 'mobile',
    status: 'completed',
    task_id: 'task-1',
    title: 'Investigate the task',
    updated_at: '2026-07-19T10:00:00Z',
    ...overrides,
  };
}

describe('task filters', () => {
  const tasks = [
    task({ task_id: 'active', status: 'running' }),
    task({ task_id: 'attention', status: 'failed' }),
    task({ task_id: 'done', status: 'completed' }),
    task({ task_id: 'archived', archived_at: '2026-07-19T10:01:00Z' }),
  ];

  it('makes actionable and active work the default inbox', () => {
    expect(taskFilters[0]).toMatchObject({ label: 'Inbox', value: 'inbox' });
    expect(filterTasks(tasks, 'inbox', '').map((item) => item.task_id)).toEqual(['active', 'attention']);
  });

  it('keeps archived tasks out of every active view and makes them discoverable', () => {
    expect(filterTasks(tasks, 'all', '').map((item) => item.task_id)).toEqual(['active', 'attention', 'done']);
    expect(filterTasks(tasks, 'archived', '').map((item) => item.task_id)).toEqual(['archived']);
  });

  it('applies search within the selected lifecycle view', () => {
    expect(filterTasks(tasks, 'inbox', 'investigate').map((item) => item.task_id)).toEqual(['active', 'attention']);
    expect(filterTasks(tasks, 'archived', 'investigate').map((item) => item.task_id)).toEqual(['archived']);
  });
});
