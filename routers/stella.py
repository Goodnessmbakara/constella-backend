from fastapi import APIRouter, WebSocketDisconnect, HTTPException, Request, WebSocket
import base64
import time
from pydantic import BaseModel, HttpUrl
import requests
import json
from typing import List, Dict, Optional
from ai.stella.prompts import get_system_prompt
import jwt
import os
from db.models.constella.constella_shared_view import ConstellaSharedView
from fastapi.responses import JSONResponse
import traceback
from db.models.constella.frontend.node import Node
from db.models.constella.frontend.edge import Edge
from db.models.constella.frontend.viewport import Viewport
from db.models.constella.frontend.message import Message
from ai.openai_setup import openai_client
from websockets.exceptions import ConnectionClosedError

from ai.stella.assistants.assistant import (assistant_instructions, assistant_tools,
	stella_openai_assistant, tool_capabilities_description)
from ai.stella.assistants.event_handler import stream_thread
import ai.stella.assistants.tools.tool_implementations as tool_impls
from db.models.constella.frontend.assistant_request import AssistantRequest
from ai.stella.assistants.utils import (format_stella_assistant_instructions,
	get_prompt_instructions_from_user_data_for_voice_convo, send_websocket_message_on_tool_call)
from ai.stella.assistants.tts import generate_speech
from ai.ai_api import create_google_request, create_new_google_request
from ai.stella.v2.cerebras_sonic import stream_cerebras_response, stream_openrouter_response

