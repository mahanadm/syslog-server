"""Storage manager — coordinates database and file writes."""

from __future__ import annotations

import logging

from syslog_server.core.config import ConfigManager
from syslog_server.core.message import SyslogMessage
from syslog_server.storage.database import DatabaseManager
from syslog_server.storage.file_writer import FileWriter

logger = logging.getLogger(__name__)


class StorageManager:
    """Facade over DatabaseManager and FileWriter for coordinated storage."""

    def __init__(self, config: ConfigManager):
        self._config = config

        self._db = DatabaseManager(config.db_path)
        self._file_writer: FileWriter | None = None

        if config.get("storage", "files", "enabled", default=True):
            self._file_writer = FileWriter(
                log_directory=config.log_directory,
                organize_by=config.get("storage", "files", "organize_by", default="ip"),
                line_format=config.get(
                    "storage", "files", "format",
                    default="{timestamp} [{severity}] {hostname} {app_name}: {message}",
                ),
                rotation=config.get("storage", "files", "rotation", default="size"),
                max_file_size_mb=config.get("storage", "files", "max_file_size_mb", default=10),
                max_files=config.get("storage", "files", "max_files", default=10),
            )

    @property
    def database(self) -> DatabaseManager:
        return self._db

    def open(self) -> None:
        """Open database connection."""
        self._db.open()

    def close(self) -> None:
        """Close database and file handlers."""
        self._db.close()
        if self._file_writer:
            self._file_writer.close()

    def write_batch(self, messages: list[SyslogMessage]) -> None:
        """Write a batch of messages to both database and log files."""
        # Write to database
        try:
            self._db.insert_batch(messages)
        except Exception:
            logger.exception("Database write failed for batch of %d messages", len(messages))

        # Write to log files
        if self._file_writer:
            try:
                self._file_writer.write_batch(messages)
            except Exception:
                logger.exception("File write failed for batch of %d messages", len(messages))

    def cleanup(self) -> None:
        """Run retention cleanup if configured."""
        retention_days = self._config.retention_days
        if retention_days > 0:
            self._db.cleanup_old_messages(retention_days)
