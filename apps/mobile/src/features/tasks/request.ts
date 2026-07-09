export type TaskPriority = 'low' | 'normal' | 'high';

export type TaskCreateForm = {
  prompt: string;
  projectId: string;
  priority: TaskPriority;
  requiresApproval: boolean;
};

export type TaskCreateRequest = {
  prompt: string;
  project_id: string;
  priority: TaskPriority;
  requires_approval: boolean;
};

export const priorityOptions: Array<{ label: string; value: TaskPriority }> = [
  { label: 'Low', value: 'low' },
  { label: 'Normal', value: 'normal' },
  { label: 'High', value: 'high' },
];

export function buildTaskCreateRequest(form: TaskCreateForm): TaskCreateRequest {
  const prompt = form.prompt.trim();
  if (!prompt) {
    throw new Error('Prompt is required');
  }

  return {
    prompt,
    project_id: form.projectId.trim() || 'default',
    priority: form.priority,
    requires_approval: form.requiresApproval,
  };
}
