"""Thread-safe message queue bridging network listeners to the dispatcher."""

from __future__ import annotations

import queue

from syslog_server.core.message import SyslogMessage


class MessageQueue:
    """Thread-safe wrapper around queue.Queue for syslog messages."""

    def __init__(self, maxsize: int = 100_000):
        self._queue: queue.Queue[SyslogMessage] = queue.Queue(maxsize=maxsize)
        self.total_enqueued = 0
        self.total_dropped = 0

    def put(self, message: SyslogMessage) -> bool:
        """Enqueue a message. Returns False if the queue is full (message dropped)."""
        try:
            self._queue.put_nowait(message)
            self.total_enqueued += 1
            return True
        except queue.Full:
            self.total_dropped += 1
            return False

    def get(self, timeout: float = 0.1) -> SyslogMessage | None:
        """Get a message with timeout. Returns None if timeout expires."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_nowait(self) -> SyslogMessage | None:
        """Get a message without waiting. Returns None if queue is empty."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def drain(self, max_batch: int = 500, timeout: float = 0.1) -> list[SyslogMessage]:
        """Drain up to max_batch messages from the queue.

        Waits up to timeout seconds for the first message, then drains
        without waiting until max_batch is reached or queue is empty.
        """
        batch: list[SyslogMessage] = []

        # Wait for the first message
        first = self.get(timeout=timeout)
        if first is None:
            return batch
        batch.append(first)

        # Drain remaining without waiting
        while len(batch) < max_batch:
            msg = self.get_nowait()
            if msg is None:
                break
            batch.append(msg)

        return batch

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def inner_queue(self) -> queue.Queue:
        """Access the underlying queue for the network listeners."""
        return self._queue
