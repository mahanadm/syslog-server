"""REST API endpoints for alert rule management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from syslog_server.app import get_notifier, get_storage
from syslog_server.alerts.notifier import Notifier
from syslog_server.storage.storage_manager import StorageManager

router = APIRouter(tags=["alerts"])


class AlertRuleBody(BaseModel):
    id: int | None = None
    name: str
    enabled: bool = True
    min_severity: int = 0
    max_severity: int = 7
    keyword_pattern: str = ""
    device_filter: str = ""
    cooldown_secs: int = 60
    sound_enabled: bool = False
    notification: bool = True


def _reload_alert_engine(storage: StorageManager) -> None:
    """Reload alert rules into the running alert engine via the app singleton."""
    from syslog_server.app import _dispatcher
    if _dispatcher and _dispatcher._alert_engine:
        rules = storage.database.get_alert_rules()
        _dispatcher._alert_engine.load_rules(rules)


@router.get("/alerts")
def list_alert_rules(storage: StorageManager = Depends(get_storage)):
    return {"rules": storage.database.get_alert_rules()}


@router.post("/alerts", status_code=201)
def create_alert_rule(body: AlertRuleBody, storage: StorageManager = Depends(get_storage)):
    rule_dict: dict[str, Any] = body.model_dump(exclude={"id"})
    rule_id = storage.database.save_alert_rule(rule_dict)
    _reload_alert_engine(storage)
    return {"id": rule_id}


@router.put("/alerts/{rule_id}")
def update_alert_rule(
    rule_id: int, body: AlertRuleBody, storage: StorageManager = Depends(get_storage)
):
    rule_dict: dict[str, Any] = body.model_dump()
    rule_dict["id"] = rule_id
    storage.database.save_alert_rule(rule_dict)
    _reload_alert_engine(storage)
    return {"ok": True}


@router.delete("/alerts/{rule_id}")
def delete_alert_rule(rule_id: int, storage: StorageManager = Depends(get_storage)):
    storage.database.delete_alert_rule(rule_id)
    _reload_alert_engine(storage)
    return {"ok": True}


@router.get("/alerts/history")
def alert_history(notifier: Notifier = Depends(get_notifier)):
    return {"history": notifier.history}


@router.delete("/alerts/history")
def clear_alert_history(notifier: Notifier = Depends(get_notifier)):
    notifier.clear_history()
    return {"ok": True}
