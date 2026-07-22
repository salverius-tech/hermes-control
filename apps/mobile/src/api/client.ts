import { buildApiUrl } from './url';

export type TaskStatus = 'awaiting_approval' | 'queued' | 'running' | 'attention_required' | 'completed' | 'failed' | 'canceled' | 'rejected' | 'blocked';
export type TaskRelation = 'original' | 'retry' | 'edited_retry' | 'continuation' | 'follow_up';

export type TaskSummary = {
  task_id: string;
  title: string;
  prompt: string;
  status: TaskStatus;
  project_id: string;
  source: string;
  priority: 'low' | 'normal' | 'high';
  requires_approval: boolean;
  created_at: string;
  updated_at: string;
  archived_at?: string | null;
  progress_log: string[];
  result_summary?: string | null;
  error?: string | null;
  blocker_category?: string | null;
  blocker_message?: string | null;
  blocker_retryable?: boolean;
  parent_task_id?: string | null;
  root_task_id?: string | null;
  session_id?: string | null;
  relation?: TaskRelation;
  execution_folder?: string | null;
};

export type TaskEvent = {
  task_id: string;
  event_type: string;
  status?: TaskStatus | null;
  message?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
};

export type WorkThreadSummary = {
  root_task_id: string;
  project_id: string;
  attempts: TaskSummary[];
  latest_attempt: TaskSummary;
  latest_outcome: TaskStatus;
};

export type TaskEnvironment = {
  task_id: string;
  ready: boolean;
  project_ready: boolean;
  session_ready: boolean | null;
  executor_ready: boolean;
  issues: string[];
};

export type ProjectSummary = {
  project_id: string;
  name: string;
  description?: string | null;
  primary_folder?: string | null;
  folders: string[];
  archived: boolean;
  queued_count: number;
  running_count: number;
  completed_count: number;
  failed_count: number;
};

/** Mirrors the Control API's native-project creation contract. */
export type ProjectOrigin = 'adopt' | 'workspace' | 'clone';

export type ProjectCreateRequest = {
  name: string;
  description?: string;
  origin: ProjectOrigin;
  /** Required for adopt; this becomes the native project primary folder. */
  folders?: string[];
  /** Required for clone; the Control API clones it into the managed workspace. */
  repository_url?: string;
};

export type SessionSummary = {
  session_id: string;
  title?: string | null;
  preview?: string | null;
  source?: string | null;
  last_active_at?: string | null;
  cwd?: string | null;
  project_id?: string | null;
  parent_session_id?: string | null;
  archived: boolean;
};

export type AgentStatus = {
  agent_id: string;
  status: 'idle' | 'busy' | 'offline';
  current_task_id?: string | null;
  project_id: string;
  last_seen_at?: string | null;
};

export type Diagnostics = {
  version: string;
  storage: 'memory' | 'sqlite';
  schema_version: string;
  execution_mode: 'unconfigured' | 'command' | 'plugin';
  notification_mode: 'disabled' | 'discord';
  websocket_path: string;
  hermes_home?: string;
  hermes_home_available?: boolean | string;
  native_projects_configured?: boolean | string;
  managed_workspace_ready?: boolean | string;
  bridge_configured?: boolean | string;
  bridge_socket_available?: boolean | string;
  executor_ready?: boolean | string;
  active_task_count?: number | string;
};

export type RecoveryPlanStatus = 'already_registered' | 'ready' | 'missing_repository' | 'conflict' | 'blocked';

export type RecoveryPlanEntry = {
  workspace: string;
  slug?: string;
  status: RecoveryPlanStatus;
  detail?: string;
};

export type RecoveryPlan = {
  entries: RecoveryPlanEntry[];
};

export type RecoveryApplyResult = {
  slug: string;
  status: 'restored' | 'blocked';
};

export type RecoveryApplyResponse = {
  results: RecoveryApplyResult[];
};

export async function apiFetch<T>(apiUrl: string, apiToken: string, path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  let timeout: ReturnType<typeof setTimeout> | undefined;
  let response: Response;
  try {
    const request = fetch(buildApiUrl(apiUrl, path), {
      ...init,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...(apiToken ? { Authorization: `Bearer ${apiToken}` } : {}),
        ...(init.headers || {}),
      },
      signal: controller.signal,
    });
    const deadline = new Promise<never>((_, reject) => {
      timeout = setTimeout(() => {
        controller.abort();
        reject(new Error('API request timed out'));
      }, 10_000);
    });
    response = await Promise.race([request, deadline]);
  } finally {
    if (timeout !== undefined) clearTimeout(timeout);
  }

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }

  return (await response.json()) as T;
}

export async function createProject(
  apiUrl: string,
  apiToken: string,
  request: ProjectCreateRequest,
): Promise<ProjectSummary> {
  return apiFetch<ProjectSummary>(apiUrl, apiToken, '/projects', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function fetchWorkThreads(
  apiUrl: string,
  apiToken: string,
  options: { projectId?: string; includeArchived?: boolean } = {},
): Promise<WorkThreadSummary[]> {
  const query = new URLSearchParams();
  if (options.projectId) query.set('project_id', options.projectId);
  if (options.includeArchived) query.set('include_archived', 'true');
  const suffix = query.size ? `?${query.toString()}` : '';
  return apiFetch<WorkThreadSummary[]>(apiUrl, apiToken, `/work-threads${suffix}`);
}

export async function fetchRecoveryPlan(apiUrl: string, apiToken: string): Promise<RecoveryPlan> {
  return apiFetch<RecoveryPlan>(apiUrl, apiToken, '/recovery-plan');
}

/** Applies only slugs selected from a freshly loaded read-only recovery plan. */
export async function applyRecoveryPlan(apiUrl: string, apiToken: string, slugs: string[]): Promise<RecoveryApplyResponse> {
  return apiFetch<RecoveryApplyResponse>(apiUrl, apiToken, '/recovery-plan/apply', {
    method: 'POST',
    body: JSON.stringify({ slugs, confirm: true }),
  });
}

export async function testConnection(apiUrl: string, apiToken: string): Promise<boolean> {
  await apiFetch<Diagnostics>(apiUrl, apiToken, '/diagnostics');
  return true;
}
