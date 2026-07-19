#!/usr/bin/env bash
# Provision the runtime directory required by the Hermes Control Extension.
# Run this after installing the plugin, from a sudo-capable shell.
set -euo pipefail

SERVICE_NAME="${HERMES_GATEWAY_SERVICE:-hermes-gateway}"
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.service.d"
DROPIN_PATH="${DROPIN_DIR}/hermes-control-runtime.conf"

service_user="$(systemctl show "${SERVICE_NAME}" --property=User --value 2>/dev/null || true)"
if [[ -z "${service_user}" ]]; then
  echo "Could not determine the User= for ${SERVICE_NAME}" >&2
  exit 1
fi

install -d -m 0755 "${DROPIN_DIR}"
cat >"${DROPIN_PATH}" <<EOF
# Installed by hermes-control: give the gateway service its private bridge runtime directory.
[Service]
RuntimeDirectory=hermes
RuntimeDirectoryMode=0750
EOF

systemctl daemon-reload
systemctl restart "${SERVICE_NAME}"

socket_path="/run/hermes/control-extension.sock"
for _ in {1..50}; do
  if python3 - "${socket_path}" <<'PY'
import asyncio
import sys


async def main() -> None:
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(sys.argv[1]), timeout=1)
    except OSError:
        raise SystemExit(1) from None
    writer.close()
    await writer.wait_closed()


asyncio.run(main())
PY
  then
    printf 'Hermes Control Extension runtime ready: %s (gateway user: %s)\n' "${socket_path}" "${service_user}"
    exit 0
  fi
  sleep 0.1
done

echo "Gateway restarted, but ${socket_path} did not accept connections" >&2
echo "Check: journalctl -u ${SERVICE_NAME} -n 100 --no-pager" >&2
exit 1
