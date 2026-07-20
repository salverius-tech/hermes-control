# Control API Deployment: Proxmox LXC + Caddy

This guide installs the FastAPI Control API into the Proxmox LXC where Hermes is already installed, then exposes it through Caddy. It assumes Debian/Ubuntu inside the LXC and a private hostname or Tailscale network.

## Security model

- Prefer Tailscale, LAN-only DNS, or firewall allowlists. Do **not** expose the Control API directly to the public internet.
- Caddy should terminate HTTPS before traffic reaches the API.
- The API uses a bearer token (`CONTROL_API_TOKEN`) for every endpoint except `/health`; use a long random token and rotate it if a phone is lost or the value is shared accidentally.
- Keep `.env` files and systemd environment files out of git. The committed files under `deploy/` are examples only.
- The mobile app should store only the Control API URL/token. It should never receive Hermes provider keys, SSH keys, Caddy credentials, or Proxmox credentials.

## 1. Prepare the LXC

Run inside the LXC as a sudo-capable user:

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip

# If Hermes is already installed, confirm the service user can run it.
command -v hermes
hermes status || true
```

Create a dedicated service user if one does not already exist:

```bash
sudo useradd --system --create-home --shell /bin/bash hermes || true
```

If Hermes was installed under another account, either install/configure Hermes for the `hermes` user or change the systemd unit's `User=`/`Group=` to the account that already has a working `hermes` command and profile.

## 2. Install the project

Choose a deployment directory and install Python dependencies:

```bash
sudo mkdir -p /opt/hermes-mobile-control
sudo chown hermes:hermes /opt/hermes-mobile-control

sudo -u hermes git clone <repo-url> /opt/hermes-mobile-control
cd /opt/hermes-mobile-control
sudo -u hermes python3 -m venv .venv
sudo -u hermes .venv/bin/python -m pip install --upgrade pip
sudo -u hermes .venv/bin/python -m pip install -r requirements.txt
```

For an update after the first install:

```bash
cd /opt/hermes-mobile-control
sudo -u hermes git pull --ff-only
sudo -u hermes .venv/bin/python -m pip install -r requirements.txt
sudo systemctl restart hermes-mobile-control-api
```

## 3. Configure environment

Create state and config directories:

```bash
sudo mkdir -p /etc/hermes-mobile-control /var/lib/hermes-mobile-control
sudo chown root:hermes /etc/hermes-mobile-control
sudo chown hermes:hermes /var/lib/hermes-mobile-control
sudo chmod 0750 /etc/hermes-mobile-control /var/lib/hermes-mobile-control
```

Generate a token:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Install the environment file from the committed example and edit it:

```bash
sudo install -o root -g hermes -m 0640 \
  /opt/hermes-mobile-control/deploy/control-api.env.example \
  /etc/hermes-mobile-control/control-api.env
sudo editor /etc/hermes-mobile-control/control-api.env
```

Recommended production values:

```text
CONTROL_API_TOKEN=<generated-token>
CONTROL_API_DB_PATH=/var/lib/hermes-mobile-control/control-api.db
CONTROL_API_HERMES_PLUGIN_SOCKET=/run/hermes/control-extension.sock
CONTROL_API_HERMES_PLUGIN_TOKEN=<local-bridge-token>
HERMES_CONTROL_EXTENSION_SOCKET=/run/hermes/control-extension.sock
HERMES_CONTROL_EXTENSION_TOKEN=<same-local-bridge-token>
HERMES_CONTROL_EXTENSION_HERMES_COMMAND="/absolute/path/to/hermes chat --ignore-user-config --ignore-rules -q"
# CONTROL_API_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/[REDACTED]
```

Use `sudo -u hermes command -v hermes` to find the Hermes binary for `CONTROL_API_HERMES_COMMAND`. The API sends task prompts to stdin, so prompts are not interpolated into a shell command.

## 4. Install systemd service

```bash
sudo install -o root -g root -m 0644 \
  /opt/hermes-mobile-control/deploy/hermes-mobile-control-api.service \
  /etc/systemd/system/hermes-mobile-control-api.service

sudo systemctl daemon-reload
sudo systemctl enable --now hermes-mobile-control-api
sudo systemctl status hermes-mobile-control-api --no-pager

