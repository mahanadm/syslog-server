"""RFC 5424 syslog message parser.

Handles the modern syslog format:
    <PRI>VERSION SP TIMESTAMP SP HOSTNAME SP APP-NAME SP PROCID SP MSGID SP STRUCTURED-DATA [SP MSG]

NILVALUE for any optional field is represented by "-".
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from syslog_server.core.message import SyslogMessage

# RFC 5424 pattern
# <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG
_RFC5424_PATTERN = re.compile(
    r"<(\d{1,3})>"       # PRI
    r"(\d+)"             # VERSION
    r"\s+"
    r"(\S+)"             # TIMESTAMP (ISO 8601 or NILVALUE "-")
    r"\s+"
    r"(\S+)"             # HOSTNAME
    r"\s+"
    r"(\S+)"             # APP-NAME
    r"\s+"
    r"(\S+)"             # PROCID
    r"\s+"
    r"(\S+)"             # MSGID
    r"\s+"
    r"(-|(?:\[.+?\])+)"  # STRUCTURED-DATA (NILVALUE or one or more SD-ELEMENT)
    r"(?:\s+(.*))?",     # MSG (optional)
    re.DOTALL,
)


def _parse_rfc5424_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse an RFC 5424 ISO 8601 timestamp."""
    if ts_str == "-":
        return None

    # Handle various ISO 8601 formats
    # Remove fractional seconds precision beyond 6 digits (Python max)
    ts_str = re.sub(r"(\.\d{6})\d+", r"\1", ts_str)

    # Try parsing with timezone
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue

    return None


def _nilvalue(val: str) -> Optional[str]:
    """Return None if val is the NILVALUE '-', otherwise return val."""
    return None if val == "-" else val


def parse_rfc5424(
    raw: str,
    source_ip: str,
    source_port: int,
    protocol: str = "udp",
    received_at: Optional[datetime] = None,
) -> Optional[SyslogMessage]:
    """Parse an RFC 5424 syslog message.

    Returns a SyslogMessage if parsing succeeds, None if the format doesn't match.
    """
    if received_at is None:
        received_at = datetime.now()

    match = _RFC5424_PATTERN.match(raw)
    if not match:
        return None

    pri = int(match.group(1))
    _version = match.group(2)  # Currently always "1"
    ts_str = match.group(3)
    hostname = _nilvalue(match.group(4))
    app_name = _nilvalue(match.group(5))
    process_id = _nilvalue(match.group(6))
    message_id = _nilvalue(match.group(7))
    structured_data = _nilvalue(match.group(8))
    message = match.group(9) or ""

    # Strip BOM from message if present (RFC 5424 allows UTF-8 BOM)
    if message.startswith("\ufeff"):
        message = message[1:]

    facility, severity = SyslogMessage.decode_priority(pri)

    timestamp = _parse_rfc5424_timestamp(ts_str)
    if timestamp is None:
        timestamp = received_at

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
        message_id=message_id,
        message=message,
        raw=raw,
        protocol=protocol,
        rfc_format="rfc5424",
        structured_data=structured_data,
    )
