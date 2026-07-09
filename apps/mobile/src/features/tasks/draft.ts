import { type TaskPriority } from './request';

export const taskDraftStorageKey = 'tasks:new:draft';

export type TaskDraft = {
  prompt: string;
  projectId: string;
  priority: TaskPriority;
  requiresApproval: boolean;
};

export type TaskDraftStorage = {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
  removeItem: (key: string) => Promise<void>;
};

const priorities: TaskPriority[] = ['low', 'normal', 'high'];

function isPriority(value: unknown): value is TaskPriority {
  return typeof value === 'string' && priorities.includes(value as TaskPriority);
}

export async function loadTaskDraft(storage: TaskDraftStorage): Promise<TaskDraft | null> {
  const raw = await storage.getItem(taskDraftStorageKey);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<TaskDraft>;
    if (typeof parsed.prompt !== 'string' || !isPriority(parsed.priority)) {
      return null;
    }
    return {
      prompt: parsed.prompt.trim(),
      projectId: typeof parsed.projectId === 'string' ? parsed.projectId.trim() || 'default' : 'default',
      priority: parsed.priority,
      requiresApproval: parsed.requiresApproval === true,
    };
  } catch {
    return null;
  }
}

export async function saveTaskDraft(storage: TaskDraftStorage, draft: TaskDraft): Promise<void> {
  await storage.setItem(
    taskDraftStorageKey,
    JSON.stringify({
      prompt: draft.prompt.trim(),
      projectId: draft.projectId.trim() || 'default',
      priority: draft.priority,
      requiresApproval: draft.requiresApproval,
    }),
  );
}

export async function clearTaskDraft(storage: TaskDraftStorage): Promise<void> {
  await storage.removeItem(taskDraftStorageKey);
}
