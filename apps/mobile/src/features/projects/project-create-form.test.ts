import { describe, expect, it } from 'vitest';

import { ProjectCreateForm, isRepositoryUrl, validateProjectCreateForm } from './project-create-form';

const form = (overrides: Partial<ProjectCreateForm> = {}): ProjectCreateForm => ({
  description: '  A focused project.  ',
  folder: ' /approved/existing-project ',
  name: '  Garden Planner  ',
  origin: 'workspace',
  repositoryUrl: ' https://example.test/team/garden.git ',
  ...overrides,
});

describe('validateProjectCreateForm', () => {
  it('builds the workspace request without a client-selected folder', () => {
    expect(validateProjectCreateForm(form())).toEqual({
      errors: {},
      request: { description: 'A focused project.', name: 'Garden Planner', origin: 'workspace' },
    });
  });

  it('requires an existing folder only when adopting a project', () => {
    expect(validateProjectCreateForm(form({ origin: 'adopt', folder: '  ' }))).toEqual({
      errors: { folder: 'Choose or enter the existing project folder to adopt.' },
    });
    expect(validateProjectCreateForm(form({ origin: 'adopt' }).request).toEqual({
      description: 'A focused project.',
      folders: ['/approved/existing-project'],
      name: 'Garden Planner',
      origin: 'adopt',
    });
  });

  it('requires and normalizes a credential-free remote only when cloning', () => {
    expect(validateProjectCreateForm(form({ origin: 'clone', repositoryUrl: '' }))).toEqual({
      errors: { repositoryUrl: 'Repository URL is required.' },
    });
    expect(validateProjectCreateForm(form({ origin: 'clone' }).request).toEqual({
      description: 'A focused project.',
      name: 'Garden Planner',
      origin: 'clone',
      repository_url: 'https://example.test/team/garden.git',
    });
  });

  it('rejects unsupported or credential-bearing repository URLs before submission', () => {
    expect(isRepositoryUrl('file:///tmp/project.git')).toBe(false);
    expect(isRepositoryUrl('https://token@example.test/team/project.git')).toBe(false);
    expect(isRepositoryUrl('ssh://user@example.test/team/project.git')).toBe(false);
    expect(isRepositoryUrl('git@example.test:team/project.git')).toBe(true);
  });

  it('requires a nonblank project name for every mode', () => {
    expect(validateProjectCreateForm(form({ name: '  ', origin: 'workspace' }))).toEqual({
      errors: { name: 'Project name is required.' },
    });
  });
});
