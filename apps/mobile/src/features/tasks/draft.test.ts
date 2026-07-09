import { describe, expect, it } from 'vitest';

import { clearTaskDraft, loadTaskDraft, saveTaskDraft, taskDraftStorageKey, type TaskDraftStorage } from './draft';

function memoryStorage(seed: Record<string, string | null> = {}) {
  const values = new Map(Object.entries(seed));
  const storage: TaskDraftStorage = {
    async getItem(key) {
      return values.get(key) ?? null;
    },
    async setItem(key, value) {
      values.set(key, value);
    },
    async removeItem(key) {
      values.delete(key);
    },
  };
  return { storage, values };
}

describe('task draft persistence', () => {
  it('loads null when no draft has been saved', async () => {
    const { storage } = memoryStorage();

    await expect(loadTaskDraft(storage)).resolves.toBeNull();
  });

  it('saves and loads a trimmed task draft', async () => {
    const { storage } = memoryStorage();

    await saveTaskDraft(storage, {
      prompt: '  summarize the repo  ',
      projectId: '  mobile  ',
      priority: 'high',
      requiresApproval: true,
    });

    await expect(loadTaskDraft(storage)).resolves.toEqual({
      prompt: 'summarize the repo',
      projectId: 'mobile',
      priority: 'high',
      requiresApproval: true,
    });
  });

  it('ignores invalid or corrupt saved drafts', async () => {
    const { storage, values } = memoryStorage({ [taskDraftStorageKey]: '{"priority":"urgent"}' });

    await expect(loadTaskDraft(storage)).resolves.toBeNull();
    values.set(taskDraftStorageKey, 'not json');
    await expect(loadTaskDraft(storage)).resolves.toBeNull();
  });

  it('clears saved drafts', async () => {
    const { storage, values } = memoryStorage({ [taskDraftStorageKey]: '{"prompt":"x"}' });

    await clearTaskDraft(storage);

    expect(values.has(taskDraftStorageKey)).toBe(false);
  });
});
