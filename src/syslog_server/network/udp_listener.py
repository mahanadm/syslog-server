"""UDP syslog listener using asyncio DatagramProtocol."""

from __future__ import annotations

import asyncio
import logging
import queue
from datetime import datetime

from syslog_server.parser.auto_detect import decode_bytes, parse

logger = logging.getLogger(__name__)


class SyslogUDPProtocol(asyncio.DatagramProtocol):
    """Receives UDP syslog messages and pushes parsed results to a queue."""

    def __init__(self, message_queue: queue.Queue, protocol_name: str = "udp"):
        self._queue = message_queue
        self._protocol_name = protocol_name
        self._transport: asyncio.DatagramTransport | None = None
        self.messages_received = 0
        self.messages_dropped = 0

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        received_at = datetime.now()
        source_ip, source_port = addr

        try:
            raw = decode_bytes(data)
            msg = parse(raw, source_ip, source_port, self._protocol_name, received_at)
            try:
                self._queue.put_nowait(msg)
                self.messages_received += 1
            except queue.Full:
                self.messages_dropped += 1
        except Exception:
            logger.exception("Error processing UDP message from %s:%d", source_ip, source_port)

    def error_received(self, exc: Exception) -> None:
        logger.error("UDP listener error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            logger.error("UDP connection lost: %s", exc)
