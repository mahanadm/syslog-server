"""REST API endpoints for querying syslog messages."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from syslog_server.app import get_storage
from syslog_server.storage.storage_manager import StorageManager

router = APIRouter(tags=["messages"])


@router.get("/messages")
def search_messages(
    keyword: Optional[str] = Query(None),
    source_ip: Optional[str] = Query(None),
    min_severity: Optional[int] = Query(None, ge=0, le=7),
    max_severity: Optional[int] = Query(None, ge=0, le=7),
    facility: Optional[int] = Query(None),
    device_id: Optional[int] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    storage: StorageManager = Depends(get_storage),
):
    results = storage.database.search(
        keyword=keyword,
        source_ip=source_ip,
        min_severity=min_severity,
        max_severity=max_severity,
        facility=facility,
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    return {"messages": results, "count": len(results), "offset": offset}


@router.get("/messages/count")
def message_count(storage: StorageManager = Depends(get_storage)):
    return {"count": storage.database.get_message_count()}


@router.get("/messages/ips")
def unique_ips(storage: StorageManager = Depends(get_storage)):
    return {"ips": storage.database.get_unique_source_ips()}
