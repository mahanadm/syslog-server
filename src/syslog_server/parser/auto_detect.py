"""Auto-detect syslog message format and parse accordingly.

Detection order:
1. RFC 5424 — check for version number after PRI
2. Cisco IOS — check for %FACILITY-SEVERITY-MNEMONIC pattern
3. Hirschmann — check for ISO timestamp + [bracket] app info
4. RFC 3164 — fallback for traditional BSD format
5. Raw fallback — if nothing matches, wrap raw data as a message
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from syslog_server.core.constants import Facility, Severity
from syslog_server.core.message import SyslogMessage
from syslog_server.parser.cisco import parse_cisco
from syslog_server.parser.hirschmann import parse_hirschmann
from syslog_server.parser.rfc3164 import parse_rfc3164
from syslog_server.parser.rfc5424 import parse_rfc5424


def decode_bytes(data: bytes) -> str:
    """Decode raw bytes from a syslog message, handling encoding chaos from OT devices."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")  # latin-1 never fails


def parse(
    raw: str,
    source_ip: str,
    source_port: int,
    protocol: str = "udp",
    received_at: Optional[datetime] = None,
) -> SyslogMessage:
    """Auto-detect format and parse a syslog message.

    Always returns a SyslogMessage — never returns None.
    If no parser matches, returns a raw fallback message.
    """
    if received_at is None:
        received_at = datetime.now()

    # Strip trailing newlines/carriage returns
    raw = raw.rstrip("\r\n")

    if not raw:
        return _raw_fallback(raw, source_ip, source_port, protocol, received_at)

    # Check if it starts with a PRI field <NNN>
    if not raw.startswith("<"):
        return _raw_fallback(raw, source_ip, source_port, protocol, received_at)

    # RFC 5424: after PRI, the next char should be the version digit (typically "1")
    # Pattern: <PRI>1 TIMESTAMP ...
    try:
        pri_end = raw.index(">")
        after_pri = raw[pri_end + 1:]
        if after_pri and after_pri[0].isdigit() and (len(after_pri) < 2 or after_pri[1] == " "):
            result = parse_rfc5424(raw, source_ip, source_port, protocol, received_at)
            if result is not None:
                return result
    except (ValueError, IndexError):
        pass

    # Cisco IOS: look for the %FACILITY-SEVERITY-MNEMONIC pattern anywhere in the message
    if "%" in raw:
        result = parse_cisco(raw, source_ip, source_port, protocol, received_at)
        if result is not None:
            return result

    # Hirschmann: ISO timestamp + [APPNAME TASKNAME TASKID] bracket format
    # Detect by looking for "[" (bracket app info) in the message
    if "[" in raw:
        result = parse_hirschmann(raw, source_ip, source_port, protocol, received_at)
        if result is not None:
            return result

    # RFC 3164 (BSD format) — the most common for OT devices
    result = parse_rfc3164(raw, source_ip, source_port, protocol, received_at)
    if result is not None:
        return result

    # Nothing matched — wrap as raw fallback
    return _raw_fallback(raw, source_ip, source_port, protocol, received_at)


def _raw_fallback(
    raw: str,
    source_ip: str,
    source_port: int,
    protocol: str,
    received_at: datetime,
) -> SyslogMessage:
    """Create a SyslogMessage from raw data that couldn't be parsed."""
    # Try to at least extract PRI if present
    facility = Facility.USER
    severity = Severity.NOTICE
    message = raw

    if raw.startswith("<"):
        try:
            pri_end = raw.index(">")
            pri = int(raw[1:pri_end])
            facility, severity = SyslogMessage.decode_priority(pri)
            message = raw[pri_end + 1:]
        except (ValueError, IndexError):
            pass

    return SyslogMessage(
        timestamp=received_at,
        received_at=received_at,
        source_ip=source_ip,
        source_port=source_port,
        facility=facility,
        severity=severity,
        hostname=source_ip,
        message=message,
        raw=raw,
        protocol=protocol,
        rfc_format="raw",
    )
