"""WebSocket module for real-time collaboration."""

from .manager import (
    ConnectionManager,
    WebSocketConnection,
    manager,
)

__all__ = [
    "ConnectionManager",
    "WebSocketConnection",
    "manager",
]
