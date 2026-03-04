"""REST API endpoints for reading and updating server configuration."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from syslog_server.alerts.email_notifier import EmailNotifier
from syslog_server.app import get_config, get_email_notifier, get_listener_manager, get_ntp_server
from syslog_server.core.config import ConfigManager
from syslog_server.network.listener_manager import ListenerManager
from syslog_server.network.ntp_server import NtpServer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])


@router.get("/config")
def get_full_config(config: ConfigManager = Depends(get_config)):
    return config.get()


@router.put("/config")
async def update_config(
    body: dict[str, Any],
    config: ConfigManager = Depends(get_config),
    listener_manager: ListenerManager = Depends(get_listener_manager),
    ntp_server: NtpServer = Depends(get_ntp_server),
):
    """Update configuration values. Body is a nested dict matching the config structure."""
    _apply_nested(config, body)
    config.save()

    # Restart listeners if listener config changed
    if "listeners" in body:
        try:
            listener_manager.stop()
            listener_manager.start()
            listener_manager.start_listeners_from_config()
        except Exception:
            logger.exception("Failed to restart listeners after config update")

    # Restart NTP server if NTP config changed
    if "ntp" in body:
        ntp_server.stop()
        if config.get("ntp", "enabled", default=False):
            ntp_host = config.get("ntp", "host", default="0.0.0.0")
            ntp_port = config.get("ntp", "port", default=123)
            try:
                await ntp_server.start(ntp_host, ntp_port)
            except Exception:
                logger.exception("Failed to restart NTP server after config update")

    return {"ok": True}


@router.post("/config/test-email")
def test_email(
    config: ConfigManager = Depends(get_config),
    email_notifier: EmailNotifier = Depends(get_email_notifier),
):
    """Send a test email using the current SMTP configuration."""
    error = email_notifier.send_test_email(config)
    if error:
        return {"ok": False, "error": error}
    return {"ok": True}


def _apply_nested(config: ConfigManager, updates: dict[str, Any], prefix: list[str] = []) -> None:
    for key, value in updates.items():
        path = prefix + [key]
        if isinstance(value, dict):
            _apply_nested(config, value, path)
        else:
            config.set(*path, value)
