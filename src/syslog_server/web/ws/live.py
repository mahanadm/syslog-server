"""WebSocket endpoint for live syslog message streaming."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from syslog_server.app import get_broadcaster
from syslog_server.web.broadcaster import WebSocketBroadcaster

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/live")
async def live_feed(ws: WebSocket):
    broadcaster: WebSocketBroadcaster = get_broadcaster()
    await broadcaster.connect(ws)
    try:
        while True:
            # Keep connection alive by reading (handles client pings / disconnects)
            await ws.receive_text()
    except WebSocketDisconnect:
        broadcaster.disconnect(ws)
    except Exception:
        broadcaster.disconnect(ws)
