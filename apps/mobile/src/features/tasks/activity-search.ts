import type { TaskSummary, WorkThreadSummary } from '@/api/client';

import { filterTasks, type TaskFilter } from './filters';

function normalizedActivityText(task: TaskSummary): string {
  return [
    task.title,
    task.prompt,
    task.project_id,
    task.status,
    task.result_summary,
    task.error,
    task.blocker_category,
    task.blocker_message,
    ...task.progress_log,
  ].filter(Boolean).join(' ').toLowerCase();
}

/**
 * Filters the Activity feed by the current attempt's lifecycle while allowing a
 * search to find relevant details from any immutable attempt in the thread.
 */
export function filterActivityThreads(
  workThreads: WorkThreadSummary[],
  filter: TaskFilter,
  query: string,
): WorkThreadSummary[] {
  const visibleLatestIds = new Set(filterTasks(
    workThreads.map((thread) => thread.latest_attempt),
    filter,
    '',
  ).map((task) => task.task_id));
  const normalizedQuery = query.trim().toLowerCase();

  return workThreads
    .filter((thread) => visibleLatestIds.has(thread.latest_attempt.task_id))
    .filter((thread) => !normalizedQuery || thread.attempts.some((attempt) => normalizedActivityText(attempt).includes(normalizedQuery)))
    .sort((left, right) => Date.parse(right.latest_attempt.updated_at) - Date.parse(left.latest_attempt.updated_at));
}
