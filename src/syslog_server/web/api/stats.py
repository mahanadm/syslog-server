"""REST API endpoint for dashboard statistics."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from syslog_server.app import get_dispatcher, get_listener_manager, get_storage
from syslog_server.core.dispatcher import MessageDispatcher
from syslog_server.network.listener_manager import ListenerManager
from syslog_server.storage.storage_manager import StorageManager

router = APIRouter(tags=["stats"])


@router.get("/stats")
def get_stats(
    storage: StorageManager = Depends(get_storage),
    dispatcher: MessageDispatcher = Depends(get_dispatcher),
    listener_manager: ListenerManager = Depends(get_listener_manager),
):
    db_stats = storage.database.get_stats()
    listener_statuses = {
        name: {
            "active": s.active,
            "protocol": s.protocol,
            "host": s.host,
            "port": s.port,
            "message_count": s.messages_received,
            "error": s.error,
        }
        for name, s in listener_manager.get_statuses().items()
    }
    return {
        **db_stats,
        "msgs_per_sec": round(dispatcher.msgs_per_sec, 2),
        "total_processed": dispatcher.total_processed,
        "listeners": listener_statuses,
    }
