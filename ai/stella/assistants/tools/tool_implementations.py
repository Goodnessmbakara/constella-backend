"""
The actual functions that are called when a tool is used by the assistant.
The entire file is passed and using the function name specified in the tools to the 
assistant, the function is called and its results are returned.
NOTE: tenant_name and other extra_args are passed to all the functions to prevent
an unexpected keyword error from happening.
"""
from db.weaviate.operations.general import query_by_vector
from ai.embeddings import create_embedding
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field
import traceback
import httpx
import html2text
from googleapiclient.discovery import build
import os
import json
from typing import Any, Dict
from websockets.exceptions import ConnectionClosedError

google_constella_api_key = os.environ.get('GOOGLE_CONSTELLA_API_KEY')
google_search_cx_uniqueid = 'c41e4d932d6f543f2'


def clean_results(results):
	"""
	Clean the results for the Assistants tool call processing.
	:param results: The results to clean.
	:return: The cleaned results as a string.
	"""
	final_str = ''
	for result in results:
		# Parse any datetime values in the result metadata
		for key, value in result.items():
			if isinstance(value, datetime):
				result[key] = value.isoformat()
		final_str += str(result) + '\n'
	return final_str

async def search_user_notes_similarity(query:str = '', similarity_setting:float = 0.5, tenant_name:str=None):
	try:
		query_vector = create_embedding(query)
		results = query_by_vector(tenant_name, query_vector, similarity_setting=similarity_setting, include_vector=False)["results"]
		return clean_results(results)
	except Exception as e:
		print('Error in search_user_notes_similarity: ', e)
		traceback.print_exc()
		return []

def html_to_text(html,ignore_links=False,bypass_tables=False,ignore_images=True):
	'''
	This function is used to convert html to text.
	It converts the html to text and returns the text.
	
	Args:
		html (str): The HTML content to convert to text.
		ignore_links (bool): Ignore links in the text. Use 'False' to receive the URLs of nested pages to scrape.
		bypass_tables (bool): Bypass tables in the text. Use 'False' to receive the text of the tables.
		ignore_images (bool): Ignore images in the text. Use 'False' to receive the text of the images.
	Returns:
		str: The text content of the webpage. If max_length is provided, the text will be truncated to the specified length.
	'''
	text = html2text.HTML2Text()
	text.ignore_links = ignore_links
	text.bypass_tables = bypass_tables
	text.ignore_images = ignore_images
	return text.handle(html,)

async def get_website_url_content(url: HttpUrl, ignore_links: bool = False, max_length: int = None, tenant_name:str=None):
	'''
	This function is used to scrape a webpage.
	It converts the html to text and returns the text.
	
	Args:
		plain_json (dict): The JSON data containing the URL to scrape. It is meant to be called as a tool call from an assistant.
		the json should be in the format of {"url": "https://www.example.com", "ignore_links": False, "max_length": 1000}

	Returns:
		str: The text content of the webpage. If max_length is provided, the text will be truncated to the specified length.
	'''
	header = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'}
	try:
		async with httpx.AsyncClient(follow_redirects=True) as client:
			response = await client.get(str(url), headers=header, timeout=5)
	except Exception as e:
		print('Error in webscrape: ', e)
		return "Error fetching the url "+str(url)
	print('response: ', response.text)
	out = html_to_text(response.text,ignore_links=ignore_links)
	if max_length:
		return out[0:max_length]
	else:
		return out


async def google_search(query: str, results: int = 5, exactTerms: str = None, excludeTerms: str = None, tenant_name:str=None):
	# foundational search function returns a google search result object
	service = build("customsearch", "v1", developerKey=google_constella_api_key)
	try:
		# 'results' parameter should be 'num' according to the API docs
		# Ensure results is between 1 and 10
		num = max(1, min(10, results))
		
		result = service.cse().list(
			q=query,
			cx=google_search_cx_uniqueid,
			num=num,  # Changed from results to num
			# exactTerms=exactTerms,
			# excludeTerms=excludeTerms
		).execute()
	except Exception as e:
		print('Error in google_search: ', e)
		traceback.print_exc()
		return None
	if result is not None and result.get('items'):
		return str(result.get('items'))
	else:
		print('No results found')
		return "No results found"

# -----------------------------------------------------------------------------
# NOTE OPERATION TOOL IMPLEMENTATIONS
# Each implementation sends the request to the connected websocket (frontend),
# and immediately returns success without waiting for a response.
# The websocket object is passed in via the `websocket_tool_io` extra_arg.
# -----------------------------------------------------------------------------

