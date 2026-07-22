import type { Diagnostics } from '@/api/client';

type DiagnosticReadiness = ['Native projects' | 'Managed workspaces' | 'Bridge' | 'Executor', string];

function ready(value: boolean | string | undefined): boolean {
  return value === true || value === 'true';
}

/** Keep native-store, workspace, bridge, and executor state visibly distinct. */
export function diagnosticReadiness(diagnostics: Diagnostics): DiagnosticReadiness[] {
  const bridgeConfigured = ready(diagnostics.bridge_configured);
  const bridgeAvailable = ready(diagnostics.bridge_socket_available);
  return [
    ['Native projects', ready(diagnostics.native_projects_configured) && ready(diagnostics.hermes_home_available) ? 'Ready' : 'Unavailable'],
    ['Managed workspaces', ready(diagnostics.managed_workspace_ready) ? 'Ready' : 'Unavailable'],
    ['Bridge', bridgeConfigured ? bridgeAvailable ? 'Ready' : 'Configured / unavailable' : 'Not configured'],
    ['Executor', ready(diagnostics.executor_ready) ? 'Ready' : 'Not ready'],
  ];
}
