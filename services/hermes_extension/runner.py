"""Systemd entrypoint for the Hermes Control bridge.

The bridge intentionally runs outside the gateway plugin process. The gateway may
reload plugins or restart without taking ownership of a mobile task's IPC server.
"""
from __future__ import annotations

import asyncio
import os
import signal

from .host import handler_from_environment
from .server import HermesExtensionServer


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _nonnegative_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def _token() -> str | None:
    value = os.getenv("HERMES_CONTROL_EXTENSION_TOKEN")
    if value:
        return value
    if os.getenv("HERMES_CONTROL_EXTENSION_ALLOW_UNAUTHENTICATED") == "1":
        return None
    raise RuntimeError("HERMES_CONTROL_EXTENSION_TOKEN is required; set HERMES_CONTROL_EXTENSION_ALLOW_UNAUTHENTICATED=1 only for development")


async def serve() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    server = HermesExtensionServer(
        os.getenv("HERMES_CONTROL_EXTENSION_SOCKET", "/run/hermes/control-extension.sock"),
        handler_from_environment(),
        auth_token=_token(),
        max_message_bytes=_positive_int("HERMES_CONTROL_EXTENSION_MAX_MESSAGE_BYTES", 1_048_576),
        max_concurrent_tasks=_positive_int("HERMES_CONTROL_EXTENSION_MAX_CONCURRENT_TASKS", 4),
        heartbeat_seconds=_nonnegative_float("HERMES_CONTROL_EXTENSION_HEARTBEAT_SECONDS", 15),
    )
    await server.start()
    try:
        await stop.wait()
    finally:
        await server.close()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
