"""Alert notification dispatcher — stores alert history for the web UI."""

from __future__ import annotations

import logging

from syslog_server.alerts.alert_engine import AlertRule
from syslog_server.core.constants import SEVERITY_NAMES
from syslog_server.core.message import SyslogMessage

logger = logging.getLogger(__name__)


class Notifier:
    """Handles triggered alert rules — records history accessible via the web UI."""

    def __init__(self) -> None:
        self._history: list[dict] = []

    def on_alert_triggered(self, msg: SyslogMessage, rule: AlertRule) -> None:
        """Called by the dispatcher when an alert rule fires."""
        severity_name = SEVERITY_NAMES.get(msg.severity, "UNKNOWN")
        logger.warning(
            "Alert '%s' triggered: [%s] %s — %s",
            rule.name, severity_name, msg.source_ip, msg.message[:120],
        )
        self._history.append({
            "rule_name": rule.name,
            "severity": severity_name,
            "source_ip": msg.source_ip,
            "message": msg.message[:500],
            "timestamp": msg.received_at.isoformat(),
        })
        if len(self._history) > 1000:
            self._history = self._history[-500:]

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()
