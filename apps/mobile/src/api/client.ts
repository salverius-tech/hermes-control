import { buildApiUrl } from './url';

export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed';

export type TaskSummary = {
  task_id: string;
  title: string;
  prompt: string;
  status: TaskStatus;
  project_id: string;
  source: string;
  priority: 'low' | 'normal' | 'high';
  created_at: string;
  updated_at: string;
  progress_log: string[];
  result_summary?: string | null;
  error?: string | null;
};

export type TaskEvent = {
  task_id: string;
  event_type: string;
  status?: TaskStatus | null;
  message?: string | null;
  created_at: string;
};

export type ProjectSummary = {
  project_id: string;
  name: string;
  queued_count: number;
  running_count: number;
  completed_count: number;
  failed_count: number;
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
  execution_mode: 'unconfigured' | 'command';
  websocket_path: string;
};

export async function apiFetch<T>(
  apiUrl: string,
  apiToken: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(buildApiUrl(apiUrl, path), {
    ...init,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiToken}`,
      ...(init.headers || {}),
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }

  return (await response.json()) as T;
}

export async function testConnection(apiUrl: string): Promise<boolean> {
  const response = await fetch(buildApiUrl(apiUrl, '/health'));
  return response.ok;
}
