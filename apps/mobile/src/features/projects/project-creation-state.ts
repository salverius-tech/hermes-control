import type { ProjectCreateRequest } from '@/api/client';

export type ProjectCreationState =
  | { kind: 'idle' | 'submitting' }
  | { kind: 'error'; message: string }
  | { actionLabel: 'Repair project registration'; kind: 'repairable_error'; message: string; request: ProjectCreateRequest };

export const initialProjectCreationState: ProjectCreationState = { kind: 'idle' };

/**
 * The Control API preserves a managed workspace after a native registration
 * failure and accepts the same create request to repair that registration.
 * Adopted folders have no managed workspace to repair.
 */
export function failedProjectCreationState(request: ProjectCreateRequest, message: string): ProjectCreationState {
  if (request.origin === 'adopt') return { kind: 'error', message };
  return { actionLabel: 'Repair project registration', kind: 'repairable_error', message, request };
}
