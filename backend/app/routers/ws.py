import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.notification import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint for real-time arbitrage alert delivery.

    The connection is identified from the session cookie, which the browser
    sends on the WebSocket handshake just as it does for HTTP.

    It previously registered under whatever user_id the client sent as its
    first message. The frontend sends character_id there, while every server
    push (alerts, region changes, market updates, fetch progress) addresses the
    database user id -- so messages went to a key with no connection on it and
    nothing was ever delivered. Trusting that field also let any client
    subscribe to another player's alerts just by naming their character id.
    """
    await websocket.accept()

    user_id = websocket.session.get("user_id")
    if not user_id:
        await websocket.send_json({"error": "not authenticated"})
        await websocket.close(code=1008)
        return

    ws_manager._connections.setdefault(user_id, []).append(websocket)
    logger.info(f"WebSocket authenticated for user {user_id} (session)")
    await websocket.send_json({"type": "connected", "user_id": user_id})

    try:
        while True:
            data = await websocket.receive_json()
            # The client still opens with a legacy auth frame; it carries no
            # authority now, so anything that isn't a ping is simply ignored.
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(user_id, websocket)
