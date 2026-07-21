import type { TaskStatus, WorkThreadSummary } from '@/api/client';

export type InboxWorkThreadState = {
  attentionRequired: WorkThreadSummary[];
  active: WorkThreadSummary[];
  recentlyResolved: WorkThreadSummary[];
};

const attentionRequiredStatuses: ReadonlySet<TaskStatus> = new Set([
  'awaiting_approval',
  'attention_required',
  'blocked',
  'failed',
]);
const activeStatuses: ReadonlySet<TaskStatus> = new Set(['queued', 'running']);
const resolvedStatuses: ReadonlySet<TaskStatus> = new Set(['completed', 'canceled', 'rejected']);

function newestFirst(threads: WorkThreadSummary[]): WorkThreadSummary[] {
  return [...threads].sort((left, right) => Date.parse(right.latest_attempt.updated_at) - Date.parse(left.latest_attempt.updated_at));
}

/**
 * Builds Inbox sections from each work thread's current attempt only. Historical
 * failures must not keep a thread in attention once a newer attempt resolves it.
 */
export function inboxWorkThreadState(workThreads: WorkThreadSummary[]): InboxWorkThreadState {
  const visibleThreads = workThreads.filter((thread) => !thread.latest_attempt.archived_at);

  return {
    attentionRequired: newestFirst(visibleThreads.filter((thread) => attentionRequiredStatuses.has(thread.latest_attempt.status))),
    active: newestFirst(visibleThreads.filter((thread) => activeStatuses.has(thread.latest_attempt.status))),
    recentlyResolved: newestFirst(visibleThreads.filter((thread) => resolvedStatuses.has(thread.latest_attempt.status))),
  };
}
