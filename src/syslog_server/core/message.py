"""SyslogMessage dataclass — the canonical internal representation of a syslog message."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from syslog_server.core.constants import Facility, Severity


@dataclass(frozen=True, slots=True)
class SyslogMessage:
    """Immutable syslog message. Used throughout the application as the universal data model."""

    # Timing
    timestamp: datetime
    received_at: datetime

    # Source
    source_ip: str
    source_port: int

    # Syslog fields
    facility: Facility
    severity: Severity

    # Header fields
    hostname: Optional[str] = None
    app_name: Optional[str] = None
    process_id: Optional[str] = None
    message_id: Optional[str] = None

    # Body
    message: str = ""
    raw: str = ""

    # Metadata
    protocol: str = "udp"           # "udp", "tcp", or "tls"
    rfc_format: str = "rfc3164"     # "rfc3164", "rfc5424", or "cisco"

    # RFC 5424 structured data
    structured_data: Optional[str] = None

    # Cisco-specific fields
    cisco_sequence: Optional[int] = None
    cisco_mnemonic: Optional[str] = None

    @property
    def priority(self) -> int:
        """Calculate PRI value from facility and severity."""
        return (self.facility.value * 8) + self.severity.value

    @staticmethod
    def decode_priority(pri: int) -> tuple[Facility, Severity]:
        """Decode a PRI value into facility and severity."""
        facility_val = pri >> 3
        severity_val = pri & 0x07
        try:
            facility = Facility(facility_val)
        except ValueError:
            facility = Facility.USER
        try:
            severity = Severity(severity_val)
        except ValueError:
            severity = Severity.NOTICE
        return facility, severity
