import { describe, expect, it, vi } from 'vitest';

import { readCache, writeCache, type CacheStorage } from './cache';

describe('api cache', () => {
  function memoryStorage(): CacheStorage & { values: Map<string, string> } {
    const values = new Map<string, string>();
    return {
      values,
      async getItem(key) {
        return values.get(key) ?? null;
      },
      async setItem(key, value) {
        values.set(key, value);
      },
    };
  }

  it('round-trips JSON values through the supplied storage', async () => {
    const storage = memoryStorage();

    await writeCache(storage, 'tasks', [{ task_id: 'task-1' }]);

    await expect(readCache<{ task_id: string }[]>(storage, 'tasks')).resolves.toEqual([{ task_id: 'task-1' }]);
  });

  it('returns null for corrupt cached JSON', async () => {
    const storage = memoryStorage();
    storage.values.set('bad', '{not-json');

    await expect(readCache(storage, 'bad')).resolves.toBeNull();
  });

  it('does not throw when cache writes fail', async () => {
    const storage: CacheStorage = {
      getItem: vi.fn(),
      setItem: vi.fn(async () => {
        throw new Error('quota exceeded');
      }),
    };

    await expect(writeCache(storage, 'tasks', [])).resolves.toBeUndefined();
  });
});
