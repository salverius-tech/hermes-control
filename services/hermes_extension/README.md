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
messages use `event: "progress"` and `message`.

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
(`plugin.yaml` + `__init__.py`). When installed into Hermes, its `register(ctx)`
function registers the `hermes_control` read tool and starts the local bridge.
The current handler uses `HERMES_CONTROL_EXTENSION_HERMES_COMMAND` as the
compatibility execution path.

Configuration:

```bash
HERMES_CONTROL_EXTENSION_SOCKET=/run/hermes/control-extension.sock
HERMES_CONTROL_EXTENSION_TOKEN='replace-with-local-bridge-token'
HERMES_CONTROL_EXTENSION_HERMES_COMMAND='hermes chat -q'
CONTROL_API_URL='http://127.0.0.1:8787'
CONTROL_API_TOKEN='replace-with-control-api-token'
```
