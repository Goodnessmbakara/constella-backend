import os
import asyncio
import json
import traceback
import websockets
import uuid
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from ai.horizon.meeting_mode import MeetingAssistant
from ai.horizon.suggestions_mode import SuggestionsAssistant
from ai.ai_api import stream_openai_response
from db.weaviate.records.meeting_note import MeetingNote
from db.milvus.operations.general import insert_record, query_by_filter, get_record_by_id, delete_record
from db.milvus.operations.general import query_by_hybrid_with_filter
from ai.embeddings import create_our_embedding


router = APIRouter(
	prefix="/horizon/meeting",
	tags=["horizon_meeting"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)


@router.websocket("/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
	"""
	WebSocket endpoint for chat UI with meeting context
	Handles real-time chat with AI assistant using meeting notes and transcript
	"""
	await websocket.accept()
	
	# Store meeting context
	meeting_notes = []
	meeting_transcript = []
	conversation_history = []
	
	try:
		while True:
			# Receive message from frontend
			data = await websocket.receive_text()
			message_data = json.loads(data)
			
			# Handle initial connection with meeting context
			if "meetingNotes" in message_data and "meetingTranscript" in message_data:
				meeting_notes = message_data.get("meetingNotes", [])
				meeting_transcript = message_data.get("meetingTranscript", [])
				
				# Send acknowledgment
				await websocket.send_text(json.dumps({
					"type": "context_received",
					"message": "Meeting context received successfully"
				}))
				continue
			
			# Handle chat messages
			if "role" in message_data and "content" in message_data:
				user_message = {
					"role": message_data["role"],
					"content": message_data["content"]
				}
				
				# Add user message to conversation history
				conversation_history.append(user_message)
				
				# Prepare context for AI
				context_prompt = ""
				if meeting_notes:
					context_prompt += f"Meeting Notes:\n{json.dumps(meeting_notes, indent=2)}\n\n"
				if meeting_transcript:
					context_prompt += f"Meeting Transcript:\n{json.dumps(meeting_transcript, indent=2)}\n\n"
				
				# Build messages for AI with context
				system_message = {
					"role": "system",
					"content": f"""You are an AI assistant helping with meeting-related questions and tasks. 
					You have access to the current meeting notes and transcript provided below.
					
					{context_prompt}
					
					Please provide helpful, concise responses based on the meeting context when relevant.
					If the user's question is not related to the meeting, respond normally."""
				}
				
				# Prepare messages for streaming
				messages_for_ai = [system_message] + conversation_history
				
				# Start streaming response
				ai_response_content = ""
				
				try:
					# Stream AI response
					async for chunk in async_stream_openai_response(
						messages=messages_for_ai,
						max_tokens=1000,
						model="gpt-4o-mini",
						temperature=0.7
					):
						if chunk:
							ai_response_content += chunk
							
							# Send streaming chunk to frontend
							await websocket.send_text(json.dumps({
								"type": "stream_chunk",
								"content": chunk
							}))
					
					# Add AI response to conversation history
					ai_message = {
						"role": "assistant",
						"content": ai_response_content
					}
					conversation_history.append(ai_message)
					
					# Send completion signal
					await websocket.send_text(json.dumps({
						"type": "stream_complete",
						"message": ai_message
					}))
					
				except Exception as e:
					print(f"Error during AI response generation: {e}")
					traceback.print_exc()
					await websocket.send_text(json.dumps({
						"type": "error",
						"message": "Failed to generate AI response"
					}))
			
	except WebSocketDisconnect:
		print("WebSocket chat disconnected")
	except Exception as e:
		print(f"WebSocket chat error: {e}")
		traceback.print_exc()
		try:
			await websocket.send_text(json.dumps({
				"type": "error",
				"message": "An unexpected error occurred"
			}))
		except:
			pass


async def async_stream_openai_response(messages, max_tokens=1000, model="gpt-4o-mini", temperature=0.7):
	"""
	Async wrapper for streaming OpenAI responses
	"""
	try:
		# Import the sync streaming function
		from ai.ai_api import stream_openai_response as sync_stream_openai
		from concurrent.futures import ThreadPoolExecutor
		import queue
		import threading
		
		# Create a queue to pass chunks between threads
		chunk_queue = queue.Queue()
		
		def stream_to_queue():
			try:
				for chunk in sync_stream_openai(
					messages=messages,
					max_tokens=max_tokens,
					model=model,
					temperature=temperature
				):
					chunk_queue.put(chunk)
				chunk_queue.put(None)  # Signal end of stream
			except Exception as e:
				chunk_queue.put(f"ERROR: {str(e)}")
		
		# Start the streaming in a separate thread
		thread = threading.Thread(target=stream_to_queue)
		thread.start()
		
		# Yield chunks as they become available
		while True:
			try:
				# Use asyncio to make the queue get non-blocking
				loop = asyncio.get_event_loop()
				chunk = await loop.run_in_executor(None, chunk_queue.get, True, 1.0)
				
				if chunk is None:  # End of stream
					break
				elif isinstance(chunk, str) and chunk.startswith("ERROR:"):
					raise Exception(chunk[6:])  # Remove "ERROR:" prefix
				else:
					yield chunk
					
			except queue.Empty:
				await asyncio.sleep(0.1)  # Small delay before retrying
				continue
		
		# Wait for thread to complete
		thread.join()
		
	except Exception as e:
		print(f"Error in async streaming: {e}")
		traceback.print_exc()


class DeleteMeetingNoteIn(BaseModel):
	tenant_name: str
	unique_id: str


@router.post("/create")
async def create_meeting_note(meeting_data: dict):
	"""
	Create a new meeting note with the provided data
	"""
	try:
		# Extract tenant_name from the request
		tenant_name = meeting_data.get("tenant_name")
		if not tenant_name:
			raise HTTPException(status_code=400, detail="tenant_name is required")
		
		# Generate unique ID if not provided
		if not meeting_data.get("uniqueid"):
			meeting_data["uniqueid"] = str(uuid.uuid4())
		
		# Create MeetingNote instance
		meeting_note = MeetingNote.from_request_data(meeting_data, tenant_name)
		
		# The referenceId for the main note is its own uniqueid
		meeting_note.properties["referenceId"] = meeting_note.uniqueid
		
		# Generate text content for embedding from title, description, notes and transcript
		embedding_text = ""
		
		# Include title and description in embedding
		if meeting_note.properties.get("title"):
			embedding_text += f"{meeting_note.properties['title']} "
		if meeting_note.properties.get("description"):
			embedding_text += f"{meeting_note.properties['description']} "
		
		# Extract text from notes
		if meeting_note.properties.get("notes"):
			for note in meeting_note.properties["notes"]:
				if isinstance(note, dict):
					embedding_text += f"{note.get('content', '')} "
				elif isinstance(note, str):
					embedding_text += f"{note} "
		
		# Extract text from transcript
		if meeting_note.properties.get("transcript"):
			for transcript_item in meeting_note.properties["transcript"]:
				if isinstance(transcript_item, dict):
					embedding_text += f"{transcript_item.get('text', '')} "
				elif isinstance(transcript_item, str):
					embedding_text += f"{transcript_item} "
		
		# Generate embedding using our custom embedding service
		if embedding_text.strip():
			meeting_note.vector = create_our_embedding(embedding_text.strip())
		else:
			# If no text content, create a default embedding
			meeting_note.vector = create_our_embedding("Meeting note")
		
		# Insert into Milvus
		record_id = insert_record(tenant_name, meeting_note)

		# --------------------------------------------------------------
		# Create derived records for notes-only and transcript-only
		# --------------------------------------------------------------
		try:
			import json as _json

			# Helper to create a derivative MeetingNote sharing all metadata but
			# with a new uniqueid, updated vector and referenceId pointing to the
			# original record.
			def _create_derivative(vector_source_text: str) -> MeetingNote:
				return MeetingNote(
					uniqueid=str(uuid.uuid4()),
					vector=create_our_embedding(vector_source_text[:3000] if vector_source_text else ""),
					notes=meeting_note.properties.get("notes", []),
					transcript=meeting_note.properties.get("transcript", []),
					created=meeting_note.properties.get("created"),
					ai_chat_messages=meeting_note.properties.get("ai_chat_messages", []),
					tenant_name=tenant_name,
					title=meeting_note.properties.get("title", "Untitled Meeting"),
					description=meeting_note.properties.get("description", ""),
					lastModified=meeting_note.properties.get("lastModified"),
					lastUpdateDevice=meeting_note.properties.get("lastUpdateDevice", ""),
					lastUpdateDeviceId=meeting_note.properties.get("lastUpdateDeviceId", ""),
					referenceId=meeting_note.uniqueid,
				)

			# Derivative 1: notes-only
			notes_text = _json.dumps(meeting_note.properties.get("notes", []))
			notes_only_record = _create_derivative(notes_text)
			insert_record(tenant_name, notes_only_record)

			# Derivative 2: transcript-only
			transcript_text = _json.dumps(meeting_note.properties.get("transcript", []))
			transcript_only_record = _create_derivative(transcript_text)
			insert_record(tenant_name, transcript_only_record)
		except Exception as _e:
			# Log but don't fail the request if derivative insertion has issues
			print(f"Warning: failed to insert derivative meeting records: {_e}")
			traceback.print_exc()
		
		return JSONResponse(
			status_code=201,
			content={
				"success": True,
				"message": "Meeting note created successfully",
				"meeting_id": record_id,
				"uniqueid": meeting_note.uniqueid,
				"title": meeting_note.properties.get("title", "Untitled Meeting"),
				"description": meeting_note.properties.get("description", "")
			}
		)
		
	except Exception as e:
		print(f"Error creating meeting note: {e}")
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to create meeting note")


@router.get("/list/{tenant_name}")
async def get_meeting_notes(tenant_name: str, limit: int = 50, offset: int = 0):
	"""
	Get meeting notes for a specific tenant using Milvus query_by_filter
	"""
	try:
		# Filter for meeting notes only
		filter_expr = 'recordType == "meeting_note"'
		
		# Query Milvus using the filter
		results = query_by_filter(
			tenant_name=tenant_name,
			filter_expr=filter_expr,
			top_k=limit
		)
		
		meeting_notes_raw = results.get("results", [])

		# Deduplicate by referenceId so that only one record is returned per
		# original meeting. Fallback to uniqueid when referenceId is missing.
		seen_refs = set()
		meeting_notes: list[dict] = []
		for item in meeting_notes_raw:
			# referenceId is now guaranteed to be on the top-level of the dict
			# from the to_milvus_dict() method on the MeetingNote class.
			ref = item.get("referenceId") or item.get("uniqueid")
			if ref not in seen_refs:
				seen_refs.add(ref)
				meeting_notes.append(item)

		# Apply offset after deduplication
		if offset > 0:
			meeting_notes = meeting_notes[offset:offset + limit] if offset < len(meeting_notes) else []
		
		return JSONResponse(
			status_code=200,
			content={
				"success": True,
				"meeting_notes": meeting_notes,
				"total": len(meeting_notes),
				"offset": offset,
				"limit": limit
			}
		)
		
	except Exception as e:
		print(f"Error fetching meeting notes: {e}")
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to fetch meeting notes")


@router.get("/get/{tenant_name}/{uniqueid}")
async def get_meeting_note(tenant_name: str, uniqueid: str):
	"""
	Get a single meeting note by its uniqueid
	"""
	try:
		# Get the meeting note from Milvus
		meeting_note = get_record_by_id(tenant_name, uniqueid)
		
		if not meeting_note:
			raise HTTPException(status_code=404, detail="Meeting note not found")
		
		# Verify it's actually a meeting note
		if meeting_note.get("recordType") != "meeting_note":
			raise HTTPException(status_code=404, detail="Record is not a meeting note")
		
		return JSONResponse(
			status_code=200,
			content={
				"success": True,
				"meeting_note": meeting_note
			}
		)
		
	except HTTPException:
		raise
	except Exception as e:
		print(f"Error fetching meeting note: {e}")
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to fetch meeting note")


# ---------------------------------------------------------------------------
# Hybrid search endpoint – combines vector similarity & keyword matching
# ---------------------------------------------------------------------------
@router.get("/search/{tenant_name}")
async def search_meeting_notes(tenant_name: str, q: str, limit: int = 50, similarity: float = 0.5):
	"""
	Hybrid search across meeting notes.

	This endpoint accepts a free-text *q* parameter which is:
	1. Embedded into a dense vector via the same embedding service used for
	   inserts.
	2. Executed as a hybrid search against the vector index **and** as a
	   keyword predicate on the ``title`` and ``content`` fields.

	Results are returned in descending order of similarity (lower distance →
	more relevant) and limited to *limit* items.
	"""
	try:
		# Constrain to meeting_note records only.
		filter_expr = 'recordType == "meeting_note"'

		results = query_by_hybrid_with_filter(
			tenant_name=tenant_name,
			query=q,
			filter_expr=filter_expr,
			top_k=limit,
			similarity_setting=similarity,
			include_vector=False,
		)

		raw_results = results.get("results", [])

		# Deduplicate search results on referenceId retaining highest-ranked (first)
		seen_refs = set()
		deduped_results: list[dict] = []
		for item in raw_results:
			ref = item.get("referenceId") or item.get("uniqueid")
			if ref not in seen_refs:
				seen_refs.add(ref)
				deduped_results.append(item)

		return JSONResponse(
			status_code=200,
			content={
				"success": True,
				"query": q,
				"results": deduped_results,
				"limit": limit,
			}
		)
	except Exception as e:
		print(f"Error performing hybrid search on meeting notes: {e}")
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to search meeting notes")


@router.delete("/delete")
async def delete_meeting_note(delete_meeting_note_in: DeleteMeetingNoteIn):
	"""
	Delete a meeting note by its uniqueid
	"""
	try:
		delete_record(delete_meeting_note_in.tenant_name, delete_meeting_note_in.unique_id)
		print("Deleted meeting note: ", delete_meeting_note_in.unique_id)
		
		return JSONResponse(
			status_code=200,
			content={
				"success": True,
				"message": "Meeting note deleted successfully",
				"uniqueid": delete_meeting_note_in.unique_id
			}
		)
		
	except Exception as e:
		print(f"Error deleting meeting note: {e}")
		traceback.print_exc()
		raise HTTPException(status_code=500, detail="Failed to delete meeting note")

