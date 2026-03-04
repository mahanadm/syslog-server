"""SQLite database manager — schema, batch inserts, queries, FTS5 search."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from syslog_server.core.constants import Facility, Severity
from syslog_server.core.message import SyslogMessage

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address      TEXT NOT NULL UNIQUE,
    hostname        TEXT,
    display_name    TEXT,
    color           TEXT DEFAULT '#4A9EFF',
    notes           TEXT,
    vendor          TEXT DEFAULT 'unknown',
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    message_count   INTEGER DEFAULT 0,
    file_logging    INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip_address);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    received_at     TEXT NOT NULL,
    source_ip       TEXT NOT NULL,
    source_port     INTEGER NOT NULL,
    facility        INTEGER NOT NULL,
    severity        INTEGER NOT NULL,
    hostname        TEXT,
    app_name        TEXT,
    process_id      TEXT,
    message_id      TEXT,
    message         TEXT NOT NULL,
    raw             TEXT NOT NULL,
    protocol        TEXT NOT NULL DEFAULT 'udp',
    rfc_format      TEXT NOT NULL DEFAULT 'rfc3164',
    structured_data TEXT,
    cisco_sequence  INTEGER,
    cisco_mnemonic  TEXT,
    device_id       INTEGER REFERENCES devices(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_received_at ON messages(received_at);
CREATE INDEX IF NOT EXISTS idx_messages_source_ip ON messages(source_ip);
CREATE INDEX IF NOT EXISTS idx_messages_severity ON messages(severity);
CREATE INDEX IF NOT EXISTS idx_messages_device_id ON messages(device_id);
CREATE INDEX IF NOT EXISTS idx_messages_source_severity_time
    ON messages(source_ip, severity, timestamp);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    message,
    content='messages',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, message) VALUES (new.id, new.message);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, message) VALUES('delete', old.id, old.message);
END;

CREATE TABLE IF NOT EXISTS alert_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    enabled         INTEGER DEFAULT 1,
    min_severity    INTEGER DEFAULT 0,
    max_severity    INTEGER DEFAULT 3,
    keyword_pattern TEXT,
    device_filter   TEXT,
    cooldown_secs   INTEGER DEFAULT 60,
    sound_enabled   INTEGER DEFAULT 0,
    notification    INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""


class DatabaseManager:
    """Manages the SQLite database for syslog message storage and querying."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._device_cache: dict[str, int] = {}  # ip -> device_id

    def open(self) -> None:
        """Open the database connection and initialize schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        self._load_device_cache()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript(_CREATE_TABLES)

        # Check schema version
        cursor = self._conn.execute("SELECT MAX(version) FROM schema_version")
        row = cursor.fetchone()
        current_version = row[0] if row[0] is not None else 0

        if current_version < SCHEMA_VERSION:
            now = datetime.now().isoformat()
            self._conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, now),
            )
            self._conn.commit()

    def _load_device_cache(self) -> None:
        """Load device IP -> ID mapping into memory."""
        cursor = self._conn.execute("SELECT id, ip_address FROM devices")
        self._device_cache = {row["ip_address"]: row["id"] for row in cursor}

    def _get_or_create_device(self, source_ip: str, hostname: str | None = None) -> int:
        """Get device ID for an IP, creating the device if it doesn't exist."""
        if source_ip in self._device_cache:
            return self._device_cache[source_ip]

        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            """INSERT INTO devices (ip_address, hostname, display_name, first_seen, last_seen, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source_ip, hostname, hostname or source_ip, now, now, now, now),
        )
        device_id = cursor.lastrowid
        self._device_cache[source_ip] = device_id
        return device_id

    def insert_batch(self, messages: list[SyslogMessage]) -> None:
        """Insert a batch of syslog messages efficiently."""
        if not messages or not self._conn:
            return

        rows = []
        device_updates: dict[int, tuple[str, int]] = {}  # device_id -> (last_seen, count)

        for msg in messages:
            device_id = self._get_or_create_device(msg.source_ip, msg.hostname)

            rows.append((
                msg.timestamp.isoformat(),
                msg.received_at.isoformat(),
                msg.source_ip,
                msg.source_port,
                msg.facility.value,
                msg.severity.value,
                msg.hostname,
                msg.app_name,
                msg.process_id,
                msg.message_id,
                msg.message,
                msg.raw,
                msg.protocol,
                msg.rfc_format,
                msg.structured_data,
                msg.cisco_sequence,
                msg.cisco_mnemonic,
                device_id,
            ))

            # Track device updates
            if device_id in device_updates:
                last_seen, count = device_updates[device_id]
                device_updates[device_id] = (msg.received_at.isoformat(), count + 1)
            else:
                device_updates[device_id] = (msg.received_at.isoformat(), 1)

        self._conn.executemany(
            """INSERT INTO messages
               (timestamp, received_at, source_ip, source_port, facility, severity,
                hostname, app_name, process_id, message_id, message, raw,
                protocol, rfc_format, structured_data, cisco_sequence, cisco_mnemonic, device_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )

        # Update device last_seen and message_count
        for device_id, (last_seen, count) in device_updates.items():
            self._conn.execute(
                "UPDATE devices SET last_seen = ?, message_count = message_count + ?, updated_at = ? WHERE id = ?",
                (last_seen, count, last_seen, device_id),
            )

        self._conn.commit()

    def search(
        self,
        keyword: str = "",
        source_ip: str = "",
        min_severity: int | None = None,
        max_severity: int | None = None,
        facility: int | None = None,
        device_id: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search messages with filters. Returns list of dicts."""
        conditions = []
        params: list[Any] = []

        if keyword:
            conditions.append("m.id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)")
            params.append(keyword)
        if source_ip:
            conditions.append("m.source_ip = ?")
            params.append(source_ip)
        if min_severity is not None:
            conditions.append("m.severity >= ?")
            params.append(min_severity)
        if max_severity is not None:
            conditions.append("m.severity <= ?")
            params.append(max_severity)
        if facility is not None:
            conditions.append("m.facility = ?")
            params.append(facility)
        if device_id is not None:
            conditions.append("m.device_id = ?")
            params.append(device_id)
        if start_time:
            conditions.append("m.timestamp >= ?")
            params.append(start_time.isoformat())
        if end_time:
            conditions.append("m.timestamp <= ?")
            params.append(end_time.isoformat())

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT m.*, d.display_name as device_name, d.color as device_color
            FROM messages m
            LEFT JOIN devices d ON m.device_id = d.id
            WHERE {where}
            ORDER BY m.timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = self._conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_message_count(self) -> int:
        """Get total number of stored messages."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM messages")
        return cursor.fetchone()[0]

    def get_devices(self) -> list[dict[str, Any]]:
        """Get all device profiles."""
        cursor = self._conn.execute(
            "SELECT * FROM devices ORDER BY display_name"
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_device(self, device_id: int, **kwargs: Any) -> None:
        """Update a device profile."""
        allowed = {"display_name", "color", "notes", "vendor", "hostname", "file_logging"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return

        updates["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [device_id]
        self._conn.execute(f"UPDATE devices SET {set_clause} WHERE id = ?", values)
        self._conn.commit()

    def get_alert_rules(self) -> list[dict[str, Any]]:
        """Get all alert rules."""
        cursor = self._conn.execute("SELECT * FROM alert_rules ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

    def save_alert_rule(self, rule: dict[str, Any]) -> int:
        """Insert or update an alert rule. Returns the rule ID."""
        now = datetime.now().isoformat()
        if "id" in rule and rule["id"]:
            rule["updated_at"] = now
            rule_id = rule.pop("id")
            set_clause = ", ".join(f"{k} = ?" for k in rule)
            values = list(rule.values()) + [rule_id]
            self._conn.execute(f"UPDATE alert_rules SET {set_clause} WHERE id = ?", values)
            self._conn.commit()
            return rule_id
        else:
            rule.pop("id", None)
            rule["created_at"] = now
            rule["updated_at"] = now
            cols = ", ".join(rule.keys())
            placeholders = ", ".join("?" for _ in rule)
            cursor = self._conn.execute(
                f"INSERT INTO alert_rules ({cols}) VALUES ({placeholders})",
                list(rule.values()),
            )
            self._conn.commit()
            return cursor.lastrowid

    def delete_alert_rule(self, rule_id: int) -> None:
        """Delete an alert rule."""
        self._conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
        self._conn.commit()

    def cleanup_old_messages(self, retention_days: int) -> int:
        """Delete messages older than retention_days. Returns count deleted."""
        if retention_days <= 0:
            return 0

        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        total_deleted = 0

        while True:
            cursor = self._conn.execute(
                "DELETE FROM messages WHERE id IN "
                "(SELECT id FROM messages WHERE received_at < ? LIMIT 1000)",
                (cutoff,),
            )
            deleted = cursor.rowcount
            self._conn.commit()
            total_deleted += deleted
            if deleted < 1000:
                break

        if total_deleted > 0:
            logger.info("Cleaned up %d old messages (retention: %d days)", total_deleted, retention_days)

        return total_deleted

    def get_stats(self) -> dict[str, Any]:
        """Get summary statistics for the dashboard."""
        stats = {}

        cursor = self._conn.execute("SELECT COUNT(*) FROM messages")
        stats["total_messages"] = cursor.fetchone()[0]

        cursor = self._conn.execute("SELECT COUNT(*) FROM devices")
        stats["total_devices"] = cursor.fetchone()[0]

        # Severity distribution
        cursor = self._conn.execute(
            "SELECT severity, COUNT(*) as count FROM messages GROUP BY severity ORDER BY severity"
        )
        stats["severity_counts"] = {row["severity"]: row["count"] for row in cursor}

        # Top 10 devices by message count
        cursor = self._conn.execute(
            """SELECT d.display_name, d.ip_address, d.message_count
               FROM devices d ORDER BY d.message_count DESC LIMIT 10"""
        )
        stats["top_devices"] = [dict(row) for row in cursor]

        # Messages in last hour
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE received_at >= ?", (one_hour_ago,)
        )
        stats["messages_last_hour"] = cursor.fetchone()[0]

        return stats

    def get_unique_source_ips(self) -> list[str]:
        """Get all unique source IPs that have sent messages."""
        cursor = self._conn.execute("SELECT DISTINCT ip_address FROM devices ORDER BY ip_address")
        return [row["ip_address"] for row in cursor]
