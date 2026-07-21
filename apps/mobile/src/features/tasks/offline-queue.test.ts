import { describe, expect, it, vi } from 'vitest';

import { enqueueTask, flushTaskQueue, loadTaskQueue, retryQueuedTask, taskQueueStorageKey, type QueueStorage } from './offline-queue';

function memoryStorage(): QueueStorage & { values: Map<string, string> } {
  const values = new Map<string, string>();
  return {
    values,
    getItem: async (key) => values.get(key) ?? null,
    setItem: async (key, value) => { values.set(key, value); },
  };
}

const request = { prompt: 'Inspect offline retry behavior', project_id: 'ops', priority: 'normal' as const, requires_approval: false };

describe('offline task queue', () => {
  it('persists a caller-created idempotency key before retrying an uncertain submission', async () => {
    const storage = memoryStorage();

    const queued = await enqueueTask(storage, request, new Date('2026-07-21T12:00:00Z'), 'mobile-request-1');

    expect(queued.idempotency_key).toBe('mobile-request-1');
    expect((await loadTaskQueue(storage))[0]).toMatchObject({
      idempotency_key: 'mobile-request-1',
      local_id: 'local-mobile-request-1',
      state: 'pending',
    });
  });

  it('reuses the persisted key after a lost response and removes the queue entry on success', async () => {
    const storage = memoryStorage();
    await enqueueTask(storage, request, new Date('2026-07-21T12:00:00Z'), 'mobile-request-2');
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.headers).toMatchObject({ 'Idempotency-Key': 'mobile-request-2' });
      return new Response(JSON.stringify({ task_id: 'task-original' }), { status: 201 });
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(flushTaskQueue(storage, 'http://localhost:8787', 'token', new Date('2026-07-21T12:00:00Z'))).resolves.toEqual([{ task_id: 'task-original' }]);
    await expect(loadTaskQueue(storage)).resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('backs off transport failures and lets explicit retry clear the backoff without changing the key', async () => {
    const storage = memoryStorage();
    await enqueueTask(storage, request, new Date('2026-07-21T12:00:00Z'), 'mobile-request-3');
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network unavailable'); }));

    await flushTaskQueue(storage, 'http://localhost:8787', 'token', new Date('2026-07-21T12:00:00Z'));
    const failed = (await loadTaskQueue(storage))[0];
    expect(failed).toMatchObject({ idempotency_key: 'mobile-request-3', state: 'retrying', attempts: 1 });
    expect(failed.next_attempt_at).toBe('2026-07-21T12:00:02.000Z');

    await retryQueuedTask(storage, failed.local_id, new Date('2026-07-21T12:01:00Z'));
    expect((await loadTaskQueue(storage))[0]).toMatchObject({ idempotency_key: 'mobile-request-3', state: 'pending', attempts: 0, next_attempt_at: '2026-07-21T12:01:00.000Z' });
    expect(storage.values.has(taskQueueStorageKey)).toBe(true);
  });
});