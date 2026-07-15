import { TaskSummary, ProjectSummary, AgentStatus } from './client';
import { buildWebSocketUrl } from './url';

export type LiveEvent =
  | { type: 'snapshot'; tasks: TaskSummary[]; projects: ProjectSummary[]; agents: AgentStatus[] }
  | { type: 'task.created'; task: TaskSummary }
  | { type: 'task.updated'; task: TaskSummary };

export function createEventsSocket(apiUrl: string, apiToken: string): WebSocket {
  return new WebSocket(buildWebSocketUrl(apiUrl, apiToken));
}

export function redactWebSocketUrl(url: string): string {
  return url.replace(/([?&]token=)[^&]*/i, '$1[REDACTED]');
}

export function parseLiveEvent(data: string): LiveEvent | null {
  try {
    const event = JSON.parse(data) as LiveEvent;
    if (event.type === 'snapshot' || event.type === 'task.created' || event.type === 'task.updated') return event;
    return null;
  } catch {
    return null;
  }
}
