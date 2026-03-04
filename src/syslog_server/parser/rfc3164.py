"""RFC 3164 (BSD) syslog message parser.

Handles the traditional syslog format used by most OT devices:
    <PRI>TIMESTAMP HOSTNAME MSG

Where TIMESTAMP is either:
    - Mmm dd hh:mm:ss  (e.g., "Oct 11 14:52:10") — standard RFC 3164
    - YYYY-MM-DD HH:MM:SS (e.g., "2025-12-27 21:14:43") — ISO format used by some modern devices
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from syslog_server.core.constants import MONTH_MAP, Facility, Severity
from syslog_server.core.message import SyslogMessage

# Standard RFC 3164: <PRI>Mmm dd HH:MM:SS HOSTNAME MSG
_RFC3164_PATTERN = re.compile(
    r"<(\d{1,3})>"
    r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
    r"\s+"
    r"(\S+)"
    r"\s+"
    r"(.*)",
    re.DOTALL,
)

# ISO timestamp variant: <PRI>YYYY-MM-DD HH:MM:SS HOSTNAME MSG
# Used by some modern OT devices that don't use the bracket format
_RFC3164_ISO_PATTERN = re.compile(
    r"<(\d{1,3})>"
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"
    r"\s+"
    r"(\S+)"
    r"\s+"
    r"(.*)",
    re.DOTALL,
)

# Extract tag[pid]: from the MSG portion
# e.g., "sshd[1234]: Failed password" -> tag=sshd, pid=1234, msg="Failed password"
_TAG_PATTERN = re.compile(
    r"^(\S+?)(?:\[(\d+)\])?:\s*(.*)",
    re.DOTALL,
)


def _parse_rfc3164_timestamp(ts_str: str, now: Optional[datetime] = None) -> datetime:
    """Parse an RFC 3164 timestamp (no year) and infer the year.

    RFC 3164 timestamps look like: "Oct 11 14:52:10"
    They have no year, so we infer from the current date.
    If the parsed date is more than 1 day in the future, we assume previous year.
    """
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
        # Invalid date (e.g., Feb 30) — use receive time
        return now

    # If parsed date is more than 1 day in the future, it's probably last year
    if (parsed - now).days > 1:
        try:
            parsed = parsed.replace(year=year - 1)
        except ValueError:
            pass

    return parsed


def _parse_iso_timestamp(ts_str: str, now: Optional[datetime] = None) -> datetime:
    """Parse an ISO-style timestamp YYYY-MM-DD HH:MM:SS."""
    try:
        return datetime.strptime(ts_str.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return now or datetime.now()


def parse_rfc3164(
    raw: str,
    source_ip: str,
    source_port: int,
    protocol: str = "udp",
    received_at: Optional[datetime] = None,
) -> Optional[SyslogMessage]:
    """Parse an RFC 3164 syslog message.

    Returns a SyslogMessage if parsing succeeds, None if the format doesn't match.
    """
    if received_at is None:
        received_at = datetime.now()

    # Try standard RFC 3164 pattern first, then ISO timestamp variant
    is_iso = False
    match = _RFC3164_PATTERN.match(raw)
    if not match:
        match = _RFC3164_ISO_PATTERN.match(raw)
        is_iso = True
    if not match:
        return None

    pri = int(match.group(1))
    ts_str = match.group(2)
    hostname = match.group(3)
    msg_part = match.group(4)

    facility, severity = SyslogMessage.decode_priority(pri)

    if is_iso:
        timestamp = _parse_iso_timestamp(ts_str, received_at)
    else:
        timestamp = _parse_rfc3164_timestamp(ts_str, received_at)

    # Try to extract tag/pid from the message
    app_name = None
    process_id = None
    message = msg_part

    tag_match = _TAG_PATTERN.match(msg_part)
    if tag_match:
        app_name = tag_match.group(1)
        process_id = tag_match.group(2)  # May be None
        message = tag_match.group(3)

    return SyslogMessage(
        timestamp=timestamp,
        received_at=received_at,
        source_ip=source_ip,
        source_port=source_port,
        facility=facility,
        severity=severity,
        hostname=hostname,
        app_name=app_name,
        process_id=process_id,
        message=message,
        raw=raw,
        protocol=protocol,
        rfc_format="rfc3164",
    )
