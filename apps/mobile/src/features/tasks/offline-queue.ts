import type { TaskSummary } from '@/api/client';
import { apiFetch } from '@/api/client';
import type { TaskCreateRequest } from './request';

export const taskQueueStorageKey = 'tasks:offline-queue:v1';

export type QueuedTask = {
  local_id: string;
  /** Stable request identity, created before the first network attempt. */
  idempotency_key: string;
  request: TaskCreateRequest;
  state: 'pending' | 'retrying';
  attempts: number;
  created_at: string;
  next_attempt_at: string;
};

export type QueueStorage = {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
};

function backoff(attempts: number): number {
  return Math.min(300000, 1000 * 2 ** Math.min(attempts, 8));
}

export async function loadTaskQueue(storage: QueueStorage): Promise<QueuedTask[]> {
  try {
    const raw = await storage.getItem(taskQueueStorageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((item): item is QueuedTask => Boolean(item && typeof item === 'object' && 'request' in item)) : [];
  } catch {
    return [];
  }
}

async function saveTaskQueue(storage: QueueStorage, queue: QueuedTask[]): Promise<void> {
  await storage.setItem(taskQueueStorageKey, JSON.stringify(queue));
}

export async function enqueueTask(storage: QueueStorage, request: TaskCreateRequest, now = new Date(), idempotencyKey?: string): Promise<QueuedTask> {
  const key = idempotencyKey || `mobile-${now.getTime()}-${Math.random().toString(16).slice(2)}`;
  const item: QueuedTask = {
    local_id: `local-${key}`,
    idempotency_key: key,
    request,
    state: 'pending',
    attempts: 0,
    created_at: now.toISOString(),
    next_attempt_at: now.toISOString(),
  };
  const queue = await loadTaskQueue(storage);
  queue.push(item);
  await saveTaskQueue(storage, queue);
  return item;
}

export async function removeQueuedTask(storage: QueueStorage, localId: string): Promise<void> {
  const queue = await loadTaskQueue(storage);
  await saveTaskQueue(storage, queue.filter((item) => item.local_id !== localId));
}

export async function retryQueuedTask(storage: QueueStorage, localId: string, now = new Date()): Promise<void> {
  const queue = await loadTaskQueue(storage);
  await saveTaskQueue(storage, queue.map((item) => item.local_id === localId ? { ...item, state: 'pending', attempts: 0, next_attempt_at: now.toISOString() } : item));
}
export async function flushTaskQueue(
  storage: QueueStorage,
  apiUrl: string,
  apiToken: string,
  now = new Date(),
): Promise<TaskSummary[]> {
  const queue = await loadTaskQueue(storage);
  const completed: TaskSummary[] = [];
  const remaining: QueuedTask[] = [];
  for (const item of queue) {
    if (Date.parse(item.next_attempt_at) > now.getTime()) {
      remaining.push(item);
      continue;
    }
    try {
      const task = await apiFetch<TaskSummary>(apiUrl, apiToken, '/tasks', {
        method: 'POST',
        // Older persisted queue entries used local_id as their key. Keep those
        // retryable while new entries retain an explicit transport identity.
        headers: { 'Idempotency-Key': item.idempotency_key || item.local_id },
        body: JSON.stringify(item.request),
      });
      completed.push(task);
    } catch {
      const attempts = item.attempts + 1;
      remaining.push({ ...item, state: 'retrying', attempts, next_attempt_at: new Date(now.getTime() + backoff(attempts)).toISOString() });
    }
  }
  await saveTaskQueue(storage, remaining);
  return completed;
}
