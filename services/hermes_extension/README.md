# Hermes Control Extension bridge

This package contains the first transport-level slice of the Hermes Control
Extension. It is intentionally independent of a specific Hermes plugin-host API
so the host adapter can be added once the installed Hermes lifecycle hooks are
selected.

## Protocol

The initial bridge is versioned newline-delimited JSON over a local Unix socket.
The Control API sends one `task.submit` envelope:

```json
{
  "version": 1,
  "type": "task.submit",
  "request_id": "uuid",
  "task": {
    "prompt": "Check Hermes status",
    "project_id": "default",
    "priority": "normal",
    "source": "mobile",
    "requires_approval": false
  }
}
```

The Hermes-side adapter emits `task.event` envelopes using the same
`request_id`. Supported terminal events are `completed` and `failed`; progress
messages use `event: "progress"` and `message`. Heartbeats use `event: "heartbeat"`
and may carry `metadata` describing bridge and child-process liveness.

Long-running tasks are supervised by event liveness rather than a fixed task-duration
timeout. A quiet task remains valid while it receives heartbeats; after the API's
configured output-quiet threshold it is marked `attention_required`, not failed. The
Control API records `last_heartbeat_at`, `last_output_at`, `execution_state`, and
`execution_phase` on the task detail and retains heartbeat metadata in its event timeline. `quiet` means the child
process is alive but has not emitted output; it is not a failure classification.

The Control API selects the bridge with:

```bash
CONTROL_API_HERMES_PLUGIN_SOCKET=/run/hermes/control-extension.sock
```

When the socket is not configured, `CONTROL_API_HERMES_COMMAND` remains the
compatibility fallback.

The initial implementation includes `HermesExtensionServer`, a Unix-socket host
adapter that validates requests, invokes a handler, and emits structured
progress/completion/failure events. The remaining Hermes-specific work is to
implement a handler that maps the installed Hermes lifecycle and tool hooks to
this interface.

The repository root is also a Hermes standalone-plugin entrypoint
(`plugin.yaml` + `__init__.py`). It registers the `hermes_control` read tool.
The local bridge is deliberately owned by the separately supervised
`hermes-control-bridge.service`, not by the plugin process. The current handler
uses `HERMES_CONTROL_EXTENSION_HERMES_COMMAND` as the compatibility execution
path.

Configuration:

```bash
HERMES_CONTROL_EXTENSION_SOCKET=/run/hermes/control-extension.sock
HERMES_CONTROL_EXTENSION_TOKEN='replace-with-local-bridge-token'
# Development-only opt-out; production must use a token.
# HERMES_CONTROL_EXTENSION_ALLOW_UNAUTHENTICATED=1
HERMES_CONTROL_EXTENSION_MAX_CONCURRENT_TASKS=4
HERMES_CONTROL_EXTENSION_MAX_MESSAGE_BYTES=1048576
HERMES_CONTROL_EXTENSION_HEARTBEAT_SECONDS=15
# Optional hard safety cap. Leave unset for activity-aware long-running tasks.
# HERMES_CONTROL_EXTENSION_HARD_TIMEOUT_SECONDS=86400
# Child-process liveness heartbeat interval.
HERMES_CONTROL_EXTENSION_PROCESS_HEARTBEAT_SECONDS=15
HERMES_CONTROL_EXTENSION_HERMES_COMMAND='hermes chat -q'
CONTROL_API_URL='http://127.0.0.1:8787'
CONTROL_API_TOKEN='replace-with-control-api-token'
```
