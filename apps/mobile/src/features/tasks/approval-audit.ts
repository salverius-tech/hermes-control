import type { TaskEvent } from '@/api/client';

export type ApprovalAudit = {
  actor: string;
  deviceId?: string;
  reason?: string;
  status?: TaskEvent['status'];
  createdAt: string;
};

function optionalText(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

/** Returns the newest durable approval decision from the task event timeline. */
export function latestApprovalAudit(events: TaskEvent[]): ApprovalAudit | null {
  for (const event of [...events].reverse()) {
    if (event.event_type !== 'approval.audit') continue;
    return {
      actor: optionalText(event.metadata?.actor) ?? 'Unknown operator',
      deviceId: optionalText(event.metadata?.device_id),
      reason: optionalText(event.metadata?.reason),
      status: event.status,
      createdAt: event.created_at,
    };
  }
  return null;
}

export function approvalDecisionLabel(status?: TaskEvent['status']): string {
  return status === 'rejected' ? 'Rejected' : status === 'queued' ? 'Approved' : 'Decision recorded';
}
