import { ProjectSummary } from '@/api/client';

export type WorkspaceFolderState = {
  primaryFolder: string | null;
  repositoryFolder: string | null;
};

function trimTrailingSeparators(path: string): string {
  if (path === '/') return path;
  return path.replace(/\/+$/, '');
}

/**
 * The current project API exposes native folder membership only. Managed
 * workspaces reserve `<primary folder>/repo` for an optional repository, so
 * recognize that registered folder without inferring repository state from
 * unrelated legacy project folders.
 */
export function workspaceFolderState(project: ProjectSummary): WorkspaceFolderState {
  const primaryFolder = project.primary_folder ? trimTrailingSeparators(project.primary_folder) : null;
  if (!primaryFolder) return { primaryFolder: null, repositoryFolder: null };

  const expectedRepositoryFolder = `${primaryFolder}/repo`;
  const repositoryFolder = project.folders.find(
    (folder) => trimTrailingSeparators(folder) === expectedRepositoryFolder,
  ) || null;

  return { primaryFolder, repositoryFolder };
}