router = APIRouter(
	prefix="/stella",
	tags=["stella"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)


def parse_websocket_request(req: dict) -> AssistantRequest:
	"""Parse incoming websocket JSON request into AssistantRequest format"""
	return AssistantRequest(
		tenant_name=req['tenant_name'],
		user_message=req['user_message'],
		nodes=req['nodes'],
		edges=req['edges'],
		viewport=req['viewport'],
		convo_mode_enabled=req.get('convo_mode_enabled', True),
		messages=req.get('messages', []),
		tags=req.get('tags', [])
	)


async def safe_websocket_send(websocket: WebSocket, message_type: str, data):
	"""
	Safely send data over websocket with proper error handling.
	Returns True if successful, False if connection is closed.
	"""
	try:
		# Check if websocket is still connected
		if hasattr(websocket, 'client_state') and websocket.client_state.name != 'CONNECTED':
			return False
			
		if message_type == 'text':
			await websocket.send_text(data)
		elif message_type == 'json':
			await websocket.send_json(data)
		elif message_type == 'bytes':
			await websocket.send_bytes(data)
		return True
	except ConnectionClosedError:
		print(f"WebSocket connection closed while sending {message_type} message")
		return False
	except Exception as e:
		print(f"Error sending {message_type} message over websocket: {e}")
		return False


@router.websocket("/assistant")
async def websocket_assistant(websocket: WebSocket):
	await websocket.accept()
	try:
		# The thread of the message history
		thread = openai_client.beta.threads.create()

		while True:

			# Receive the request data as JSON
			req = await websocket.receive_json()

			# Parse the request data into our expected format
			request_data = parse_websocket_request(req)

			# Create a message in the thread from the user
			message = openai_client.beta.threads.messages.create(
				thread_id=thread.id,
				role="user",
				content=format_stella_assistant_instructions(request_data)
			)

			# Send initial confirmation
			if not await safe_websocket_send(websocket, 'text', '|INIT|'):
				break

			full_message = ""
			async def stream_response_back(response):
				await safe_websocket_send(websocket, 'text', response.text.value)

			# Arguments that get passed all the way to to the tool execution
			extra_args = {
				"tenant_name": request_data.tenant_name,
				"websocket_tool_io": websocket
			}

			# Send progress updates to the frontend
			def progress_callback(tool_call):
				pass


			response = stream_thread(thread=thread, assistant_id=stella_openai_assistant.id, content=request_data.user_message, tools=tool_impls, extra_args=extra_args, progress_callback=progress_callback)
			try:
				async for token in response:
					full_message += token.text.value
					if not await safe_websocket_send(websocket, 'text', token.text.value):
						break
			except Exception as stream_error:
				# Log the streaming error
				print(f"Error during streaming: {stream_error}")
				traceback.print_exc()
				
				# Send error message to frontend only if connection is still active
				error_msg = {
					"error": "Assistant run failed",
					"details": str(stream_error),
					"type": "stream_error"
				}
				await safe_websocket_send(websocket, 'json', error_msg)
				
				# Send completion signal even on error
				continue

			# Send completion signal
			await safe_websocket_send(websocket, 'text', '|DONE_STREAMING|')

	except WebSocketDisconnect:
		pass
	except ConnectionClosedError:
		print("WebSocket connection closed by client")
	except Exception as e:
		traceback.print_exc()
		# Only try to send error if connection might still be active
		await safe_websocket_send(websocket, 'json', {"error": str(e)})

# New Cerebras API for extremely fast responses
@router.websocket("/assistant-v2")
async def websocket_assistant(websocket: WebSocket):
	await websocket.accept()
	try:
		while True:

			# Receive the request data as JSON
			req = await websocket.receive_json()

			# Parse the request data into our expected format
			request_data = parse_websocket_request(req)

			# Send initial confirmation
			if not await safe_websocket_send(websocket, 'text', '|INIT|'):
				break

			full_message = ""
			async def stream_response_back(response):
				await websocket.send_text(response.text.value)

			# Arguments that get passed all the way to to the tool execution
			extra_args = {
				"tenant_name": request_data.tenant_name,
				"websocket_tool_io": websocket
			}

			# Add graph data to the last message
			request_data.messages[-1]['content'] = f"""User's request: {request_data.user_message}
				Nodes on user's graph:{request_data.nodes}
				Edges on user's graph:{request_data.edges}
				Viewport on user's graph:{request_data.viewport}
				All of user's tags:{request_data.tags}
				"""

			try:				
				message_resp = await stream_cerebras_response(messages=request_data.messages, extra_args=extra_args, system_prompt=assistant_instructions)

				if message_resp is None:
					message_resp = "Sorry, I couldn't generate a response at this time."
				
				if not await safe_websocket_send(websocket, 'text', "|TEXT_RESPONSE:|" + message_resp):
					break
				
				if request_data.convo_mode_enabled:
					if not await safe_websocket_send(websocket, 'text', '|AUDIO_START|'):
						break
					try:
						with openai_client.audio.speech.with_streaming_response.create(
							model="gpt-4o-mini-tts",
							voice="sage",
							response_format="mp3",
							input=message_resp[:4000], # Has max input of 2k tokens, so we'll do 4k chars as safety (~1k words)
						) as audio_response:
							for chunk in audio_response.iter_bytes(chunk_size=1024):
								if not await safe_websocket_send(websocket, 'bytes', chunk):
									break

						if not await safe_websocket_send(websocket, 'text', '|AUDIO_END|'):
							break
						# Send completion signal
						if not await safe_websocket_send(websocket, 'text', '|DONE_STREAMING|'):
							break
					except Exception as e:
						traceback.print_exc()
						await safe_websocket_send(websocket, 'text', '|AUDIO_ERROR|')

			except Exception as stream_error:
				# Log the streaming error
				print(f"Error during streaming: {stream_error}")
				traceback.print_exc()
				
				# Send error message to frontend only if connection is still active
				error_msg = {
					"error": "Assistant run failed",
					"details": str(stream_error),
					"type": "stream_error"
				}
				await safe_websocket_send(websocket, 'json', error_msg)
				
				# Send completion signal even on error
				continue

			# Send completion signal
			await safe_websocket_send(websocket, 'text', '|DONE_STREAMING|')

	except WebSocketDisconnect:
		pass
	except ConnectionClosedError:
		print("WebSocket connection closed by client")
	except Exception as e:
		traceback.print_exc()
		# Only try to send error if connection might still be active
		await safe_websocket_send(websocket, 'json', {"error": str(e)})

# New OpenRouter API for extremely fast responses using Cerebras via OpenRouter
@router.websocket("/assistant-v3")
async def websocket_assistant_openrouter(websocket: WebSocket):
	await websocket.accept()
	try:
		while True:

			# Receive the request data as JSON
			req = await websocket.receive_json()

			# Parse the request data into our expected format
			request_data = parse_websocket_request(req)

			# Send initial confirmation
			if not await safe_websocket_send(websocket, 'text', '|INIT|'):
				break

			full_message = ""
			async def stream_response_back(response):
				await websocket.send_text(response.text.value)

			# Arguments that get passed all the way to to the tool execution
			extra_args = {
				"tenant_name": request_data.tenant_name,
				"websocket_tool_io": websocket
			}

			# Add graph data to the last message
			request_data.messages[-1]['content'] = f"""User's request: {request_data.user_message}
				Nodes on user's graph:{request_data.nodes}
				Edges on user's graph:{request_data.edges}
				Viewport on user's graph:{request_data.viewport}
				All of user's tags:{request_data.tags}
				"""

			try:				
				message_resp = await stream_openrouter_response(messages=request_data.messages, extra_args=extra_args, system_prompt=assistant_instructions)

				if message_resp is None:
					message_resp = "Sorry, I couldn't generate a response at this time."
				
				if not await safe_websocket_send(websocket, 'text', "|TEXT_RESPONSE:|" + message_resp):
					break
				
				if request_data.convo_mode_enabled:
					if not await safe_websocket_send(websocket, 'text', '|AUDIO_START|'):
						break
					try:
						with openai_client.audio.speech.with_streaming_response.create(
							model="gpt-4o-mini-tts",
							voice="sage",
							response_format="mp3",
							input=message_resp[:4000], # Has max input of 2k tokens, so we'll do 4k chars as safety (~1k words,
						) as audio_response:
							for chunk in audio_response.iter_bytes(chunk_size=1024):
								if not await safe_websocket_send(websocket, 'bytes', chunk):
									break

						if not await safe_websocket_send(websocket, 'text', '|AUDIO_END|'):
							break
						# Send completion signal
						if not await safe_websocket_send(websocket, 'text', '|DONE_STREAMING|'):
							break
					except Exception as e:
						traceback.print_exc()
						await safe_websocket_send(websocket, 'text', '|AUDIO_ERROR|')

			except Exception as stream_error:
				# Log the streaming error
				print(f"Error during streaming: {stream_error}")
				traceback.print_exc()
				
				# Send error message to frontend only if connection is still active
				error_msg = {
					"error": "Assistant run failed",
					"details": str(stream_error),
					"type": "stream_error"
				}
				await safe_websocket_send(websocket, 'json', error_msg)
				
				# Send completion signal even on error
				continue

			# Send completion signal
			await safe_websocket_send(websocket, 'text', '|DONE_STREAMING|')

	except WebSocketDisconnect:
		pass
	except ConnectionClosedError:
		print("WebSocket connection closed by client")
	except Exception as e:
		traceback.print_exc()
		# Only try to send error if connection might still be active
		await safe_websocket_send(websocket, 'json', {"error": str(e)})


class InitialMessageAudioIn(BaseModel):
	user_message: str


@router.post("/initial-message-audio")
async def initial_message_audio(request: InitialMessageAudioIn):
	try:
		pass
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))