# The bridge is a separate, restart-supervised owner of task execution.
sudo install -o root -g root -m 0644 \
  /opt/hermes-mobile-control/deploy/hermes-control-bridge.service \
  /etc/systemd/system/hermes-control-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-control-bridge
sudo systemctl status hermes-control-bridge --no-pager
```

The example unit binds uvicorn to `127.0.0.1:8787` so only Caddy or local processes can reach it directly. It grants explicit state write access to `/var/lib/hermes-mobile-control`; the service user may also use its Hermes profile under its home directory when `CONTROL_API_HERMES_COMMAND` runs.

Service logs:

```bash
journalctl -u hermes-mobile-control-api -f
```

## 5. Configure Caddy reverse proxy

Preferred private subdomain example:

```caddyfile
control-api.example.ts.net {
	encode zstd gzip
	reverse_proxy 127.0.0.1:8787
}
```

Caddy's `reverse_proxy` supports WebSocket upgrades automatically, so `/ws/events?token=...` works through the same site.

If using a path under an existing Hermes hostname, strip the prefix:

```caddyfile
hermes.example.ts.net {
	handle_path /control-api/* {
		reverse_proxy 127.0.0.1:8787
	}
}
```

Then set the mobile API URL to the same prefix, for example `https://hermes.example.ts.net/control-api`.

Install or adapt the committed example:

```bash
sudo cp /opt/hermes-mobile-control/deploy/Caddyfile.control-api.example /etc/caddy/conf.d/control-api.caddy
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Your Caddy layout may use `/etc/caddy/Caddyfile` directly instead of `conf.d/`; merge the site block into the active config if needed.

## 6. Verify deployment

Local LXC checks:

```bash
curl -fsS http://127.0.0.1:8787/health
TOKEN=$(sudo awk -F= '/^CONTROL_API_TOKEN=/{gsub(/"/, "", $2); print $2}' /etc/hermes-mobile-control/control-api.env)
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/diagnostics
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/tasks
```

Through Caddy:

```bash
curl -fsS https://control-api.example.ts.net/health
curl -fsS -H "Authorization: Bearer $TOKEN" https://control-api.example.ts.net/diagnostics
```

Create a real task through Caddy:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Report Hermes status from the Control API deployment"}' \
  https://control-api.example.ts.net/tasks
```

Confirm persistence survives restart:

```bash
sudo systemctl restart hermes-mobile-control-api
curl -fsS -H "Authorization: Bearer $TOKEN" https://control-api.example.ts.net/tasks
```

Optional WebSocket smoke test from a machine with Python `websockets` installed:

```bash
CONTROL_API_WS_URL="wss://control-api.example.ts.net/ws/events?token=$TOKEN" python3 - <<'PY'
import asyncio, os, websockets
url = os.environ['CONTROL_API_WS_URL']
async def main():
    async with websockets.connect(url) as ws:
        print(await ws.recv())
asyncio.run(main())
PY
```

## Token rotation

1. Generate a new token with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`.
2. Replace `CONTROL_API_TOKEN` in `/etc/hermes-mobile-control/control-api.env`.
3. Restart the API: `sudo systemctl restart hermes-mobile-control-api`.
4. Update the token in the mobile app Settings screen.
5. Verify `/diagnostics` returns `401` with the old token and succeeds with the new token.

## Troubleshooting

### `503 CONTROL_API_TOKEN is not configured`

The environment file is missing, unreadable by the service, or lacks `CONTROL_API_TOKEN`. Check:

```bash
sudo systemctl cat hermes-mobile-control-api
sudo systemctl show hermes-mobile-control-api -p EnvironmentFiles
sudo journalctl -u hermes-mobile-control-api -n 100 --no-pager
```

### Mobile app cannot connect

- Use the Caddy HTTPS URL or Tailscale hostname, not `127.0.0.1`.
- Confirm `curl https://<host>/health` works from another device on the same network.
- Confirm Caddy routes WebSockets by testing `/ws/events` with the generated token.

### Tasks complete with an unconfigured-adapter message

Set `CONTROL_API_HERMES_COMMAND` to the Hermes CLI path available to the systemd service user, then restart the service. Validate with:

```bash
sudo -u hermes /absolute/path/to/hermes status
sudo systemctl restart hermes-mobile-control-api
curl -fsS -H "Authorization: Bearer $TOKEN" https://control-api.example.ts.net/diagnostics
```

`diagnostics.execution_mode` should be `command`.
