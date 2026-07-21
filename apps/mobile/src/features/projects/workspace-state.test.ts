import { describe, expect, it } from 'vitest';

import { ProjectSummary } from '@/api/client';

import { workspaceFolderState } from './workspace-state';

const project = (overrides: Partial<ProjectSummary> = {}): ProjectSummary => ({
  archived: false,
  completed_count: 0,
  failed_count: 0,
  folders: ['/workspaces/mobile-control'],
  name: 'Mobile Control',
  primary_folder: '/workspaces/mobile-control',
  project_id: 'mobile-control',
  queued_count: 0,
  running_count: 0,
  ...overrides,
});

describe('workspaceFolderState', () => {
  it('exposes the managed workspace primary folder and registered repo folder', () => {
    expect(workspaceFolderState(project({ folders: ['/workspaces/mobile-control', '/workspaces/mobile-control/repo'] }))).toEqual({
      primaryFolder: '/workspaces/mobile-control',
      repositoryFolder: '/workspaces/mobile-control/repo',
    });
  });

  it('does not mistake an unrelated additional project folder for a managed repository', () => {
    expect(workspaceFolderState(project({ folders: ['/workspaces/mobile-control', '/repos/legacy'] }))).toEqual({
      primaryFolder: '/workspaces/mobile-control',
      repositoryFolder: null,
    });
  });

  it('handles workspace-only and no-primary-folder projects', () => {
    expect(workspaceFolderState(project())).toEqual({
      primaryFolder: '/workspaces/mobile-control',
      repositoryFolder: null,
    });
    expect(workspaceFolderState(project({ primary_folder: null }))).toEqual({ primaryFolder: null, repositoryFolder: null });
  });
});
