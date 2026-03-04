"""REST API endpoints for device management."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from syslog_server.app import get_storage
from syslog_server.storage.storage_manager import StorageManager

router = APIRouter(tags=["devices"])


class DeviceUpdate(BaseModel):
    display_name: Optional[str] = None
    color: Optional[str] = None
    vendor: Optional[str] = None
    hostname: Optional[str] = None
    notes: Optional[str] = None
    file_logging: Optional[bool] = None


@router.get("/devices")
def list_devices(storage: StorageManager = Depends(get_storage)):
    return {"devices": storage.database.get_devices()}


@router.put("/devices/{device_id}")
def update_device(
    device_id: int,
    body: DeviceUpdate,
    storage: StorageManager = Depends(get_storage),
):
    updates: dict[str, Any] = {
        k: v for k, v in body.model_dump().items() if v is not None
    }
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    storage.database.update_device(device_id, **updates)
    return {"ok": True}
