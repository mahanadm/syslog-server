"""Thread-safe WebSocket connection manager for broadcasting live log messages."""

from __future__ import annotations

import asyncio
import logging
import threading

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketBroadcaster:
    """Manages all active WebSocket connections and broadcasts messages to them.

    Thread-safe: broadcast_from_thread() can be called from non-asyncio threads.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = threading.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        with self._lock:
            self._connections.add(ws)
        logger.debug("WebSocket client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        with self._lock:
            self._connections.discard(ws)
        logger.debug("WebSocket client disconnected (%d total)", len(self._connections))

    async def broadcast(self, data: str) -> None:
        """Send a message to all connected clients. Called from asyncio context."""
        with self._lock:
            connections = set(self._connections)

        dead: set[WebSocket] = set()
        for ws in connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)

        if dead:
            with self._lock:
                self._connections -= dead

    def broadcast_from_thread(
        self, loop: asyncio.AbstractEventLoop, data: str
    ) -> None:
        """Schedule a broadcast from a non-asyncio thread (e.g. dispatcher thread)."""
        asyncio.run_coroutine_threadsafe(self.broadcast(data), loop)

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._connections)
