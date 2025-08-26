from typing import Dict, Set
from fastapi import WebSocket
import json
import asyncio
from datetime import datetime

class ConnectionManager:
    """Manages WebSocket connections and broadcasts messages to connected clients."""
    
    def __init__(self):
        # Dictionary to store active connections by tenant_name
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Lock for thread-safe operations
        self.lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, tenant_name: str):
        """Accept a new WebSocket connection and add it to the active connections."""
        await websocket.accept()
        async with self.lock:
            if tenant_name not in self.active_connections:
                self.active_connections[tenant_name] = set()
            self.active_connections[tenant_name].add(websocket)
            print(f"Client connected for tenant: {tenant_name}. Total connections: {len(self.active_connections[tenant_name])}")
    
    async def disconnect(self, websocket: WebSocket, tenant_name: str):
        """Remove a WebSocket connection from the active connections."""
        async with self.lock:
            if tenant_name in self.active_connections:
                self.active_connections[tenant_name].discard(websocket)
                if not self.active_connections[tenant_name]:
                    del self.active_connections[tenant_name]
                print(f"Client disconnected from tenant: {tenant_name}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_text(message)
        except Exception as e:
            print(f"Error sending personal message: {e}")
    
    async def broadcast_to_tenant(self, tenant_name: str, message: dict):
        """Broadcast a message to all connections for a specific tenant."""
        async with self.lock:
            if tenant_name in self.active_connections:
                # Create a copy of connections to avoid modification during iteration
                connections = list(self.active_connections[tenant_name])
                
        # Send messages outside the lock to avoid blocking
        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected connections
        if disconnected:
            async with self.lock:
                if tenant_name in self.active_connections:
                    for conn in disconnected:
                        self.active_connections[tenant_name].discard(conn)
    
    async def broadcast_tag_update(self, tenant_name: str, action: str, tag_data: dict):
        """Broadcast a tag update to all connections for a specific tenant."""
        message = {
            "type": "tag_update",
            "action": action,  # "created", "updated", "deleted"
            "data": tag_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast_to_tenant(tenant_name, message)
    
    def get_connection_count(self, tenant_name: str = None) -> int:
        """Get the number of active connections for a tenant or all tenants."""
        if tenant_name:
            return len(self.active_connections.get(tenant_name, set()))
        return sum(len(connections) for connections in self.active_connections.values())

# Create a singleton instance
manager = ConnectionManager() 