@router.post("/get-azure-speech-token")
async def get_speech_token():
	try:
		speech_key = os.getenv('AZURE_SPEECH_KEY', '')
		speech_region = "eastus"

		headers = {
			"Ocp-Apim-Subscription-Key": speech_key,
			"Content-Type": "application/x-www-form-urlencoded"
		}

		response = requests.post(
			f"https://{speech_region}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
			headers=headers
		)

		if response.status_code == 200:
			return {
				"token": response.text,
				"region": speech_region
			}
		else:
			raise HTTPException(
				status_code=401,
				detail="There was an error authorizing your speech key."
			)

	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe-audio")
async def transcribe_audio(request: Request):
	try:
		# Get JSON body
		body = await request.json()
		audio_base64 = body['audio']

		# Remove data URL prefix if present
		if 'base64,' in audio_base64:
			audio_base64 = audio_base64.split('base64,')[1]

		# Decode base64 to bytes
		audio_bytes = base64.b64decode(audio_base64)

		temp_file_path = '/tmp/audio.webm'

		# Write to temporary file
		with open('/tmp/audio.webm', 'wb') as f:
			f.write(audio_bytes)

		# Open file and transcribe with Whisper
		with open(temp_file_path, "rb") as audio_file:
			transcript = openai_client.audio.transcriptions.create(
				model="whisper-1",
				file=audio_file
			)

		# Clean up temp file
		os.unlink(temp_file_path)

		return {"text": transcript.text}

	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))


class WebsiteContentRequest(BaseModel):
    url: HttpUrl
    ignore_links: Optional[bool] = False
    max_length: Optional[int] = None
    tenant_name: Optional[str] = None

class GoogleSearchRequest(BaseModel):
    query: str
    results: Optional[int] = 5
    exactTerms: Optional[str] = None
    excludeTerms: Optional[str] = None
    tenant_name: Optional[str] = None

class FixJsonRequest(BaseModel):
    broken_json: str

# Define your FastAPI routes
@router.post("/get-website-content")
async def get_website_content(request: WebsiteContentRequest):
    result = await tool_impls.get_website_url_content(
        url=request.url,
        ignore_links=request.ignore_links,
        max_length=request.max_length,
        tenant_name=request.tenant_name
    )
    if "Error" in result:
        raise HTTPException(status_code=500, detail=result)
    return {"content": result}

