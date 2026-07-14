import { buildApiUrl } from './url';

export type TaskStatus = 'awaiting_approval' | 'queued' | 'running' | 'completed' | 'failed' | 'canceled' | 'rejected' | 'blocked';
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
  description?: string | null;
  primary_folder?: string | null;
  folders: string[];
  archived: boolean;
  queued_count: number;
  running_count: number;
  completed_count: number;
  failed_count: number;
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
  hermes_home_available?: string;
};

export async function apiFetch<T>(apiUrl: string, apiToken: string, path: string, init: RequestInit = {}): Promise<T> {
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
