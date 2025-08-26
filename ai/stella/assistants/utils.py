"""
The Stella Assistant mode AI
"""

from typing import List, Dict
import traceback
from db.models.constella.frontend.message import Message
from db.models.constella.frontend.assistant_request import AssistantRequest

max_chars_in_context = 255000

def format_stella_assistant_instructions(request: AssistantRequest):
	message = f"""User's request: {request.user_message}
	Nodes on user's graph:{request.nodes}
	Edges on user's graph:{request.edges}
	Viewport on user's graph:{request.viewport}
	"""
	
	# Truncate message if it exceeds max chars
	if len(message) > max_chars_in_context:
		message = message[:max_chars_in_context]
		
	return message

def send_websocket_message_on_tool_call(tool_call) -> str:
    """Send websocket message based on tool call type"""
    try:
        match tool_call.function.name:
            case "search_user_notes_similarity" | "search_user_notes_keyword":
                return "|SEARCHING_NOTES|"
            case "google_search":
                return "|SEARCHING_GOOGLE|"
            case "get_website_url_content":
                return "|FETCHING_WEBPAGE|"
            case "create_note" | "edit_note" | "delete_note" | "create_connection" | "delete_connection":
                # Note operations are sent separately by the tool implementation, no progress string needed
                return ""
            case _:
                return ""
    except Exception:
        traceback.print_exc()


def get_prompt_instructions_from_user_data_for_voice_convo(request: AssistantRequest) -> str:
	"""
	Generate prompt instructions from user data specifically for voice conversation.
	Only includes node titles to keep the context concise for voice interactions.
	"""
	node_titles = []
	
	for node in request.nodes:
		if hasattr(node, 'data') and hasattr(node.data, 'note') and hasattr(node.data.note, 'rxdbData'):
			title = node.data.note.rxdbData.title
			if title:
				node_titles.append(title)
	
	if node_titles:
		titles_text = ", ".join(node_titles)
		return f"Titles of user's notes in user's graph: {titles_text}"
	else:
		return "No notes currently in user's graph"
