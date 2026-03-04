"""Manages all syslog network listeners in a dedicated asyncio thread."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass, field
from typing import Any

from syslog_server.core.config import ConfigManager
from syslog_server.network.tcp_listener import TCPListenerHandler
from syslog_server.network.tls_listener import create_tls_context
from syslog_server.network.udp_listener import SyslogUDPProtocol

logger = logging.getLogger(__name__)


@dataclass
class ListenerStatus:
    """Status information for a listener."""
    protocol: str
    host: str
    port: int
    active: bool = False
    error: str = ""
    messages_received: int = 0
    messages_dropped: int = 0


class ListenerManager:
    """Creates and manages syslog listeners in a dedicated asyncio event loop thread."""

    def __init__(self, message_queue: queue.Queue, config: ConfigManager):
        self._queue = message_queue
        self._config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._transports: dict[str, Any] = {}
        self._servers: dict[str, asyncio.AbstractServer] = {}
        self._handlers: dict[str, Any] = {}
        self._statuses: dict[str, ListenerStatus] = {}
        self._started = threading.Event()

    def start(self) -> None:
        """Start the asyncio event loop thread."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="syslog-net"
        )
        self._thread.start()
        self._started.wait(timeout=5)

    def _run_loop(self) -> None:
        """Run the asyncio event loop (called in the network thread)."""
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

    def stop(self) -> None:
        """Stop all listeners and shut down the event loop."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)

    def start_listeners_from_config(self) -> None:
        """Start all enabled listeners based on current config."""
        if self._config.get("listeners", "udp", "enabled", default=True):
            host = self._config.get("listeners", "udp", "host", default="0.0.0.0")
            port = self._config.get("listeners", "udp", "port", default=514)
            self.start_udp(host, port)

        if self._config.get("listeners", "tcp", "enabled", default=False):
            host = self._config.get("listeners", "tcp", "host", default="0.0.0.0")
            port = self._config.get("listeners", "tcp", "port", default=514)
            framing = self._config.get("listeners", "tcp", "framing", default="newline")
            self.start_tcp(host, port, framing)

        if self._config.get("listeners", "tls", "enabled", default=False):
            host = self._config.get("listeners", "tls", "host", default="0.0.0.0")
            port = self._config.get("listeners", "tls", "port", default=6514)
            cert = self._config.get("listeners", "tls", "cert_file", default="")
            key = self._config.get("listeners", "tls", "key_file", default="")
            ca = self._config.get("listeners", "tls", "ca_file", default="")
            client_cert = self._config.get("listeners", "tls", "require_client_cert", default=False)
            framing = self._config.get("listeners", "tcp", "framing", default="newline")
            self.start_tls(host, port, cert, key, ca, client_cert, framing)

    def start_udp(self, host: str, port: int) -> None:
        """Start the UDP listener."""
        status = ListenerStatus(protocol="udp", host=host, port=port)
        self._statuses["udp"] = status
        future = asyncio.run_coroutine_threadsafe(
            self._start_udp(host, port), self._loop
        )
        try:
            future.result(timeout=5)
            status.active = True
            logger.info("UDP listener started on %s:%d", host, port)
        except Exception as e:
            status.error = str(e)
            logger.error("Failed to start UDP listener on %s:%d: %s", host, port, e)

    async def _start_udp(self, host: str, port: int) -> None:
        protocol = SyslogUDPProtocol(self._queue)
        transport, _ = await self._loop.create_datagram_endpoint(
            lambda: protocol,
            local_addr=(host, port),
        )
        self._transports["udp"] = transport
        self._handlers["udp"] = protocol

    def start_tcp(self, host: str, port: int, framing: str = "newline") -> None:
        """Start the TCP listener."""
        status = ListenerStatus(protocol="tcp", host=host, port=port)
        self._statuses["tcp"] = status
        future = asyncio.run_coroutine_threadsafe(
            self._start_tcp(host, port, framing), self._loop
        )
        try:
            future.result(timeout=5)
            status.active = True
            logger.info("TCP listener started on %s:%d", host, port)
        except Exception as e:
            status.error = str(e)
            logger.error("Failed to start TCP listener on %s:%d: %s", host, port, e)

    async def _start_tcp(self, host: str, port: int, framing: str) -> None:
        handler = TCPListenerHandler(self._queue, framing=framing, protocol_name="tcp")
        server = await asyncio.start_server(
            handler.handle_client, host, port
        )
        self._servers["tcp"] = server
        self._handlers["tcp"] = handler

    def start_tls(
        self,
        host: str,
        port: int,
        cert_file: str,
        key_file: str,
        ca_file: str = "",
        require_client_cert: bool = False,
        framing: str = "newline",
    ) -> None:
        """Start the TLS listener."""
        status = ListenerStatus(protocol="tls", host=host, port=port)
        self._statuses["tls"] = status

        ssl_ctx = create_tls_context(cert_file, key_file, ca_file, require_client_cert)
        if ssl_ctx is None:
            status.error = "Failed to create TLS context — check certificate files"
            logger.error("TLS listener not started: invalid TLS configuration")
            return

        future = asyncio.run_coroutine_threadsafe(
            self._start_tls(host, port, ssl_ctx, framing), self._loop
        )
        try:
            future.result(timeout=5)
            status.active = True
            logger.info("TLS listener started on %s:%d", host, port)
        except Exception as e:
            status.error = str(e)
            logger.error("Failed to start TLS listener on %s:%d: %s", host, port, e)

    async def _start_tls(self, host: str, port: int, ssl_ctx, framing: str) -> None:
        handler = TCPListenerHandler(self._queue, framing=framing, protocol_name="tls")
        server = await asyncio.start_server(
            handler.handle_client, host, port, ssl=ssl_ctx
        )
        self._servers["tls"] = server
        self._handlers["tls"] = handler

    def stop_listener(self, protocol: str) -> None:
        """Stop a specific listener."""
        if self._loop is None:
            return

        if protocol in self._transports:
            transport = self._transports.pop(protocol)
            self._loop.call_soon_threadsafe(transport.close)
        if protocol in self._servers:
            server = self._servers.pop(protocol)
            self._loop.call_soon_threadsafe(server.close)
        if protocol in self._handlers:
            del self._handlers[protocol]
        if protocol in self._statuses:
            self._statuses[protocol].active = False

        logger.info("%s listener stopped", protocol.upper())

    def get_statuses(self) -> dict[str, ListenerStatus]:
        """Get status of all listeners, including message counts."""
        for proto, handler in self._handlers.items():
            if proto in self._statuses:
                self._statuses[proto].messages_received = handler.messages_received
                self._statuses[proto].messages_dropped = handler.messages_dropped
        return dict(self._statuses)
