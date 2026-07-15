import type { TaskSummary } from '@/api/client';
import { apiFetch } from '@/api/client';
import type { TaskCreateRequest } from './request';

export const taskQueueStorageKey = 'tasks:offline-queue:v1';

export type QueuedTask = {
  local_id: string;
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

export async function enqueueTask(storage: QueueStorage, request: TaskCreateRequest, now = new Date(), localId?: string): Promise<QueuedTask> {
  const item: QueuedTask = {
    local_id: localId || `local-${now.getTime()}-${Math.random().toString(16).slice(2)}`,
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
        headers: { 'Idempotency-Key': item.local_id },
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
