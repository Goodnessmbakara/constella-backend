from typing import Dict, Any, Literal
import os

import httpx

# Central sync server that fans out websocket events to all pods.
SYNC_SERVER_URL: str = os.getenv("SYNC_SERVER_URL", "https://instant-syncing-server.onrender.com").rstrip("/")

# Category names correspond to the router prefixes (`/constella_db/note`, `/constella_db/tag`)
async def second_broadcast_event(category: Literal["note", "tag"], message: Dict[str, Any]) -> None:
    """Forward *message* to the sync server so it can fan-out to other nodes.

    Parameters
    ----------
    category: Literal["notes", "tags"]
        The resource type. Determines the remote endpoint path
        (``/notes/broadcast-event`` or ``/tags/broadcast-event``).
    message: dict
        The JSON serialisable payload that would normally be broadcast to local
        websocket clients.
    """
    url = f"{SYNC_SERVER_URL}/constella_db/{category}/broadcast-event"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json=message)
    except Exception:
        # We *never* want a sync failure to break the main request flow – just
        # log and continue. Real logging can be wired in here if desired.
        pass 