import { describe, expect, it } from 'vitest';

import { ProjectCreateRequest } from '@/api/client';

import { failedProjectCreationState, initialProjectCreationState } from './project-creation-state';

const workspaceRequest: ProjectCreateRequest = { name: 'Garden', origin: 'workspace' };

describe('failedProjectCreationState', () => {
  it('retains a managed-project request and offers an explicit registration repair', () => {
    expect(failedProjectCreationState(workspaceRequest, 'API 400: native registration failed')).toEqual({
      actionLabel: 'Repair project registration',
      kind: 'repairable_error',
      message: 'API 400: native registration failed',
      request: workspaceRequest,
    });
  });

  it('does not offer a repair action for adopted-folder failures', () => {
    expect(failedProjectCreationState({ name: 'Existing', origin: 'adopt', folders: ['/approved/existing'] }, 'API 400: rejected')).toEqual({
      kind: 'error',
      message: 'API 400: rejected',
    });
  });

  it('starts with no stale repair action', () => {
    expect(initialProjectCreationState).toEqual({ kind: 'idle' });
  });
});
