import { describe, expect, it } from 'vitest';

import { buildTaskCreateRequest, priorityOptions } from './request';

describe('buildTaskCreateRequest', () => {
  it('trims prompt and project id before submission', () => {
    expect(
      buildTaskCreateRequest({
        prompt: '  Check Hermes status  ',
        projectId: '  local  ',
        priority: 'high',
        requiresApproval: true,
      }),
    ).toEqual({
      prompt: 'Check Hermes status',
      project_id: 'local',
      priority: 'high',
      requires_approval: true,
    });
  });

  it('falls back to the default project when the project id is blank', () => {
    expect(
      buildTaskCreateRequest({
        prompt: 'Run diagnostics',
        projectId: '   ',
        priority: 'normal',
        requiresApproval: false,
      }),
    ).toMatchObject({ project_id: 'default' });
  });

  it('rejects blank prompts before hitting the API', () => {
    expect(() =>
      buildTaskCreateRequest({
        prompt: '   ',
        projectId: 'default',
        priority: 'low',
        requiresApproval: false,
      }),
    ).toThrow('Prompt is required');
  });
});

describe('priorityOptions', () => {
  it('keeps the supported API priorities in display order', () => {
    expect(priorityOptions.map((option) => option.value)).toEqual(['low', 'normal', 'high']);
  });
});
