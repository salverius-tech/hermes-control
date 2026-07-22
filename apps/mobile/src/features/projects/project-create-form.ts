import { ProjectCreateRequest, ProjectOrigin } from '@/api/client';

export type ProjectCreateForm = {
  name: string;
  description: string;
  folder: string;
  origin: ProjectOrigin;
  repositoryUrl: string;
};

export type ProjectCreateFormErrors = Partial<Record<'name' | 'folder' | 'repositoryUrl', string>>;

export type ProjectCreateFormValidation = {
  errors: ProjectCreateFormErrors;
  request?: ProjectCreateRequest;
};

export const initialProjectCreateForm: ProjectCreateForm = {
  name: '',
  description: '',
  folder: '',
  origin: 'workspace',
  repositoryUrl: '',
};

/** Matches the Control API's credential-free HTTPS/SSH remote requirement. */
export function isRepositoryUrl(value: string): boolean {
  const remote = value.trim();
  if (!remote || remote.startsWith('-')) return false;
  if (remote.startsWith('http://')) {
    try {
      const url = new URL(remote);
      return url.hostname === '127.0.0.1' && Boolean(url.port) && Boolean(url.pathname.replaceAll('/', '')) && !url.username && !url.password;
    } catch {
      return false;
    }
  }
  if (!/^(https:\/\/|ssh:\/\/|git@)[^\s]+$/.test(remote)) return false;
  const host = remote.startsWith('git@') ? '' : remote.replace(/^[a-z]+:\/\//, '').split('/', 1)[0];
  return remote.startsWith('git@') || !host.includes('@');
}

export function validateProjectCreateForm(form: ProjectCreateForm): ProjectCreateFormValidation {
  const name = form.name.trim();
  const description = form.description.trim();
  const folder = form.folder.trim();
  const repositoryUrl = form.repositoryUrl.trim();
  const errors: ProjectCreateFormErrors = {};

  if (!name) errors.name = 'Project name is required.';
  if (form.origin === 'adopt' && !folder) errors.folder = 'Choose or enter the existing project folder to adopt.';
  if (form.origin === 'clone' && !repositoryUrl) errors.repositoryUrl = 'Repository URL is required.';
  else if (form.origin === 'clone' && !isRepositoryUrl(repositoryUrl)) errors.repositoryUrl = 'Use a credential-free HTTPS or SSH repository URL.';

  if (Object.keys(errors).length) return { errors };

  const request: ProjectCreateRequest = {
    name,
    origin: form.origin,
    ...(description ? { description } : {}),
    ...(form.origin === 'adopt' ? { folders: [folder] } : {}),
    ...(form.origin === 'clone' ? { repository_url: repositoryUrl } : {}),
  };
  return { errors, request };
}
