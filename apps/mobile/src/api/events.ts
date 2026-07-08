import { buildWebSocketUrl } from './url';

export type LiveEvent =
  | {
      type: 'snapshot';
      tasks: unknown[];
      projects: unknown[];
      agents: unknown[];
    }
  | {
      type: 'task.created';
      task: unknown;
    };

export function createEventsSocket(apiUrl: string, apiToken: string): WebSocket {
  return new WebSocket(buildWebSocketUrl(apiUrl, apiToken));
}
