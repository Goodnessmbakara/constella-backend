from datetime import datetime
import json
from utils.notifs import send_ios_image_notification
from weaviate.exceptions import UnexpectedStatusCodeError
import fastapi
from fastapi import BackgroundTasks
from weaviate.classes.query import Filter, MetadataQuery
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import traceback
import sentry_sdk
from typing import List, Dict, Any, Optional
from db.weaviate.operations.general import (delete_all_records, delete_record,
	delete_records_by_ids, get_most_recent_records, get_record_by_id, get_records_by_ids,
	insert_record, query_by_filter, query_by_keyword, query_by_keyword_with_filter, query_by_vector,
	query_by_vector_with_filter, update_record_metadata, update_record_vector, upsert_records)
from ai.embeddings import create_embedding, create_file_embedding, get_image_to_text
from db.weaviate.records.note import WeaviateNote
from db.models.constella.long_job import LongJob
from constants import default_query_limit, image_note_prefix
from utils.constella.files.file_base64 import clean_base64
from utils.constella.files.s3.s3 import (get_file_url_from_path, get_signed_file_url,
	upload_file_bytes_to_s3, remove_signed_params_from_url)
from db.models.constella.constella_retry_queue import RetryQueue
from utils.constella.files.s3.s3_file_management import cloudfront_url_prefix
from ai.vision.images import (format_ocr_json_to_string, image_matches_instruction,
	openai_ocr_image_to_text)
from ai.stella.prompts import get_system_prompt
from ai.ai_api import stream_anthropic_response, stream_google_response
from fastapi import WebSocket, WebSocketDisconnect
from ai.horizon.assist_ai import get_horizon_system_prompt, parse_horizon_frontend_messages, convert_anthropic_to_google


router = APIRouter(
	prefix="/horizon/assist",
	tags=["horizon_assist"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

class HorizonAssist(BaseModel):
	ocr_text: str
	chat_messages: str

class ChatMessage(BaseModel):
	role: str
	content: str

class ChatRequest(BaseModel):
	messages: List[ChatMessage]
	max_tokens: int = 1024
	ocr_text: Optional[str] = None
	selected_text: Optional[str] = None
	other_data: Optional[Dict[str, Any]] = None

@router.websocket("/chat-ws")
async def websocket_chat_endpoint(websocket: WebSocket):
	await websocket.accept()
	try:
		print('HORIZON ASSIST WS RECEIVED')

		while True:
			# Receive request from the WebSocket connection and handle malformed JSON gracefully
			try:
				req = await websocket.receive_json()
			except Exception as e:
				# If JSON parsing fails (e.g., malformed payload), notify the client (if possible)
				# and break the loop so the websocket can be closed in the `finally` block.
				print("Chat-WS Error receiving JSON payload over websocket:", e)
				try:
					await websocket.send_text("|ERROR:INVALID_JSON|")
				except Exception:
					# If we cannot send a message back, proceed to close the connection silently.
					pass
				break

			# If init key in request, then send init message
			if 'init' in req:
				await websocket.send_text('|INIT|')
				continue
			
			try:
				# Extract image_bytes from top-level request
				image_bytes = req.get('imageBytes')
				
				messages = parse_horizon_frontend_messages(
					req['messages'], 
					model="google",
					image_bytes=image_bytes
				)			
				system_prompt = get_horizon_system_prompt(messages)

				for word in stream_google_response(
					messages,
					max_tokens=req.get('max_tokens', 1024),
					system_prompt=system_prompt,
					model='gemini-2.5-flash-preview-05-20',
					convert_func=convert_anthropic_to_google
				):
					try:
						await websocket.send_text(word)
					except Exception as e:
						print('Error in stream google response: ', e)
						await websocket.send_text("|ERROR|")
			except Exception as e:
				print('Error in stream google response: ', e)
				
				# Try anthropic as a backup
				messages = parse_horizon_frontend_messages(
					req['messages'], 
					model="anthropic",
					image_bytes=None  # Anthropic doesn't support images in this implementation
				)
				system_prompt = get_horizon_system_prompt(messages)

				for word in stream_anthropic_response(
					messages,
					max_tokens=req.get('max_tokens', 1024),
					system_prompt=system_prompt
				):
					await websocket.send_text(word)

	except WebSocketDisconnect:
		pass
	except Exception as e:
		print('Error in horizon assist chat request: ', e)
		traceback.print_exc()
		try:
			await websocket.send_json({"error": str(e)})
		except Exception:
			pass
	finally:
		# Ensure the websocket connection is properly closed regardless of what happens above.
		try:
			await websocket.close()
		except Exception:
			pass
