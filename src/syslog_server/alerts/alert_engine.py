"""Alert engine — evaluates incoming messages against configured rules."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from syslog_server.core.message import SyslogMessage


@dataclass
class AlertRule:
    """An alert rule definition."""
    id: int = 0
    name: str = ""
    enabled: bool = True
    min_severity: int = 0
    max_severity: int = 3  # EMERGENCY through ERROR by default
    keyword_pattern: str = ""
    device_filter: str = ""  # Comma-separated device IDs, or empty for all
    cooldown_secs: int = 60
    sound_enabled: bool = False
    notification: bool = True
    _compiled_pattern: re.Pattern | None = field(default=None, repr=False)
    _last_fired: float = field(default=0.0, repr=False)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> AlertRule:
        """Create an AlertRule from a database row dict."""
        rule = AlertRule(
            id=d.get("id", 0),
            name=d.get("name", ""),
            enabled=bool(d.get("enabled", True)),
            min_severity=d.get("min_severity", 0),
            max_severity=d.get("max_severity", 3),
            keyword_pattern=d.get("keyword_pattern", "") or "",
            device_filter=d.get("device_filter", "") or "",
            cooldown_secs=d.get("cooldown_secs", 60),
            sound_enabled=bool(d.get("sound_enabled", False)),
            notification=bool(d.get("notification", True)),
        )
        if rule.keyword_pattern:
            try:
                rule._compiled_pattern = re.compile(rule.keyword_pattern, re.IGNORECASE)
            except re.error:
                rule._compiled_pattern = None
        return rule

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dict suitable for database storage."""
        return {
            "id": self.id,
            "name": self.name,
            "enabled": int(self.enabled),
            "min_severity": self.min_severity,
            "max_severity": self.max_severity,
            "keyword_pattern": self.keyword_pattern,
            "device_filter": self.device_filter,
            "cooldown_secs": self.cooldown_secs,
            "sound_enabled": int(self.sound_enabled),
            "notification": int(self.notification),
        }


class AlertEngine:
    """Evaluates syslog messages against alert rules."""

    def __init__(self):
        self._rules: list[AlertRule] = []

    def load_rules(self, rule_dicts: list[dict[str, Any]]) -> None:
        """Load alert rules from database row dicts."""
        self._rules = [AlertRule.from_dict(d) for d in rule_dicts]

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def remove_rule(self, rule_id: int) -> None:
        self._rules = [r for r in self._rules if r.id != rule_id]

    def evaluate(self, msg: SyslogMessage) -> list[AlertRule]:
        """Evaluate a message against all rules. Returns list of triggered rules."""
        triggered = []
        now = time.monotonic()

        for rule in self._rules:
            if not rule.enabled:
                continue

            # Check cooldown
            if (now - rule._last_fired) < rule.cooldown_secs:
                continue

            # Check severity range (lower number = more severe)
            if not (rule.min_severity <= msg.severity.value <= rule.max_severity):
                continue

            # Check device filter
            if rule.device_filter:
                # device_filter is comma-separated IPs or device IDs
                allowed = {x.strip() for x in rule.device_filter.split(",")}
                if msg.source_ip not in allowed:
                    continue

            # Check keyword pattern
            if rule.keyword_pattern and rule._compiled_pattern:
                if not rule._compiled_pattern.search(msg.message):
                    continue

            # All conditions met — trigger
            rule._last_fired = now
            triggered.append(rule)

        return triggered
