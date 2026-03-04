"""TCP syslog listener using asyncio StreamServer.

Supports two framing modes:
- Newline-delimited (most common for OT devices)
- Octet-counting per RFC 5425 (length-prefixed)
"""

from __future__ import annotations

import asyncio
import logging
import queue
from datetime import datetime

from syslog_server.parser.auto_detect import decode_bytes, parse

logger = logging.getLogger(__name__)


class TCPListenerHandler:
    """Handles individual TCP client connections."""

    def __init__(
        self,
        message_queue: queue.Queue,
        framing: str = "newline",
        protocol_name: str = "tcp",
    ):
        self._queue = message_queue
        self._framing = framing
        self._protocol_name = protocol_name
        self.messages_received = 0
        self.messages_dropped = 0

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single TCP client connection."""
        peer = writer.get_extra_info("peername")
        source_ip = peer[0] if peer else "unknown"
        source_port = peer[1] if peer else 0
        logger.info("TCP client connected: %s:%d", source_ip, source_port)

        try:
            if self._framing == "octet-counting":
                await self._read_octet_counting(reader, source_ip, source_port)
            else:
                await self._read_newline(reader, source_ip, source_port)
        except asyncio.CancelledError:
            pass
        except ConnectionResetError:
            logger.debug("TCP client disconnected: %s:%d", source_ip, source_port)
        except Exception:
            logger.exception("Error handling TCP client %s:%d", source_ip, source_port)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("TCP client disconnected: %s:%d", source_ip, source_port)

    async def _read_newline(
        self, reader: asyncio.StreamReader, source_ip: str, source_port: int
    ) -> None:
        """Read newline-delimited syslog messages."""
        while True:
            data = await reader.readline()
            if not data:
                break
            self._process_message(data, source_ip, source_port)

    async def _read_octet_counting(
        self, reader: asyncio.StreamReader, source_ip: str, source_port: int
    ) -> None:
        """Read octet-counting framed syslog messages (RFC 5425)."""
        while True:
            # Read the length prefix (digits followed by space)
            length_bytes = b""
            while True:
                byte = await reader.readexactly(1)
                if byte == b" ":
                    break
                if not byte.isdigit():
                    raise ValueError(f"Invalid octet-counting frame: expected digit, got {byte!r}")
                length_bytes += byte
                if len(length_bytes) > 10:
                    raise ValueError("Octet-counting length too long")

            msg_length = int(length_bytes)
            if msg_length <= 0 or msg_length > 65536:
                raise ValueError(f"Invalid message length: {msg_length}")

            data = await reader.readexactly(msg_length)
            self._process_message(data, source_ip, source_port)

    def _process_message(
        self, data: bytes, source_ip: str, source_port: int
    ) -> None:
        """Parse and enqueue a message."""
        received_at = datetime.now()
        try:
            raw = decode_bytes(data)
            msg = parse(raw, source_ip, source_port, self._protocol_name, received_at)
            try:
                self._queue.put_nowait(msg)
                self.messages_received += 1
            except queue.Full:
                self.messages_dropped += 1
        except Exception:
            logger.exception("Error processing TCP message from %s:%d", source_ip, source_port)
