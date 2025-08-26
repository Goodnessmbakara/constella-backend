from typing import Dict, List
from fastapi import WebSocket
import json
from collections import defaultdict

class WSManager:
    """
    WebSocket connection manager that groups connections per-tenant so that
    real-time updates are delivered only to the relevant clients.
    """

    def __init__(self):
        # Mapping tenant_name -> list[WebSocket]
        self.active: Dict[str, List[WebSocket]] = defaultdict(list)

    async def connect(self, tenant_name: str, ws: WebSocket):
        """Register a new websocket connection for a tenant."""
        await ws.accept()
        self.active[tenant_name].append(ws)

    def disconnect(self, tenant_name: str, ws: WebSocket):
        """Remove a websocket from the tenant's pool (and clean up if empty)."""
        if tenant_name in self.active and ws in self.active[tenant_name]:
            self.active[tenant_name].remove(ws)
            if not self.active[tenant_name]:
                del self.active[tenant_name]

    async def broadcast(self, message: dict):
        """
        Broadcast a message to all sockets belonging to the tenant specified in
        `message['tenant']`. If no tenant field is present, the message is sent
        to every connected socket (maintains previous behaviour).
        """
        tenant_name = message.get("tenant")
        if tenant_name is None:
            targets = [ws for sockets in self.active.values() for ws in sockets]
        else:
            targets = list(self.active.get(tenant_name, []))

        payload = json.dumps(message)
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                # Drop broken connections
                for t, sockets in list(self.active.items()):
                    if ws in sockets:
                        self.disconnect(t, ws)
                        break


# Singleton instance
ws_manager = WSManager()