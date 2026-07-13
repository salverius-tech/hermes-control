"""Hermes Control Extension bridge primitives.

The extension is intentionally transport-agnostic at this layer. Hermes-side
plugin code can use the versioned JSONL envelope to communicate with the
Control API over a local Unix socket.
"""

from .host import SubprocessHermesTaskHandler, handler_from_environment
from .protocol import BRIDGE_VERSION, PluginEvent, PluginRequest, decode_message, encode_message
from .server import HermesExtensionServer, HermesTaskHandler

__all__ = [
    "BRIDGE_VERSION",
    "HermesExtensionServer",
    "HermesTaskHandler",
    "PluginEvent",
    "PluginRequest",
    "SubprocessHermesTaskHandler",
    "decode_message",
    "encode_message",
    "handler_from_environment",
]
