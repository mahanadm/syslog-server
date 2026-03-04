"""Cisco IOS syslog message parser.

Handles Cisco IOS / Stratix / Allen-Bradley switch log formats:
    <PRI>[seq]: [*]TIMESTAMP: %FACILITY-SEVERITY-MNEMONIC: message

Examples:
    <189>12: Oct 11 14:52:10.039: %LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down
    <189>*Mar  1 00:00:00.000: %SYS-5-CONFIG_I: Configured from console by console
    <189>2024-10-11T14:52:10.039+00:00: %LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from syslog_server.core.constants import MONTH_MAP, Severity
from syslog_server.core.message import SyslogMessage

# Cisco syslog message with sequence number, timestamp, and %FACILITY-SEV-MNEMONIC
_CISCO_PATTERN = re.compile(
    r"<(\d{1,3})>"                    # PRI
    r"(?:(\d+):\s+)?"                 # Optional sequence number
    r"(\*?"                           # Optional asterisk (clock not set)
    r"(?:\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?|"  # Mmm dd hh:mm:ss.sss
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?)"  # ISO 8601
    r")"
    r":\s+"
    r"%(\w+)-(\d)-(\w+)"             # %FACILITY-SEVERITY-MNEMONIC
    r":\s+"
    r"(.*)",                          # message
    re.DOTALL,
)

# Simpler pattern for Cisco messages without timestamp (some configs)
_CISCO_NO_TS_PATTERN = re.compile(
    r"<(\d{1,3})>"
    r"(?:(\d+):\s+)?"
    r"%(\w+)-(\d)-(\w+)"
    r":\s+"
    r"(.*)",
    re.DOTALL,
)

# Map Cisco severity digits to standard syslog severity
_CISCO_SEVERITY_MAP = {
    0: Severity.EMERGENCY,
    1: Severity.ALERT,
    2: Severity.CRITICAL,
    3: Severity.ERROR,
    4: Severity.WARNING,
    5: Severity.NOTICE,
    6: Severity.INFORMATIONAL,
    7: Severity.DEBUG,
}


def _parse_cisco_timestamp(ts_str: str, now: Optional[datetime] = None) -> datetime:
    """Parse a Cisco IOS timestamp. Handles multiple formats."""
    if now is None:
        now = datetime.now()

    # Remove leading asterisk (indicates clock not synchronized)
    clean_ts = ts_str.lstrip("*").strip()

    # Try ISO 8601 format first
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(clean_ts, fmt)
        except ValueError:
            continue

    # Try Cisco traditional format: Mmm dd hh:mm:ss.sss
    parts = clean_ts.split()
    if len(parts) >= 3:
        month_str = parts[0]
        month = MONTH_MAP.get(month_str)
        if month:
            try:
                day = int(parts[1])
                time_str = parts[2]
                # Remove fractional seconds for parsing
                time_base = time_str.split(".")[0]
                time_parts = time_base.split(":")
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                second = int(time_parts[2])

                year = now.year
                parsed = datetime(year, month, day, hour, minute, second)

                # Handle year boundary
                if (parsed - now).days > 1:
                    parsed = parsed.replace(year=year - 1)

                return parsed
            except (ValueError, IndexError):
                pass

    # If all parsing fails, use receive time
    return now


def parse_cisco(
    raw: str,
    source_ip: str,
    source_port: int,
    protocol: str = "udp",
    received_at: Optional[datetime] = None,
) -> Optional[SyslogMessage]:
    """Parse a Cisco IOS syslog message.

    Returns a SyslogMessage if parsing succeeds, None if the format doesn't match.
    """
    if received_at is None:
        received_at = datetime.now()

    # Try full pattern with timestamp
    match = _CISCO_PATTERN.match(raw)
    if match:
        pri = int(match.group(1))
        seq_str = match.group(2)
        ts_str = match.group(3)
        cisco_facility = match.group(4)
        cisco_sev = int(match.group(5))
        mnemonic = match.group(6)
        message = match.group(7)

        facility, _ = SyslogMessage.decode_priority(pri)
        severity = _CISCO_SEVERITY_MAP.get(cisco_sev, Severity.NOTICE)
        timestamp = _parse_cisco_timestamp(ts_str, received_at)

        return SyslogMessage(
            timestamp=timestamp,
            received_at=received_at,
            source_ip=source_ip,
            source_port=source_port,
            facility=facility,
            severity=severity,
            hostname=source_ip,  # Cisco often doesn't include hostname in the message
            app_name=cisco_facility,
            message=message,
            raw=raw,
            protocol=protocol,
            rfc_format="cisco",
            cisco_sequence=int(seq_str) if seq_str else None,
            cisco_mnemonic=mnemonic,
        )

    # Try pattern without timestamp
    match = _CISCO_NO_TS_PATTERN.match(raw)
    if match:
        pri = int(match.group(1))
        seq_str = match.group(2)
        cisco_facility = match.group(3)
        cisco_sev = int(match.group(4))
        mnemonic = match.group(5)
        message = match.group(6)

        facility, _ = SyslogMessage.decode_priority(pri)
        severity = _CISCO_SEVERITY_MAP.get(cisco_sev, Severity.NOTICE)

        return SyslogMessage(
            timestamp=received_at,
            received_at=received_at,
            source_ip=source_ip,
            source_port=source_port,
            facility=facility,
            severity=severity,
            hostname=source_ip,
            app_name=cisco_facility,
            message=message,
            raw=raw,
            protocol=protocol,
            rfc_format="cisco",
            cisco_sequence=int(seq_str) if seq_str else None,
            cisco_mnemonic=mnemonic,
        )

    return None
