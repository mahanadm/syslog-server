"""Syslog severity levels, facility codes, and application defaults."""

from enum import IntEnum


class Severity(IntEnum):
    """Syslog severity levels per RFC 5424."""
    EMERGENCY = 0
    ALERT = 1
    CRITICAL = 2
    ERROR = 3
    WARNING = 4
    NOTICE = 5
    INFORMATIONAL = 6
    DEBUG = 7


class Facility(IntEnum):
    """Syslog facility codes per RFC 5424."""
    KERN = 0
    USER = 1
    MAIL = 2
    DAEMON = 3
    AUTH = 4
    SYSLOG = 5
    LPR = 6
    NEWS = 7
    UUCP = 8
    CRON = 9
    AUTHPRIV = 10
    FTP = 11
    NTP = 12
    AUDIT = 13
    ALERT = 14
    CLOCK = 15
    LOCAL0 = 16
    LOCAL1 = 17
    LOCAL2 = 18
    LOCAL3 = 19
    LOCAL4 = 20
    LOCAL5 = 21
    LOCAL6 = 22
    LOCAL7 = 23


SEVERITY_NAMES = {s: s.name for s in Severity}
FACILITY_NAMES = {f: f.name for f in Facility}

SEVERITY_COLORS = {
    Severity.EMERGENCY: "#FF0000",
    Severity.ALERT: "#FF3300",
    Severity.CRITICAL: "#FF6600",
    Severity.ERROR: "#FF9900",
    Severity.WARNING: "#FFCC00",
    Severity.NOTICE: "#33CC33",
    Severity.INFORMATIONAL: "#3399FF",
    Severity.DEBUG: "#999999",
}

# Default ports
DEFAULT_UDP_PORT = 514
DEFAULT_TCP_PORT = 514
DEFAULT_TLS_PORT = 6514

# Default performance settings
DEFAULT_QUEUE_MAX_SIZE = 100_000
DEFAULT_BATCH_SIZE = 500
DEFAULT_BATCH_TIMEOUT_MS = 100
DEFAULT_LIVE_VIEW_MAX_ROWS = 50_000

# Default storage settings
DEFAULT_MAX_FILE_SIZE_MB = 10
DEFAULT_MAX_ROTATED_FILES = 10
DEFAULT_RETENTION_DAYS = 0  # 0 = keep forever

# Month abbreviations for RFC 3164 parsing
MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
