"""Email alert notifier — detects OT switch events and sends SMTP notifications."""

from __future__ import annotations

import logging
import queue
import re
import smtplib
import socket
import threading
from collections import deque
from datetime import datetime
from email.mime.text import MIMEText
from time import monotonic
from typing import TYPE_CHECKING

from syslog_server.core.message import SyslogMessage

if TYPE_CHECKING:
    from syslog_server.core.config import ConfigManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event patterns (case-insensitive, matched against msg.message)
# ---------------------------------------------------------------------------
_EVENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "link_state": re.compile(
        r"link[\s_](up|down)|UPDOWN|LINKUP|LINKDOWN", re.IGNORECASE
    ),
    "spanning_tree": re.compile(
        r"spanning.tree|spantree|\bSTP\b|\bMSTP\b|\bRSTP\b|topology.change",
        re.IGNORECASE,
    ),
    "login_failure": re.compile(
        r"login.fail|authentication.fail|LOGIN_FAILED|invalid.*password",
        re.IGNORECASE,
    ),
    "config_change": re.compile(
        r"configuration.chang|CONFIG_I|nvram.*written|NVM state|hm2ConfigurationChanged",
        re.IGNORECASE,
    ),
    "power_supply": re.compile(
        r"power.supply.*(fail|absent|missing|error|fault)|PSU.*(fail|fault)|ENVMON.*SUPPLY",
        re.IGNORECASE,
    ),
    "high_temperature": re.compile(
        r"temperature.*(exceed|high|critical|alarm|warn)|TEMP.*(ALARM|CRIT)|thermal.*alarm",
        re.IGNORECASE,
    ),
    "ntp_sync_failure": re.compile(
        r"ntp.*(?:fail|not.sync|unsync|lost|timeout)|sntp.*(?:fail|timeout|not.sync)|NOTSYNCED",
        re.IGNORECASE,
    ),
    "device_reboot": re.compile(
        r"cold.start|warm.start|SYS-5-RELOAD|\breload\b|system.*restart|rebooted|restarting",
        re.IGNORECASE,
    ),
    "port_security": re.compile(
        r"port.security|port-security.*violation|PSECURE|MAC.*violation|secure.*violation",
        re.IGNORECASE,
    ),
    "fan_failure": re.compile(
        r"fan.*(fail|fault|missing|removed|absent|alarm)|FAN.*(ALARM|FAIL|FAULT)",
        re.IGNORECASE,
    ),
    "sfp_alarm": re.compile(
        r"sfp.*(alarm|power|warn|high|low|fail)|transceiver.*(alarm|warn|power)"
        r"|optical.*(alarm|power|high|low)|TX.*power|RX.*power",
        re.IGNORECASE,
    ),
}

_EVENT_LABELS: dict[str, str] = {
    "link_state": "Link State Change",
    "spanning_tree": "Spanning Tree / MST Event",
    "login_failure": "Login Failure",
    "config_change": "Switch Configuration Change",
    "power_supply": "Power Supply Failure",
    "high_temperature": "High Temperature Alarm",
    "ntp_sync_failure": "NTP Sync Failure",
    "device_reboot": "Device Reboot / Restart",
    "port_security": "Port Security Violation",
    "fan_failure": "Fan Failure",
    "sfp_alarm": "SFP Optical Power Alarm",
    "new_device": "New / Unknown Device",
}

# Sentinel for the sender thread to exit cleanly
_STOP = object()


