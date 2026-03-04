"""Per-device log file writer with rotation."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path

from syslog_server.core.constants import FACILITY_NAMES, SEVERITY_NAMES, Facility, Severity
from syslog_server.core.message import SyslogMessage

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Remove characters that are not safe for filenames."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


class FileWriter:
    """Writes syslog messages to per-device log files with rotation."""

    def __init__(
        self,
        log_directory: Path,
        organize_by: str = "ip",
        line_format: str = "{timestamp} [{severity}] {hostname} {app_name}: {message}",
        rotation: str = "size",
        max_file_size_mb: int = 10,
        max_files: int = 10,
        timestamp_format: str = "%Y-%m-%d %H:%M:%S",
    ):
        self._log_dir = log_directory
        self._organize_by = organize_by
        self._line_format = line_format
        self._rotation = rotation
        self._max_bytes = max_file_size_mb * 1024 * 1024
        self._max_files = max_files
        self._timestamp_format = timestamp_format
        self._handlers: dict[str, logging.Logger] = {}

    def _get_device_key(self, msg: SyslogMessage) -> str:
        """Determine the file key for a message based on organize_by setting."""
        if self._organize_by == "hostname" and msg.hostname:
            return _sanitize_filename(msg.hostname)
        return _sanitize_filename(msg.source_ip)

    def _get_logger(self, device_key: str) -> logging.Logger:
        """Get or create a rotating file logger for a device."""
        if device_key in self._handlers:
            return self._handlers[device_key]

        device_dir = self._log_dir / device_key
        device_dir.mkdir(parents=True, exist_ok=True)
        log_path = device_dir / "syslog.log"

        file_logger = logging.getLogger(f"syslog_file.{device_key}")
        file_logger.setLevel(logging.DEBUG)
        file_logger.propagate = False

        # Remove existing handlers
        for h in file_logger.handlers[:]:
            file_logger.removeHandler(h)

        if self._rotation == "daily":
            handler = TimedRotatingFileHandler(
                str(log_path),
                when="midnight",
                backupCount=self._max_files,
                encoding="utf-8",
            )
        else:
            handler = RotatingFileHandler(
                str(log_path),
                maxBytes=self._max_bytes,
                backupCount=self._max_files,
                encoding="utf-8",
            )

        handler.setFormatter(logging.Formatter("%(message)s"))
        file_logger.addHandler(handler)
        self._handlers[device_key] = file_logger
        return file_logger

    def _format_message(self, msg: SyslogMessage) -> str:
        """Format a syslog message into a log line."""
        return self._line_format.format(
            timestamp=msg.timestamp.strftime(self._timestamp_format),
            received_at=msg.received_at.strftime(self._timestamp_format),
            severity=SEVERITY_NAMES.get(msg.severity, "UNKNOWN"),
            facility=FACILITY_NAMES.get(msg.facility, "UNKNOWN"),
            hostname=msg.hostname or msg.source_ip,
            source_ip=msg.source_ip,
            app_name=msg.app_name or "-",
            process_id=msg.process_id or "-",
            message=msg.message,
            protocol=msg.protocol,
            raw=msg.raw,
        )

    def write_batch(self, messages: list[SyslogMessage]) -> None:
        """Write a batch of messages to their respective device log files."""
        for msg in messages:
            try:
                device_key = self._get_device_key(msg)
                file_logger = self._get_logger(device_key)
                line = self._format_message(msg)
                file_logger.info(line)
            except Exception:
                logger.exception(
                    "Failed to write log for %s:%d", msg.source_ip, msg.source_port
                )

    def close(self) -> None:
        """Close all file handlers."""
        for name, file_logger in self._handlers.items():
            for handler in file_logger.handlers[:]:
                handler.close()
                file_logger.removeHandler(handler)
        self._handlers.clear()
