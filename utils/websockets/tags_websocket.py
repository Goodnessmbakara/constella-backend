from typing import Dict, List
from fastapi import WebSocket
import json
from collections import defaultdict

class TagsWSManager:
    """Connection manager for tag-related websocket updates, grouped per tenant."""

    def __init__(self):
        self.active: Dict[str, List[WebSocket]] = defaultdict(list)

    async def connect(self, tenant_name: str, ws: WebSocket):
        await ws.accept()
        self.active[tenant_name].append(ws)

    def disconnect(self, tenant_name: str, ws: WebSocket):
        if tenant_name in self.active and ws in self.active[tenant_name]:
            self.active[tenant_name].remove(ws)
            if not self.active[tenant_name]:
                del self.active[tenant_name]

    async def broadcast(self, message: dict):
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
                for t, sockets in list(self.active.items()):
                    if ws in sockets:
                        self.disconnect(t, ws)
                        break

# Singleton instance to be imported elsewhere
tags_ws_manager = TagsWSManager() 