class EmailNotifier:
    """Detects OT switch events and sends email alerts via SMTP.

    Designed to be called from the dispatcher thread; all SMTP I/O is done
    on a background daemon thread so it never blocks the message pipeline.
    """

    def __init__(self) -> None:
        # Cooldown tracking: event_key -> last_sent monotonic timestamp
        # event_key = "<event_type>:<source_ip>"
        self._last_sent: dict[str, float] = {}
        self._last_sent_lock = threading.Lock()

        # Per-source-IP sliding window for login failure rate limiting
        # ip -> deque of monotonic timestamps
        self._login_times: dict[str, deque[float]] = {}

        # Background SMTP sender
        self._send_queue: queue.Queue = queue.Queue(maxsize=200)
        self._thread = threading.Thread(target=self._sender_loop, daemon=True, name="EmailSender")
        self._thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_message(self, msg: SyslogMessage, config: "ConfigManager") -> None:
        """Check a single message against all enabled event patterns.

        Called from the dispatcher thread for every message in the batch.
        Config is read live so changes take effect without a server restart.
        """
        if not config.get("email", "enabled", default=False):
            return

        email_alerts = config.get("email_alerts") or {}
        cooldown_secs = int(email_alerts.get("cooldown_minutes", 15)) * 60

        for event_type, pattern in _EVENT_PATTERNS.items():
            if not email_alerts.get(event_type, True):
                continue

            if event_type == "login_failure":
                self._check_login_failure(msg, config, email_alerts, cooldown_secs)
                continue  # handled separately

            if not pattern.search(msg.message):
                continue

            self._maybe_send(event_type, msg.source_ip, cooldown_secs, config, msg)

    def send_new_device_alert(
        self, ip: str, hostname: str, config: "ConfigManager"
    ) -> None:
        """Send a new-device alert. Called from dispatcher when a new IP is first seen."""
        if not config.get("email", "enabled", default=False):
            return
        email_alerts = config.get("email_alerts") or {}
        if not email_alerts.get("new_device", True):
            return

        cooldown_secs = int(email_alerts.get("cooldown_minutes", 15)) * 60
        event_key = f"new_device:{ip}"

        with self._last_sent_lock:
            last = self._last_sent.get(event_key, 0.0)
            now = monotonic()
            if now - last < cooldown_secs:
                return
            self._last_sent[event_key] = now

        subject = f"[Syslog Alert] New Device — {ip}"
        body = self._format_body(
            event_label="New / Unknown Device",
            source_ip=ip,
            hostname=hostname,
            timestamp=datetime.now(),
            severity_name="Info",
            message=f"A new device has started sending syslog messages: {ip} ({hostname})",
            config=config,
        )
        self._enqueue(subject, body, config)

    def send_test_email(
        self, config: "ConfigManager", override_smtp: dict | None = None
    ) -> str:
        """Send a test email synchronously. Returns empty string on success, error message on failure.

        If *override_smtp* is provided it is used instead of the saved config, allowing
        the UI to test settings before saving.
        """
        smtp_cfg = override_smtp if override_smtp is not None else (config.get("email") or {})
        host = smtp_cfg.get("smtp_host", "")
        if not host:
            return "SMTP host is not configured."

        recipients = smtp_cfg.get("recipients", [])
        if not recipients:
            return "No recipients configured."

        web_port = config.get("web", "port", default=8080)
        subject = "[Syslog Alert] Test Email"
        body = (
            "This is a test email from your Syslog Server.\n\n"
            "If you received this, email alerts are configured correctly.\n"
            f"\n---\nSyslog Server | http://localhost:{web_port}\n"
        )
        try:
            self._send_smtp_from_cfg(subject, body, smtp_cfg)
            return ""
        except Exception as exc:
            return str(exc)

    def stop(self) -> None:
        """Signal the background sender thread to exit."""
        self._send_queue.put(_STOP)
        self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_login_failure(
        self,
        msg: SyslogMessage,
        config: "ConfigManager",
        email_alerts: dict,
        cooldown_secs: int,
    ) -> None:
        """Rate-limit login failure alerts: send only when threshold exceeded within window."""
        if not _EVENT_PATTERNS["login_failure"].search(msg.message):
            return

        threshold = int(email_alerts.get("login_failure_threshold", 3))
        window_secs = int(email_alerts.get("login_failure_window_secs", 300))
        ip = msg.source_ip
        now = monotonic()

        times = self._login_times.setdefault(ip, deque())
        times.append(now)
        # Prune old entries outside the window
        while times and (now - times[0]) > window_secs:
            times.popleft()

        if len(times) < threshold:
            return

        # Threshold reached — apply cooldown before alerting
        self._maybe_send("login_failure", ip, cooldown_secs, config, msg)

    def _maybe_send(
        self,
        event_type: str,
        source_ip: str,
        cooldown_secs: int,
        config: "ConfigManager",
        msg: SyslogMessage,
    ) -> None:
        """Send an alert if the per-event cooldown has elapsed."""
        event_key = f"{event_type}:{source_ip}"
        now = monotonic()

        with self._last_sent_lock:
            last = self._last_sent.get(event_key, 0.0)
            if now - last < cooldown_secs:
                return
            self._last_sent[event_key] = now

        severity_name = msg.severity.name.capitalize() if msg.severity else "Unknown"
        label = _EVENT_LABELS.get(event_type, event_type.replace("_", " ").title())
        device_label = msg.hostname or source_ip
        subject = f"[Syslog Alert] {label} — {source_ip}"
        body = self._format_body(
            event_label=label,
            source_ip=source_ip,
            hostname=device_label,
            timestamp=msg.received_at,
            severity_name=severity_name,
            message=msg.message,
            config=config,
        )
        self._enqueue(subject, body, config)

    def _format_body(
        self,
        event_label: str,
        source_ip: str,
        hostname: str,
        timestamp: datetime,
        severity_name: str,
        message: str,
        config: "ConfigManager",
    ) -> str:
        web_port = config.get("web", "port", default=8080)
        try:
            server_host = socket.gethostname()
        except Exception:
            server_host = "localhost"

        return (
            f"Event:    {event_label}\n"
            f"Device:   {source_ip} ({hostname})\n"
            f"Time:     {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Severity: {severity_name}\n"
            f"Message:  {message}\n"
            f"\n---\n"
            f"Syslog Server | http://{server_host}:{web_port}\n"
        )

    def _enqueue(self, subject: str, body: str, config: "ConfigManager") -> None:
        """Put an email task on the background send queue (non-blocking)."""
        smtp_cfg = dict(config.get("email") or {})
        try:
            self._send_queue.put_nowait((subject, body, smtp_cfg))
        except queue.Full:
            logger.warning("Email send queue is full — dropping alert: %s", subject)

    def _sender_loop(self) -> None:
        """Background thread: drain the send queue and deliver emails via SMTP."""
        while True:
            item = self._send_queue.get()
            if item is _STOP:
                break
            subject, body, smtp_cfg = item
            try:
                self._send_smtp_from_cfg(subject, body, smtp_cfg)
            except Exception:
                logger.exception("Failed to send alert email: %s", subject)

    def _send_smtp(self, subject: str, body: str, config: "ConfigManager") -> None:
        """Send synchronously (used for test email)."""
        smtp_cfg = dict(config.get("email") or {})
        self._send_smtp_from_cfg(subject, body, smtp_cfg)

    def _send_smtp_from_cfg(self, subject: str, body: str, smtp_cfg: dict) -> None:
        """Build and deliver the email using the supplied SMTP config dict."""
        host = smtp_cfg.get("smtp_host", "")
        port = int(smtp_cfg.get("smtp_port", 587))
        user = smtp_cfg.get("smtp_user", "")
        password = smtp_cfg.get("smtp_password", "")
        use_tls = smtp_cfg.get("use_tls", True)
        from_addr = smtp_cfg.get("from_address", "") or user
        recipients = smtp_cfg.get("recipients", [])

        if not host:
            raise ValueError("SMTP host is not configured")
        if not recipients:
            raise ValueError("No email recipients configured")
        if not from_addr:
            raise ValueError("From address is not configured")

        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(recipients)

        if use_tls:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if user and password:
                    server.login(user, password)
                server.sendmail(from_addr, recipients, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                if user and password:
                    server.login(user, password)
                server.sendmail(from_addr, recipients, msg.as_string())

        logger.info("Alert email sent: %s → %s", subject, recipients)
