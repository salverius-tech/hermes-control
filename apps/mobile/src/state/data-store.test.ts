import { describe, expect, it, vi } from 'vitest';

vi.mock('@react-native-async-storage/async-storage', () => ({
  default: { getItem: vi.fn(), setItem: vi.fn() },
}));
vi.mock('expo-secure-store', () => ({
  getItemAsync: vi.fn(),
  setItemAsync: vi.fn(),
}));

import { normalizeCachedData } from './data-store';

describe('normalizeCachedData', () => {
  it('derives one work thread per task for legacy cached data', () => {
    const task = { project_id: 'ops', root_task_id: null, status: 'completed', task_id: 'task-1' };
    const legacyCache = { tasks: [task], stale: false };

    expect(normalizeCachedData(legacyCache)).toMatchObject({
      tasks: [task],
      stale: false,
      workThreads: [{ root_task_id: 'task-1', project_id: 'ops', attempts: [task], latest_attempt: task, latest_outcome: 'completed' }],
    });
  });

  it('preserves cached work threads from current cache data', () => {
    const workThreads = [{ root_task_id: 'task-1' }];

    expect(normalizeCachedData({ workThreads })).toMatchObject({ workThreads });
  });
});