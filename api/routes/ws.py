"""WebSocket endpoint for real-time pipeline updates."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config.logging_config import get_logger
from services.websocket_manager import manager

router = APIRouter()
logger = get_logger(__name__)


@router.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """Stream pipeline progress events for a given run.

    Clients connect with the run_id returned by POST /run-agent.
    Messages are JSON objects with ``{type, data, timestamp}`` envelope.
    Types: step_update | log | failure | fix | iteration | result | error
    """
    await manager.connect(websocket, run_id)
    try:
        # Keep connection alive — wait for client close
        while True:
            # We don't expect messages from the client, but we must
            # await to detect disconnection.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, run_id)
    except Exception:
        await manager.disconnect(websocket, run_id)
