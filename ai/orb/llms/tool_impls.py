from typing import Dict, Any, Optional
import json
import sys
from websockets.exceptions import ConnectionClosedError

# Import the Orb Cerebras tool definitions
from ai.orb.tools_cerebras import get_cerebras_orb_tools

# The list of tool JSON schemas that will be sent to the model via the OpenRouter API.
assistant_tools = get_cerebras_orb_tools(auto_execute=True)

# -----------------------------------------------------------------------------
# Helper – send the tool call request straight to the connected websocket
# -----------------------------------------------------------------------------
async def _send_tool_request(websocket_tool_io,
                            payload: Dict[str, Any]):
    """Send a JSON payload to the frontend via websocket and immediately return."""
    if websocket_tool_io is None:
        return {"status": "no_websocket", "echo": payload}

    try:
        # Only attempt to send if the websocket is still connected
        if hasattr(websocket_tool_io, 'client_state') and websocket_tool_io.client_state.name != 'CONNECTED':
            return {"status": "websocket_disconnected"}

        # Format the payload in the expected tool call structure
        tool_calls_response = [{
            "id": "",
            "type": "function",
            "function": {
                "name": payload.get("tool_call", ""),
                "arguments": json.dumps(payload.get("arguments", {}))
            }
        }]

        # Send tool calls as JSON
        await websocket_tool_io.send_json({
            "tool_calls": tool_calls_response
        })
        return {"status": "success"}
    except ConnectionClosedError:
        return {"status": "connection_closed"}
    except Exception as e:  # pylint: disable=broad-except
        return {"status": "error", "error": str(e)}

# -----------------------------------------------------------------------------
# Tool implementations
# -----------------------------------------------------------------------------

async def converse_with_user(message: str, websocket_tool_io=None, **kwargs):
    """Simple passthrough: just return the message back."""
    return {"message": message}


async def input_text(text: str, websocket_tool_io=None, **kwargs):
    payload = {
        "tool_call": "input_text",
        "arguments": {"text": text},
    }
    return await _send_tool_request(websocket_tool_io, payload)


async def click_text(text: str, websocket_tool_io=None, **kwargs):
    payload = {
        "tool_call": "click_text",
        "arguments": {"text": text},
    }
    return await _send_tool_request(websocket_tool_io, payload)


# Expose the current module object under the name expected by ai.orb.llms.openrouter
# This allows `getattr(tool_impls, ...)` look-ups to succeed.
tool_impls = sys.modules[__name__] 