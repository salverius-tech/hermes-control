import { describe, expect, it } from 'vitest';

import type { TaskEvent } from '@/api/client';
import { approvalDecisionLabel, latestApprovalAudit } from './approval-audit';

function event(overrides: Partial<TaskEvent>): TaskEvent {
  return {
    created_at: '2026-07-21T12:00:00Z',
    event_type: 'task.created',
    task_id: 'task-1',
    ...overrides,
  };
}

describe('latestApprovalAudit', () => {
  it('presents the latest durable approval metadata without trusting malformed values', () => {
    const audit = latestApprovalAudit([
      event({ event_type: 'approval.audit', metadata: { actor: 'previous operator' }, status: 'rejected' }),
      event({ created_at: '2026-07-21T12:01:00Z', event_type: 'approval.audit', metadata: { actor: '  operator  ', device_id: ' phone-1 ', reason: '  Safe to proceed  ' }, status: 'queued' }),
    ]);

    expect(audit).toEqual({
      actor: 'operator',
      createdAt: '2026-07-21T12:01:00Z',
      deviceId: 'phone-1',
      reason: 'Safe to proceed',
      status: 'queued',
    });
    expect(approvalDecisionLabel(audit?.status)).toBe('Approved');
  });

  it('does not invent an audit record when no approval event exists', () => {
    expect(latestApprovalAudit([event({ metadata: { actor: 'operator' } })])).toBeNull();
    expect(approvalDecisionLabel('rejected')).toBe('Rejected');
  });
});
