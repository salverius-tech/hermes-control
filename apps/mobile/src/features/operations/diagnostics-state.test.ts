import { describe, expect, it } from 'vitest';

import { Diagnostics } from '@/api/client';

import { diagnosticReadiness } from './diagnostics-state';

const diagnostics: Diagnostics = {
  execution_mode: 'plugin',
  notification_mode: 'disabled',
  schema_version: '3',
  storage: 'sqlite',
  version: '0.1.0',
  websocket_path: '/ws/events',
  bridge_configured: 'true',
  bridge_socket_available: 'false',
  executor_ready: 'false',
  hermes_home_available: 'true',
  managed_workspace_ready: 'true',
  native_projects_configured: 'true',
};

describe('diagnosticReadiness', () => {
  it('keeps readiness dimensions separate instead of treating API reachability as execution readiness', () => {
    expect(diagnosticReadiness(diagnostics)).toEqual([
      ['Native projects', 'Ready'],
      ['Managed workspaces', 'Ready'],
      ['Bridge', 'Configured / unavailable'],
      ['Executor', 'Not ready'],
    ]);
  });
});