@router.post("/google-search")
async def google_search_route(request: GoogleSearchRequest):
    result = await tool_impls.google_search(
        query=request.query,
        results=request.results,
        exactTerms=request.exactTerms,
        excludeTerms=request.excludeTerms,
        tenant_name=request.tenant_name
    )
    if result is None:
        raise HTTPException(status_code=500, detail="Error performing Google search")
    return {"results": result}

@router.post("/fix-json")
async def fix_json_route(request: FixJsonRequest):
    try:
        prompt = f"""Fix the following broken JSON and return only the corrected JSON without any explanation or additional text:

{request.broken_json}

Return only the valid JSON:"""

        response = create_new_google_request(prompt=prompt)
        
        if response:
            return {"fixed_json": response.strip()}
        else:
            raise HTTPException(status_code=500, detail="Failed to fix JSON")
            
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/voice-convo")
async def websocket_voice_convo(websocket: WebSocket):
	await websocket.accept()
	try:
		while True:
			# Receive the request data as JSON
			req = await websocket.receive_json()

			# Check if message_to_speak is provided
			message_to_speak = req.get('message_to_speak')
			
			if message_to_speak:
				# Direct message provided - skip Google request and go straight to audio
				response = message_to_speak
			else:
				# Parse the request data into our expected format
				request_data = parse_websocket_request(req)

				# Format the available tools into a readable string
				available_tools = []
				for tool in assistant_tools:
					tool_name = tool.get('function', {}).get('name', 'Unknown')
					tool_desc = tool.get('function', {}).get('description', 'No description')
					available_tools.append(f"- {tool_name}: {tool_desc}")
				
				tools_text = "\n".join(available_tools)

				# Create the prompt for Google Flash Lite
				google_prompt = f"""You are Stella, a human being in a conversation with the user regarding their knowledge base.
{tool_capabilities_description}
Never greet the user as you are already in the middle of the conversation. Do not introduce yourself at all but be specific related to the task and speak straight to the point as to what you are doing.
Mention specific details about the topic they mentioned, not generic things like "I am helping", "I am creating notes", etc. but make specific remarks conversationally on that topic.
This message is about always their notes and current graph view. This is the data regarding that:
{get_prompt_instructions_from_user_data_for_voice_convo(request_data)}
Look at their current graph view and the user's message and use that to make an interesting remark and tie in what you are doing to help them.
Do not mention specific details about what you are doing but rather on the content of what they asked in regards to their graph view as you do it.
Generate a single sentence user in the present continuous tense of what you are doing currently as if you are doing it.
Never say anything like "looking through the notes", this is already known.
However, if the user asks a general question or information request, then simply mention 'let me analyze', 'let me think', 'looking through', etc.
Your single sentence response in the user's language:
"""

				# Call Google Flash Lite for fast voice response
				try:
					response = create_new_google_request(
						prompt=google_prompt,
						model_name="gemini-2.5-flash-preview-04-17",
					)


					print('Response: ' + response)
					
					if not response:
						print("No response from Google Flash Lite")
						response = "Sorry, I couldn't generate a response at this time."
						
				except Exception as e:
					print(f"Error calling Google Flash Lite: {e}")
					response = "Error generating voice response."

			# Send the text response
			if not await safe_websocket_send(websocket, 'text', '|AUDIO RESPONSE:|' + response):
				break

			# Check if conversation mode is enabled (only check if not direct message or if provided in req)
			convo_mode_enabled = True  # Default value
			if not message_to_speak:
				convo_mode_enabled = request_data.convo_mode_enabled
			else:
				convo_mode_enabled = req.get('convo_mode_enabled', True)

			if convo_mode_enabled:
				print("Streaming audio")
				# Stream the audio data to the client
				if not await safe_websocket_send(websocket, 'text', '|AUDIO_START|'):
					break

				try:
					with openai_client.audio.speech.with_streaming_response.create(
						model="tts-1",
						voice="sage",
						response_format="mp3",
						input=response,
					) as audio_response:
						for chunk in audio_response.iter_bytes(chunk_size=1024):
							if not await safe_websocket_send(websocket, 'bytes', chunk):
								break

					if not await safe_websocket_send(websocket, 'text', '|AUDIO_END|'):
						break
				except Exception as audio_error:
					print(f"Error during audio streaming: {audio_error}")
					await safe_websocket_send(websocket, 'text', '|AUDIO_ERROR|')

			# Send completion signal
			await safe_websocket_send(websocket, 'text', '|DONE_STREAMING|')

	except WebSocketDisconnect:
		pass
	except ConnectionClosedError:
		print("WebSocket connection closed by client")
	except Exception as e:
		traceback.print_exc()
		# Only try to send error if connection might still be active
		await safe_websocket_send(websocket, 'json', {"error": str(e)})
