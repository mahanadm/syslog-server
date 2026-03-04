"""Message dispatcher — reads from queue, batches, fans out to storage and WebSocket clients."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import TYPE_CHECKING

from syslog_server.core.message import SyslogMessage
from syslog_server.core.message_queue import MessageQueue

if TYPE_CHECKING:
    from syslog_server.alerts.alert_engine import AlertEngine
    from syslog_server.alerts.notifier import Notifier
    from syslog_server.storage.storage_manager import StorageManager
    from syslog_server.web.broadcaster import WebSocketBroadcaster

logger = logging.getLogger(__name__)


class MessageDispatcher(threading.Thread):
    """Reads syslog messages from the queue, batches them, and dispatches to consumers.

    Runs in a dedicated background thread. Pushes new messages to WebSocket clients
    via the broadcaster using asyncio.run_coroutine_threadsafe().
    """

    def __init__(
        self,
        message_queue: MessageQueue,
        storage: StorageManager,
        alert_engine: AlertEngine | None = None,
        notifier: Notifier | None = None,
        batch_size: int = 500,
        batch_timeout_ms: int = 100,
    ):
        super().__init__(name="MessageDispatcher", daemon=True)
        self._queue = message_queue
        self._storage = storage
        self._alert_engine = alert_engine
        self._notifier = notifier
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout_ms / 1000.0
        self._running = False
        self._total_processed = 0
        self._last_stats_time = 0.0
        self._last_stats_count = 0
        self._msgs_per_sec = 0.0

        # Set by app.py after the asyncio loop is available
        self._broadcaster: WebSocketBroadcaster | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_broadcaster(
        self, broadcaster: WebSocketBroadcaster, loop: asyncio.AbstractEventLoop
    ) -> None:
        """Attach the WebSocket broadcaster and the asyncio event loop."""
        self._broadcaster = broadcaster
        self._loop = loop

    @property
    def total_processed(self) -> int:
        return self._total_processed

    @property
    def msgs_per_sec(self) -> float:
        return self._msgs_per_sec

    def run(self) -> None:
        """Main dispatcher loop (runs in background thread)."""
        self._running = True
        self._last_stats_time = time.monotonic()
        logger.info("Message dispatcher started")

        while self._running:
            batch = self._queue.drain(
                max_batch=self._batch_size,
                timeout=self._batch_timeout,
            )

            if batch:
                # Write to storage (DB + files)
                try:
                    self._storage.write_batch(batch)
                except Exception:
                    logger.exception("Storage write failed for batch of %d messages", len(batch))

                # Push to WebSocket clients
                if self._broadcaster and self._loop and self._loop.is_running():
                    json_batch = _messages_to_json(batch)
                    asyncio.run_coroutine_threadsafe(
                        self._broadcaster.broadcast(json_batch), self._loop
                    )

                # Evaluate alerts
                if self._alert_engine and self._notifier:
                    for msg in batch:
                        triggered = self._alert_engine.evaluate(msg)
                        for rule in triggered:
                            self._notifier.on_alert_triggered(msg, rule)

                self._total_processed += len(batch)

            # Update message rate stat ~every second
            now = time.monotonic()
            elapsed = now - self._last_stats_time
            if elapsed >= 1.0:
                self._msgs_per_sec = (
                    self._total_processed - self._last_stats_count
                ) / elapsed
                self._last_stats_time = now
                self._last_stats_count = self._total_processed

        logger.info("Message dispatcher stopped (processed %d messages)", self._total_processed)

    def stop(self) -> None:
        """Signal the dispatcher to stop."""
        self._running = False


def _messages_to_json(batch: list[SyslogMessage]) -> str:
    """Serialize a batch of messages to a JSON array string."""
    import json

    items = []
    for msg in batch:
        items.append({
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            "received_at": msg.received_at.isoformat(),
            "source_ip": msg.source_ip,
            "severity": msg.severity.value if msg.severity is not None else None,
            "severity_name": msg.severity.name if msg.severity is not None else "UNKNOWN",
            "facility": msg.facility.value if msg.facility is not None else None,
            "hostname": msg.hostname,
            "app_name": msg.app_name,
            "message": msg.message,
            "protocol": msg.protocol,
            "rfc_format": msg.rfc_format,
            "cisco_mnemonic": msg.cisco_mnemonic,
        })
    return json.dumps({"type": "messages", "data": items})
