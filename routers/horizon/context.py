from datetime import datetime
import time
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
from ai.ai_api import stream_anthropic_response, stream_google_response, create_google_request
from fastapi import WebSocket, WebSocketDisconnect
from ai.horizon.assist_ai import get_horizon_system_prompt, parse_horizon_frontend_messages
import re
from uuid import UUID
from db.milvus.operations.general import query_by_vector
from ai.embeddings import create_our_embedding


router = APIRouter(
	prefix="/horizon/context",
	tags=["horizon_assist"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

def format_json_for_serialization(obj):
	"""
	Recursively convert datetime and UUID objects to strings for JSON serialization.
	"""
	if isinstance(obj, datetime):
		return obj.isoformat()
	elif isinstance(obj, UUID):
		return str(obj)
	elif isinstance(obj, dict):
		return {key: format_json_for_serialization(value) for key, value in obj.items()}
	elif isinstance(obj, list):
		return [format_json_for_serialization(item) for item in obj]
	else:
		return obj

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

class ContextRequest(BaseModel):
	screen_ocr: str
	tenant_name: str
	selected_text: Optional[str] = None


@router.websocket("/context-search-ws-topic-extraction")
async def websocket_context_search_endpoint(websocket: WebSocket):
	await websocket.accept()
	try:
		print('CONTEXT SEARCH WS RECEIVED')

		while True:
			try:
				# Receive request from the WebSocket connection
				req = await websocket.receive_json()
			except Exception as e:
				print('Error receiving request: ', e)
				traceback.print_exc()
				await websocket.send_json({"error": str(e)})
				continue
			
			print('REQ: ', req)

			# If init key in request, then send init message
			if 'init' in req:
				await websocket.send_text('|INIT|')
				continue
			
			try:
				# Parse the request
				context_request = ContextRequest(**req)
				
				# Extract search queries from OCR text using Gemini
				search_prompt = f"""This is a chunk of text on the screen. I want to see if I have important related notes to this text that could unlock new insights. Give me a list of 3 strings of the most relevant searches I can do to find such related notes. Additionally, if there are specific proper nouns, return those as queries by themselves as well as the other general topics. Return in a JSON format {{'search_queries': ['...', '...']}}

Text: {context_request.screen_ocr}"""

				ai_response = create_google_request(
					prompt=search_prompt,
					model_name="gemini-2.0-flash-lite",
					temperature=0.2,
					max_tokens=300,
					response_mime_type="application/json"
				)

				if not ai_response:
					await websocket.send_json({"error": "Failed to extract search queries"})
					continue

				# Parse the AI response to get search queries
				try:
					search_data = json.loads(ai_response)
					search_queries = search_data.get('search_queries', [])
					# Limit to just 3
					search_queries = search_queries[:3]
				except json.JSONDecodeError:
					await websocket.send_json({"error": "Failed to parse search queries"})
					continue

				# Search for related notes using each query
				all_results = []
				seen_ids = set()
				
				
				search_start_time = time.time()
				
				for query in search_queries:
					if not query.strip():
						continue
						
					try:
						# Try keyword search first
						keyword_results = query_by_keyword(
							tenant_name=context_request.tenant_name,
							keyword=query,
							top_k=10,
							include_metadata=True
						)
						
						# Add unique results
						for result in keyword_results.get('results', []):
							if result and result.get('uniqueid') not in seen_ids:
								all_results.append(result)
								seen_ids.add(result.get('uniqueid'))
								
						# Also try vector search using embeddings
						try:
							query_vector = create_embedding(query)
							if query_vector:
								vector_results = query_by_vector(
									tenant_name=context_request.tenant_name,
									query_vector=query_vector,
									top_k=10,
									similarity_setting=0.7,
									include_vector=False
								)
								
								# Add unique results from vector search
								for result in vector_results.get('results', []):
									if result and result.get('uniqueid') not in seen_ids:
										all_results.append(result)
										seen_ids.add(result.get('uniqueid'))
						except Exception as vector_e:
							print(f"Vector search error for query '{query}': {vector_e}")
							
					except Exception as search_e:
						print(f"Search error for query '{query}': {search_e}")
						continue
				
				search_end_time = time.time()
				search_execution_time = search_end_time - search_start_time
				print(f"Search execution time: {search_execution_time:.3f} seconds")

				# Send the combined results
				await websocket.send_json({
					"results": format_json_for_serialization(all_results),
					"search_queries_used": search_queries,
					"total_results": len(all_results)
				})

			except Exception as e:
				print('Error in context search request: ', e)
				traceback.print_exc()
				await websocket.send_json({"error": str(e)})

	except WebSocketDisconnect:
		pass
	except Exception as e:
		print('Error in context search websocket: ', e)
		traceback.print_exc()
		await websocket.send_json({"error": str(e)})

@router.websocket("/context-search-ws-sentence-chunks")
async def websocket_context_search_sentence_chunks_endpoint(websocket: WebSocket):
	await websocket.accept()
	try:
		print('CONTEXT SEARCH SENTENCE CHUNKS WS RECEIVED')

		while True:
			# Receive request from the WebSocket connection
			req = await websocket.receive_json()

			# If init key in request, then send init message
			if 'init' in req: 
				await websocket.send_text('|INIT|')
				continue
			
			try:
				# Parse the request
				context_request = ContextRequest(**req)

				if not context_request.tenant_name:
					await websocket.send_json({"error": "Tenant name is required"})
					continue

				
				# If selected_text is provided, use it directly as the only chunk
				if context_request.selected_text and context_request.selected_text.strip():
					print('Selected text: ', context_request.selected_text)
					sentence_chunks = [context_request.selected_text.strip()]
				else:
					# Divide OCR text into sentences and group into chunks		
					# Split text into sentences using basic punctuation
					sentences = re.split(r'[.!?]+', context_request.screen_ocr.strip())
					sentences = [s.strip() for s in sentences if s.strip()]
					
					# Group sentences into chunks of 3
					sentence_chunks = []
					for i in range(0, len(sentences), 3):
						chunk = ' '.join(sentences[i:i+3]).replace('||', ' ')
						if chunk.strip():
							sentence_chunks.append(chunk.strip())
					
					# If no sentences found, use the original text as one chunk
					if not sentence_chunks and context_request.screen_ocr.strip():
						sentence_chunks = [context_request.screen_ocr.strip()]
				
				# Limit to last 3 chunks
				sentence_chunks = sentence_chunks[-3:]
				
				# Search for related notes using each sentence chunk
				all_results = []
				seen_ids = set()
				
				
				for chunk in sentence_chunks:
					if not chunk.strip():
						continue
						
					try:
						# Create embedding for the sentence chunk
						chunk_vector = create_our_embedding(chunk)
						if not chunk_vector:
							continue
							
						# Perform vector search using the chunk embedding
						vector_results = query_by_vector(
							tenant_name=context_request.tenant_name,
							query_vector=chunk_vector,
							top_k=3,
							similarity_setting=0.35,
							include_vector=False
						)
						
						# Add unique results from vector search
						for result in vector_results.get('results', []):
							if result and result.get('uniqueid') not in seen_ids:
								# If title is missing, create it from content or filetext
								if not result.get('title'):
									source_text = result.get('content') or result.get('filetext')
									if source_text:
										result['title'] = source_text[:100]

								# Remove original text fields to keep payload light
								result.pop('content', None)
								result.pop('filetext', None)

								all_results.append(result)
								seen_ids.add(result.get('uniqueid'))
								
					except Exception as search_e:
						print(f"Search error for chunk '{chunk[:50]}...': {search_e}")
						continue
				

				# Send the combined results
				await websocket.send_json({
					"results": format_json_for_serialization(all_results),
					"sentence_chunks_used": sentence_chunks,
					"total_results": len(all_results)
				})

			except Exception as e:
				print('Error in sentence chunk context search request: ', e)
				traceback.print_exc()
				await websocket.send_json({"error": str(e)})

	except WebSocketDisconnect:
		pass
	except Exception as e:
		print('Error in sentence chunk context search websocket: ', e)
		traceback.print_exc()
		await websocket.send_json({"error": str(e)})
