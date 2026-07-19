import type { TaskStatus, TaskSummary } from '@/api/client';

export type TaskFilter = 'inbox' | 'all' | 'active' | 'completed' | 'archived';

export const taskFilters: ReadonlyArray<{ label: string; value: TaskFilter }> = [
  { label: 'Inbox', value: 'inbox' },
  { label: 'All', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Done', value: 'completed' },
  { label: 'Archived', value: 'archived' },
];

const activeStatuses: TaskStatus[] = ['awaiting_approval', 'queued', 'running', 'failed', 'blocked'];

export function filterTasks(tasks: TaskSummary[], filter: TaskFilter, query: string): TaskSummary[] {
  const normalizedQuery = query.trim().toLowerCase();
  return tasks.filter((task) => {
    if (filter === 'archived' ? !task.archived_at : task.archived_at) return false;
    if (filter === 'inbox' && !activeStatuses.includes(task.status)) return false;
    if (filter === 'active' && !['awaiting_approval', 'queued', 'running'].includes(task.status)) return false;
    if (filter === 'completed' && task.status !== 'completed') return false;
    return !normalizedQuery || `${task.title} ${task.prompt} ${task.project_id}`.toLowerCase().includes(normalizedQuery);
  }).sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
}