async def _send_tool_request(
	websocket_tool_io,
	payload: Dict[str, Any],
	timeout: int = 60,
):
	"""Helper to send a JSON payload over the websocket and immediately return success."""
	if websocket_tool_io is None:
		# In case websocket is not provided (e.g. during unit tests) just echo
		return {"status": "no_websocket", "echo": payload}

	try:
		# Check if websocket is still connected before sending
		if hasattr(websocket_tool_io, 'client_state') and websocket_tool_io.client_state.name != 'CONNECTED':
			return {"status": "websocket_disconnected", "message": "WebSocket connection is not active"}
		
		# Send the payload to the frontend
		await websocket_tool_io.send_json(payload)

		# Immediately return success without waiting for response
		return {"status": "success", "message": f"Tool call '{payload.get('tool_call', 'unknown')}' sent to frontend"}
	except ConnectionClosedError:
		# Handle websocket connection closed gracefully
		print(f"WebSocket connection closed while sending tool call '{payload.get('tool_call', 'unknown')}'")
		return {"status": "connection_closed", "message": "WebSocket connection was closed"}
	except Exception as e:  # pylint: disable=broad-except
		print(f"Error during websocket tool IO: {e}")
		traceback.print_exc()
		return {"error": str(e)}

# CREATE NOTE
async def create_note(title: str, content: str, tags: list[dict] | None = None, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "create_note",
		"arguments": {
			"title": title,
			"content": content,
			"tags": tags or []
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)

# EDIT NOTE
async def edit_note(note_uniqueid: str, title: str | None = None, content: str | None = None, tags: list[dict] | None = None, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "edit_note",
		"arguments": {
			"note_uniqueid": note_uniqueid,
			"title": title,
			"content": content,
			"tags": tags,
		},
		"tenant_name": tenant_name,
	}
	# Remove None values to keep the payload clean
	payload["arguments"] = {k: v for k, v in payload["arguments"].items() if v is not None}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)

# DELETE NOTE
async def delete_note(note_uniqueid: str, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "delete_note",
		"arguments": {
			"note_uniqueid": note_uniqueid,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)

# CREATE CONNECTION
async def create_connection(start_note_uniqueid: str, end_note_uniqueid: str, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "create_connection",
		"arguments": {
			"start_note_uniqueid": start_note_uniqueid,
			"end_note_uniqueid": end_note_uniqueid,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)

# DELETE CONNECTION
async def delete_connection(start_note_uniqueid: str, end_note_uniqueid: str, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "delete_connection",
		"arguments": {
			"start_note_uniqueid": start_note_uniqueid,
			"end_note_uniqueid": end_note_uniqueid,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)

# CONVERSE WITH USER
async def converse_with_user(long_message: str, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "converse_with_user",
		"arguments": {
			"long_message": long_message,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)

# -----------------------------------------------------------------------------
# NEW SPECIALISED NOTE-EDITING IMPLEMENTATIONS
# -----------------------------------------------------------------------------

# Edit only the note title
async def edit_note_title(note_uniqueid: str, new_title: str, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "edit_note_title",
		"arguments": {
			"note_uniqueid": note_uniqueid,
			"new_title": new_title,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)

# Add tags to a note
async def add_tags_to_note(note_uniqueid: str, tags_to_add: list[dict], tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "add_tags_to_note",
		"arguments": {
			"note_uniqueid": note_uniqueid,
			"tags_to_add": tags_to_add,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)


# Remove tags from a note
async def remove_tags_from_note(note_uniqueid: str, tags_to_remove: list[dict], tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "remove_tags_from_note",
		"arguments": {
			"note_uniqueid": note_uniqueid,
			"tags_to_remove": tags_to_remove,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)


# Delete part of content
async def delete_part_of_note_content(note_uniqueid: str, content_part_to_delete: str, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "delete_part_of_note_content",
		"arguments": {
			"note_uniqueid": note_uniqueid,
			"content_part_to_delete": content_part_to_delete,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)

# Replace part of content
async def replace_part_of_note_content(note_uniqueid: str, content_part_to_replace: str, replacement_content: str, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "replace_part_of_note_content",
		"arguments": {
			"note_uniqueid": note_uniqueid,
			"content_part_to_replace": content_part_to_replace,
			"replacement_content": replacement_content,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)

# Append new content
async def add_part_to_note_content(note_uniqueid: str, content_to_add: str, tenant_name: str = None, websocket_tool_io=None, **kwargs):
	payload = {
		"tool_call": "add_part_to_note_content",
		"arguments": {
			"note_uniqueid": note_uniqueid,
			"content_to_add": content_to_add,
		},
		"tenant_name": tenant_name,
	}
	result = await _send_tool_request(websocket_tool_io, payload)
	return json.dumps(result)