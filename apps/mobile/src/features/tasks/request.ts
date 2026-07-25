export type TaskPriority = 'low' | 'normal' | 'high';

export type TaskCreateForm = {
  prompt: string;
  projectId: string;
  provider?: string;
  model?: string;
  priority: TaskPriority;
  requiresApproval: boolean;
};

export type TaskCreateRequest = {
  prompt: string;
  project_id: string;
  provider?: string;
  model?: string;
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

  const request: TaskCreateRequest = {
    prompt,
    project_id: form.projectId.trim() || 'default',
    priority: form.priority,
    requires_approval: form.requiresApproval,
  };

  const provider = form.provider?.trim();
  const model = form.model?.trim();
  if (provider) request.provider = provider;
  if (model) request.model = model;
  return request;
}
