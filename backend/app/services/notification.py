"""Pushing live updates to the browser over WebSockets.

WHY WEBSOCKETS
    Normal HTTP is one-way: the browser asks, the server answers. Alerts need
    the opposite -- the server learns something and wants to tell a browser
    that is not currently asking. A WebSocket is a connection that stays open
    so either side can send at any time.

WHAT THE MANAGER TRACKS
    `_connections` maps a user id to the list of open sockets for that user --
    a list, not a single socket, because the same person may have the dashboard
    and the popout window open at once, and both should update.

    The key is the *database* user id. Registering under anything else means
    messages are addressed to a key with no socket on it, and nothing arrives
    at all -- which is exactly the bug that made alerts silently never work.

    Sending to a closed socket raises, so failures are collected during the
    send loop and removed afterwards. Removing items from a list while
    iterating over it skips elements, so the two steps must stay separate.
"""

import json
import logging
from datetime import datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time alert delivery."""

    def __init__(self):
        # user_id -> list of active WebSocket connections
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        logger.info(f"WebSocket connected for user {user_id}")

    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self._connections:
            self._connections[user_id] = [
                ws for ws in self._connections[user_id] if ws != websocket
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info(f"WebSocket disconnected for user {user_id}")

    def has_connections(self, user_id: int) -> bool:
        return user_id in self._connections and len(self._connections[user_id]) > 0

    async def broadcast_to_user(self, user_id: int, payload: dict):
        """Send a JSON message to all active connections for a user."""
        if user_id not in self._connections:
            return

        dead_connections = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_json(payload)
            except Exception:
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self._connections[user_id].remove(ws)

    async def send_alert(self, user_id: int, alert_data: dict):
        """Send an arbitrage alert notification."""
        payload = {
            "type": "arbitrage_alert",
            "data": alert_data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.broadcast_to_user(user_id, payload)

    async def send_region_change(self, user_id: int, region_id: int, region_name: str):
        """Notify the frontend that the character changed regions."""
        payload = {
            "type": "region_change",
            "data": {
                "region_id": region_id,
                "region_name": region_name,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.broadcast_to_user(user_id, payload)

    async def send_progress(
        self,
        user_id: int,
        phase: str,
        region_name: str,
        completed: int,
        total: int,
        done: bool = False,
    ):
        """Report how far along a market fetch is.

        A full Jita pull is ~275 pages and takes several seconds, which is far
        too long to leave the UI showing an unqualified spinner.
        """
        payload = {
            "type": "fetch_progress",
            "data": {
                "phase": phase,
                "region_name": region_name,
                "completed": completed,
                "total": total,
                "done": done,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.broadcast_to_user(user_id, payload)

    async def send_market_update(self, user_id: int, region_id: int, deal_count: int):
        """Notify the frontend that market data was refreshed."""
        payload = {
            "type": "market_update",
            "data": {
                "region_id": region_id,
                "deal_count": deal_count,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.broadcast_to_user(user_id, payload)


# Singleton instance
ws_manager = ConnectionManager()
