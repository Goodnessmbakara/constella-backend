from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from utils.websockets.websocket_manager import manager
import asyncio
import json

router = APIRouter(
    prefix="/constella_db/tag",
    tags=["constella_db_tag_websocket"],
)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, tenant_name: str = Query(...)):
    """
    WebSocket endpoint for real-time tag updates.
    Clients connect with their tenant_name to receive updates for their tags.
    """
    await manager.connect(websocket, tenant_name)
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "tenant_name": tenant_name
        })
        
        # Keep connection alive and handle ping/pong
        while True:
            try:
                # Wait for any message from client (including ping)
                message = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                
                # Handle ping messages
                if message == "ping":
                    await websocket.send_text("pong")
                # Handle other messages if needed
                else:
                    data = json.loads(message)
                    # Process other message types if needed
                    
            except asyncio.TimeoutError:
                # Send a ping to check if connection is still alive
                try:
                    await websocket.send_json({"type": "ping"})
                except:
                    break
                    
    except WebSocketDisconnect:
        await manager.disconnect(websocket, tenant_name)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await manager.disconnect(websocket, tenant_name) 