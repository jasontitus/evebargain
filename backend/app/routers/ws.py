import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.notification import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint for real-time arbitrage alert delivery.

    The client sends its user_id as the first message after connection.
    All subsequent messages from the server are alert/notification payloads.
    """
    await websocket.accept()

    try:
        # Wait for client to send authentication message
        auth_msg = await websocket.receive_json()
        user_id = auth_msg.get("user_id")

        if not user_id:
            await websocket.send_json({"error": "user_id required"})
            await websocket.close()
            return

        # Register connection
        # Note: we re-accept internally via the manager, so we directly
        # add to the pool since we already accepted above
        if user_id not in ws_manager._connections:
            ws_manager._connections[user_id] = []
        ws_manager._connections[user_id].append(websocket)

        logger.info(f"WebSocket authenticated for user {user_id}")
        await websocket.send_json({"type": "connected", "user_id": user_id})

        # Keep connection alive, waiting for client messages (heartbeats)
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if user_id:
            ws_manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if user_id:
            ws_manager.disconnect(user_id, websocket)
