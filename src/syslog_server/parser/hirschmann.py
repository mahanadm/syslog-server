"""Hirschmann switch syslog message parser.

Handles the Hirschmann-specific syslog format with [APPNAME TASKNAME TASKID] brackets.
Supports both timestamp formats:

BSD (standard RFC 3164):
    <PRI>Mmm dd HH:MM:SS HOSTNAME [APPNAME TASKNAME TASKID] MESSAGE

ISO (some firmware versions):
    <PRI>YYYY-MM-DD HH:MM:SS HOSTNAME [APPNAME TASKNAME TASKID] MESSAGE

Examples from real Hirschmann switches:
    <13>Dec 27 21:46:20 RSP-ECE55576F0F0 [SNMP_TRAP SNMPTrapTask 0x00230001] hm2ConfigurationChangedTrap: hm2FMNvmState.0=2
    <13>Dec 27 21:45:35 RSP-ECE55576F0F0 [USERMGR tLighty 0x0002005a] Login via web interface successful for user 'admin', role 'Administrator'.
    <13>2025-12-27 21:14:43 RSP-ECE55576F0F0 [USERMGR tLighty 0x0002005b] Logout via web interface successful for user 'admin', role 'Administrator'.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from syslog_server.core.constants import MONTH_MAP
from syslog_server.core.message import SyslogMessage
from syslog_server.parser.hirschmann_enricher import enrich_message

# --- BSD timestamp patterns (Mmm dd HH:MM:SS) ---

# Full 3-field bracket: <PRI>Mmm dd HH:MM:SS HOSTNAME [APP TASK ID] MSG
_HIRSCHMANN_BSD_PATTERN = re.compile(
    r"<(\d{1,3})>"                                  # PRI
    r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"      # Timestamp: Mmm dd HH:MM:SS
    r"\s+"
    r"(\S+)"                                        # HOSTNAME
    r"\s+"
    r"\[(\S+)\s+(\S+)\s+(\S+)\]"                   # [APPNAME TASKNAME TASKID]
    r"\s*"
    r"(.*)",                                        # MESSAGE
    re.DOTALL,
)

# Short bracket: <PRI>Mmm dd HH:MM:SS HOSTNAME [anything] MSG
_HIRSCHMANN_BSD_SHORT_PATTERN = re.compile(
    r"<(\d{1,3})>"                                  # PRI
    r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"      # Timestamp: Mmm dd HH:MM:SS
    r"\s+"
    r"(\S+)"                                        # HOSTNAME
    r"\s+"
    r"\[([^\]]+)\]"                                 # [... anything in brackets ...]
    r"\s*"
    r"(.*)",                                        # MESSAGE
    re.DOTALL,
)

# --- ISO timestamp patterns (YYYY-MM-DD HH:MM:SS) ---

# Full 3-field bracket: <PRI>YYYY-MM-DD HH:MM:SS HOSTNAME [APP TASK ID] MSG
_HIRSCHMANN_ISO_PATTERN = re.compile(
    r"<(\d{1,3})>"                                  # PRI
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"    # Timestamp: YYYY-MM-DD HH:MM:SS
    r"\s+"
    r"(\S+)"                                        # HOSTNAME
    r"\s+"
    r"\[(\S+)\s+(\S+)\s+(\S+)\]"                   # [APPNAME TASKNAME TASKID]
    r"\s*"
    r"(.*)",                                        # MESSAGE
    re.DOTALL,
)

# Short bracket: <PRI>YYYY-MM-DD HH:MM:SS HOSTNAME [anything] MSG
_HIRSCHMANN_ISO_SHORT_PATTERN = re.compile(
    r"<(\d{1,3})>"                                  # PRI
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"    # Timestamp: YYYY-MM-DD HH:MM:SS
    r"\s+"
    r"(\S+)"                                        # HOSTNAME
    r"\s+"
    r"\[([^\]]+)\]"                                 # [... anything in brackets ...]
    r"\s*"
    r"(.*)",                                        # MESSAGE
    re.DOTALL,
)


def _parse_bsd_timestamp(ts_str: str, now: Optional[datetime] = None) -> datetime:
    """Parse a BSD timestamp (Mmm dd HH:MM:SS) and infer the year."""
    if now is None:
        now = datetime.now()

    parts = ts_str.split()
    month = MONTH_MAP.get(parts[0], 1)
    day = int(parts[1])
    time_parts = parts[2].split(":")
    hour = int(time_parts[0])
    minute = int(time_parts[1])
    second = int(time_parts[2])

    year = now.year
    try:
        parsed = datetime(year, month, day, hour, minute, second)
    except ValueError:
        return now

    # If parsed date is more than 1 day in the future, it's probably last year
    if (parsed - now).days > 1:
        try:
            parsed = parsed.replace(year=year - 1)
        except ValueError:
            pass

    return parsed


def _parse_iso_timestamp(ts_str: str) -> datetime:
    """Parse an ISO timestamp (YYYY-MM-DD HH:MM:SS)."""
    try:
        return datetime.strptime(ts_str.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.now()


def parse_hirschmann(
    raw: str,
    source_ip: str,
    source_port: int,
    protocol: str = "udp",
    received_at: Optional[datetime] = None,
) -> Optional[SyslogMessage]:
    """Parse a Hirschmann syslog message.

    Tries BSD timestamp patterns first (most common), then ISO patterns.
    Returns a SyslogMessage if parsing succeeds, None if the format doesn't match.
    """
    if received_at is None:
        received_at = datetime.now()

    # --- Try BSD timestamp patterns (most common from real switches) ---

    # Full 3-field bracket: [APPNAME TASKNAME TASKID]
    match = _HIRSCHMANN_BSD_PATTERN.match(raw)
    if match:
        return _build_message_full(match, _parse_bsd_timestamp, source_ip, source_port, protocol, received_at)

    # Short bracket: [anything]
    match = _HIRSCHMANN_BSD_SHORT_PATTERN.match(raw)
    if match:
        return _build_message_short(match, _parse_bsd_timestamp, source_ip, source_port, protocol, received_at)

    # --- Try ISO timestamp patterns ---

    # Full 3-field bracket
    match = _HIRSCHMANN_ISO_PATTERN.match(raw)
    if match:
        return _build_message_full(match, _parse_iso_timestamp, source_ip, source_port, protocol, received_at)

    # Short bracket
    match = _HIRSCHMANN_ISO_SHORT_PATTERN.match(raw)
    if match:
        return _build_message_short(match, _parse_iso_timestamp, source_ip, source_port, protocol, received_at)

    return None


def _build_message_full(match, ts_parser, source_ip, source_port, protocol, received_at):
    """Build SyslogMessage from a full 3-field bracket match."""
    pri = int(match.group(1))
    ts_str = match.group(2)
    hostname = match.group(3)
    app_name = match.group(4)
    task_name = match.group(5)
    task_id = match.group(6)
    message = match.group(7).strip()

    facility, severity = SyslogMessage.decode_priority(pri)
    timestamp = ts_parser(ts_str) if ts_parser != _parse_iso_timestamp else ts_parser(ts_str)

    # Enrich SNMP trap messages with human-readable translations
    enriched_message = enrich_message(message)

    return SyslogMessage(
        timestamp=timestamp,
        received_at=received_at,
        source_ip=source_ip,
        source_port=source_port,
        facility=facility,
        severity=severity,
        hostname=hostname,
        app_name=app_name,
        process_id=task_name,
        message_id=task_id,
        message=enriched_message,
        raw=match.string,
        protocol=protocol,
        rfc_format="hirschmann",
    )


def _build_message_short(match, ts_parser, source_ip, source_port, protocol, received_at):
    """Build SyslogMessage from a short bracket match."""
    pri = int(match.group(1))
    ts_str = match.group(2)
    hostname = match.group(3)
    bracket_content = match.group(4).strip()
    message = match.group(5).strip()

    facility, severity = SyslogMessage.decode_priority(pri)
    timestamp = ts_parser(ts_str) if ts_parser != _parse_iso_timestamp else ts_parser(ts_str)

    # Try to split bracket content into parts
    parts = bracket_content.split()
    app_name = parts[0] if parts else bracket_content
    task_name = parts[1] if len(parts) > 1 else None
    task_id = parts[2] if len(parts) > 2 else None

    # Enrich SNMP trap messages with human-readable translations
    enriched_message = enrich_message(message)

    return SyslogMessage(
        timestamp=timestamp,
        received_at=received_at,
        source_ip=source_ip,
        source_port=source_port,
        facility=facility,
        severity=severity,
        hostname=hostname,
        app_name=app_name,
        process_id=task_name,
        message_id=task_id,
        message=enriched_message,
        raw=match.string,
        protocol=protocol,
        rfc_format="hirschmann",
    )
