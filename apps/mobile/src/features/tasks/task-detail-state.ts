import type { TaskSummary, WorkThreadSummary } from '@/api/client';

export type RecoveryAction = 'check_environment' | 'continue_session' | 'edit_retry' | 'start_new_session';

const recoverableStatuses = new Set(['failed', 'blocked', 'completed', 'canceled', 'rejected']);

export function availableRecoveryActions(task: TaskSummary): RecoveryAction[] {
  if (!recoverableStatuses.has(task.status)) return [];

  return [
    'check_environment',
    ...(task.session_id ? (['continue_session'] as const) : []),
    'edit_retry',
    'start_new_session',
  ];
}

/** Server ordering is authoritative; add durable, human-readable retry lineage labels. */
export function attemptTimeline(thread: WorkThreadSummary, currentTaskId: string): Array<{ task: TaskSummary; label: string; isCurrent: boolean }> {
  return thread.attempts.map((task, index) => ({
    task,
    isCurrent: task.task_id === currentTaskId,
    label: index === 0 ? 'Original request' : relationLabel(task.relation),
  }));
}

export function relationLabel(relation?: TaskSummary['relation']): string {
  switch (relation) {
    case 'continuation': return 'Continued session';
    case 'edited_retry': return 'Edited retry';
    case 'retry': return 'New-session retry';
    case 'follow_up': return 'Follow-up';
    default: return 'Original request';
  }
}
