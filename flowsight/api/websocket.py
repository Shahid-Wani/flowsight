"""
FlowSight API WebSocket Routes

Real-time WebSocket endpoints for live flow updates.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from flowsight import get_logger
from flowsight.api import deps

logger = get_logger(__name__)

router = APIRouter()


def _recent_window(seconds: int) -> tuple[str, str]:
    """Return a Flux-ready ``(start, stop)`` pair covering the last N seconds.

    A relative duration plus an explicit ``now()`` keeps the window
    valid Flux regardless of local clock or timezone formatting:
    absolute naive timestamps (``datetime.utcnow().isoformat()``) are
    rejected by the storage layer's ``normalize_time_range``.
    """
    return f"-{seconds}s", "now()"


def _new_alerts_since(alert_rows: list[dict[str, Any]], last_seen: str) -> list[dict[str, Any]]:
    """Filter alert rows to those strictly newer than ``last_seen``.

    Strict comparison (no ``>=``) keeps each alert broadcasting exactly
    once: a re-read alert whose timestamp equals the last-seen mark is
    skipped instead of re-sent every tick.
    """
    return [row for row in alert_rows if row.get("timestamp") and row["timestamp"] > last_seen]


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
        """Periodically broadcast latest stats and new alerts."""
        last_seen = datetime.now(timezone.utc).isoformat()
        while self.active_connections:
            try:
                if deps.storage and deps.storage._connected:
                    start, stop = _recent_window(30)

                    series = await deps.storage.get_bandwidth_timeseries(start, stop, "10s")
                    if series:
                        latest = series[-1]
                        await self.broadcast({"type": "bandwidth_update", "data": latest})

                    # Get top talkers
                    talkers = await deps.storage.get_top_talkers(start, stop, 5, "bytes")
                    await self.broadcast({"type": "top_talkers_update", "data": talkers})

                    # Get protocol distribution (the frontend listens for this)
                    protocols = await deps.storage.get_protocol_distribution(start, stop)
                    await self.broadcast({"type": "protocols_update", "data": protocols})

                    # Broadcast alerts persisted since the last tick (the
                    # frontend Alerts page listens for this type). Alerts
                    # are timestamped at generation in other processes; the
                    # strict filter keeps each one broadcasting once.
                    alert_rows = await deps.storage.read_alerts(last_seen, "now()", limit=50)
                    new_alerts = _new_alerts_since(alert_rows, last_seen)
                    for alert in new_alerts:
                        await self.broadcast({"type": "alert", "data": alert})
                    if new_alerts:
                        last_seen = max(a["timestamp"] for a in new_alerts)
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
    if not deps.storage or not deps.storage._connected:
        await websocket.send_json({"type": "error", "message": "Storage not available"})
        return

    try:
        if query_type == "top_talkers":
            result = await deps.storage.get_top_talkers(
                params.get("start", "-5m"),
                params.get("stop", "now"),
                params.get("limit", 10),
                params.get("by", "bytes"),
            )
            await websocket.send_json(
                {"type": "query_result", "query": "top_talkers", "data": result}
            )
        elif query_type == "bandwidth":
            result = await deps.storage.get_bandwidth_timeseries(
                params.get("start", "-1h"), params.get("stop", "now"), params.get("interval", "1m")
            )
            await websocket.send_json(
                {"type": "query_result", "query": "bandwidth", "data": result}
            )
        elif query_type == "protocols":
            result = await deps.storage.get_protocol_distribution(
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
