"""
FlowSight API WebSocket Routes

Real-time WebSocket endpoints for live flow updates.
"""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from flowsight import get_logger
from flowsight.api.main import storage

logger = get_logger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._broadcast_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.debug("websocket_connected", count=len(self.active_connections))

        # Start broadcast task if not running
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self._broadcast_loop())

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.debug("websocket_disconnected", count=len(self.active_connections))

    async def send_personal_message(self, message: dict[str, Any], websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)

    async def broadcast(self, message: dict[str, Any]):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def _broadcast_loop(self):
        """Periodically broadcast latest stats."""
        while self.active_connections:
            try:
                if storage and storage._connected:
                    # Get latest bandwidth point
                    from datetime import datetime, timedelta

                    stop = datetime.utcnow().isoformat()
                    start = (datetime.utcnow() - timedelta(seconds=30)).isoformat()

                    series = await storage.get_bandwidth_timeseries(start, stop, "10s")
                    if series:
                        latest = series[-1]
                        await self.broadcast({"type": "bandwidth_update", "data": latest})

                    # Get top talkers
                    talkers = await storage.get_top_talkers(start, stop, 5, "bytes")
                    await self.broadcast({"type": "top_talkers_update", "data": talkers})
            except Exception as e:
                logger.warning("broadcast_error", error=str(e))

            await asyncio.sleep(5)  # Broadcast every 5 seconds


manager = ConnectionManager()


@router.websocket("/ws/live")
async def websocket_live(
    websocket: WebSocket, token: str | None = Query(None, description="Optional JWT token for auth")
):
    """WebSocket endpoint for real-time flow data."""
    await manager.connect(websocket)

    try:
        # Send initial connection message
        await websocket.send_json(
            {"type": "connected", "message": "Connected to FlowSight live feed"}
        )

        # Keep connection alive, handle incoming messages
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await handle_client_message(websocket, message)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception("websocket_error", error=str(e))
        manager.disconnect(websocket)


async def handle_client_message(websocket: WebSocket, message: dict[str, Any]):
    """Handle incoming WebSocket messages from client."""
    msg_type = message.get("type")

    if msg_type == "ping":
        await websocket.send_json({"type": "pong"})
    elif msg_type == "subscribe":
        channels = message.get("channels", ["bandwidth", "top_talkers"])
        await websocket.send_json({"type": "subscribed", "channels": channels})
    elif msg_type == "query":
        # Allow ad-hoc queries via WebSocket
        query_type = message.get("query")
        params = message.get("params", {})
        await handle_query(websocket, query_type, params)
    else:
        await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


async def handle_query(websocket: WebSocket, query_type: str, params: dict[str, Any]):
    """Handle ad-hoc queries via WebSocket."""
    if not storage or not storage._connected:
        await websocket.send_json({"type": "error", "message": "Storage not available"})
        return

    try:
        if query_type == "top_talkers":
            result = await storage.get_top_talkers(
                params.get("start", "-5m"),
                params.get("stop", "now"),
                params.get("limit", 10),
                params.get("by", "bytes"),
            )
            await websocket.send_json(
                {"type": "query_result", "query": "top_talkers", "data": result}
            )
        elif query_type == "bandwidth":
            result = await storage.get_bandwidth_timeseries(
                params.get("start", "-1h"), params.get("stop", "now"), params.get("interval", "1m")
            )
            await websocket.send_json(
                {"type": "query_result", "query": "bandwidth", "data": result}
            )
        elif query_type == "protocols":
            result = await storage.get_protocol_distribution(
                params.get("start", "-1h"), params.get("stop", "now")
            )
            await websocket.send_json(
                {"type": "query_result", "query": "protocols", "data": result}
            )
        else:
            await websocket.send_json(
                {"type": "error", "message": f"Unknown query type: {query_type}"}
            )
    except Exception as e:
        logger.exception("ws_query_failed", query=query_type, error=str(e))
        await websocket.send_json({"type": "error", "message": str(e)})
