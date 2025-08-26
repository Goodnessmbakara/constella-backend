import os
import asyncio
import json
import traceback
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ai.horizon.meeting_mode import MeetingAssistant
from ai.horizon.suggestions_mode import SuggestionsAssistant


router = APIRouter(
	prefix="/horizon/audio",
	tags=["horizon_orb"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)


@router.websocket("/transcribe-audio")
async def transcribe_audio_ws(websocket: WebSocket):
	"""Bidirectional WebSocket that streams raw PCM audio to Deepgram STT and relays
	interim/final transcripts back to the caller.

	Client workflow:
	1. Open WebSocket connection to this endpoint.
	2. Stream 16-kHz mono `linear16` audio frames as *binary* messages (ideally ~100-200 ms chunks).
	3. Optionally send the text command `finalize` when the user stops speaking and `done` to fully
	   close the upstream Deepgram session.
	4. Receive JSON objects from the server containing Deepgram transcript events (interim + final).
	   The payloads are forwarded verbatim from Deepgram.
	"""
	try:
		await websocket.accept()

		api_key = os.getenv("DEEPGRAM_API_KEY")
		if not api_key:
			await websocket.close(code=1011)  # Internal error
			return

		ws_params = {
			"model": "nova-2",
			"encoding": "opus",
			"sample_rate": "16000",
			"channels": "1",
			"interim_results": "true",
			"smart_format": "true",
			"diarize": "true",
			"language": "en",
			"punctuate": "true",
		}

		param_str = "&".join(f"{k}={v}" for k, v in ws_params.items())
		deepgram_uri = f"wss://api.deepgram.com/v1/listen?{param_str}"

		async def bridge_upstream():
			"""Forward audio & control messages from client → Deepgram."""
			try:
				while True:
					try:
						frame = await websocket.receive()
					except (WebSocketDisconnect, RuntimeError):
						break

					if frame.get("bytes"):
						await deepgram_ws.send(frame["bytes"])

					elif frame.get("text"):
						cmd = frame["text"].strip()
						if cmd == "finalize":
							await deepgram_ws.send_json({"type": "CloseStream"})
						elif cmd == "done":
							await deepgram_ws.close()
			except (WebSocketDisconnect, asyncio.CancelledError):
				# Gracefully close upstream session
				try:
					await deepgram_ws.close()
				except Exception:
					pass

		async def bridge_downstream():
			"""Forward transcripts from Deepgram → client."""
			try:
				async for msg in deepgram_ws:
					# Deepgram only sends JSON text frames for STT responses
					if isinstance(msg, str):
						try:
							await websocket.send_text(msg)
						except (WebSocketDisconnect, RuntimeError):
							break
						except Exception:
							break
			except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
				pass

		# Connect to Deepgram STT WebSocket
		headers = {'Authorization': f"Token {api_key}"}
		try:
			async with websockets.connect(
				deepgram_uri,
				additional_headers=headers,
				ping_interval=10,
				ping_timeout=5,
			) as deepgram_ws:
				# Bidirectional streaming: run tasks concurrently
				await asyncio.gather(bridge_upstream(), bridge_downstream())
		except Exception as e:
			# Bubble error back to client then close
			try:
				await websocket.send_json({"type": "error", "message": str(e)})
			except RuntimeError:
				pass
			try:
				await websocket.close(code=1011)
			except RuntimeError:
				pass
	except Exception:
		await websocket.close(code=1011)


@router.websocket("/transcribe-audio-system")
async def transcribe_audio_ws(websocket: WebSocket):
	"""Bidirectional WebSocket that streams raw PCM audio to Deepgram STT and relays
	interim/final transcripts back to the caller.

	Client workflow:
	1. Open WebSocket connection to this endpoint.
	2. Stream 16-kHz mono `linear16` audio frames as *binary* messages (ideally ~100-200 ms chunks).
	3. Optionally send the text command `finalize` when the user stops speaking and `done` to fully
	   close the upstream Deepgram session.
	4. Receive JSON objects from the server containing Deepgram transcript events (interim + final).
	   The payloads are forwarded verbatim from Deepgram.
	"""
	try:
		print('Transcribe audio system')
		await websocket.accept()

		api_key = os.getenv("DEEPGRAM_API_KEY")
		if not api_key:
			await websocket.close(code=1011)  # Internal error
			return

		ws_params = {
			"model": "nova-2",
			"encoding": "opus",
			"sample_rate": "16000",
			"channels": "1",
			"interim_results": "true",
			"smart_format": "true",
			"diarize": "true",
			"language": "en",
			"punctuate": "true",
		}

		param_str = "&".join(f"{k}={v}" for k, v in ws_params.items())
		deepgram_uri = f"wss://api.deepgram.com/v1/listen?{param_str}"

		async def bridge_upstream():
			"""Forward audio & control messages from client → Deepgram."""
			try:
				while True:
					try:
						frame = await websocket.receive()
					except (WebSocketDisconnect, RuntimeError):
						break

					if frame.get("bytes"):
						await deepgram_ws.send(frame["bytes"])

					elif frame.get("text"):
						cmd = frame["text"].strip()
						if cmd == "finalize":
							await deepgram_ws.send_json({"type": "CloseStream"})
						elif cmd == "done":
							await deepgram_ws.close()
			except (WebSocketDisconnect, asyncio.CancelledError):
				# Gracefully close upstream session
				try:
					await deepgram_ws.close()
				except Exception:
					pass

		async def bridge_downstream():
			"""Forward transcripts from Deepgram → client."""
			try:
				async for msg in deepgram_ws:
					# Deepgram only sends JSON text frames for STT responses
					if isinstance(msg, str):
						try:
							print('Sending msg: ', msg)
							await websocket.send_text(msg)
						except (WebSocketDisconnect, RuntimeError):
							break
						except Exception:
							break
			except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
				pass

		# Connect to Deepgram STT WebSocket
		headers = {'Authorization': f"Token {api_key}"}
		try:
			async with websockets.connect(
				deepgram_uri,
				additional_headers=headers,
				ping_interval=10,
				ping_timeout=5,
			) as deepgram_ws:
				# Bidirectional streaming: run tasks concurrently
				await asyncio.gather(bridge_upstream(), bridge_downstream())
		except Exception as e:
			# Bubble error back to client then close
			try:
				await websocket.send_json({"type": "error", "message": str(e)})
			except RuntimeError:
				pass
			try:
				await websocket.close(code=1011)
			except RuntimeError:
				pass
	except Exception:
		await websocket.close(code=1011)

@router.websocket("/text-to-speech")
async def text_to_speech_ws(websocket: WebSocket):
	"""Bidirectional WebSocket that streams text to ElevenLabs TTS and relays
	the synthesized audio back to the caller.

	Client workflow:
	1. Open a WebSocket connection to this endpoint.
	2. Send text to be synthesized as a JSON string. Example:
	   '{"text": "Hello world ", "try_trigger_generation": true}'
	   Note: The trailing space helps trigger audio generation more quickly.
	3. To finalize the stream, send a JSON object with an empty text string:
	   '{"text": ""}'
	4. Receive JSON objects from the server containing Base64-encoded audio chunks.
	   The client is responsible for decoding the Base64 audio and playing it.
	   Payload format: {"audio": "...", "isFinal": ...}
	"""

	VOICE_ID = "21m00Tcm4TlvDq8ikWAM" 
	MODEL_ID = "eleven_turbo_v2" # or "eleven_turbo_v2", etc.

	try:
		await websocket.accept()

		api_key = os.getenv("ELEVENLABS_API_KEY")
		if not api_key:
			print("Error: ELEVENLABS_API_KEY environment variable not set.")
			await websocket.close(code=1011)  # Internal error
			return

		# Build the ElevenLabs WebSocket URI
		elevenlabs_uri = (
			f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input"
			f"?model_id={MODEL_ID}"
		)

		async def forward_text_to_elevenlabs():
			"""
			Forwards text messages from the client to ElevenLabs.
			It acts as a simple relay, forwarding the raw text received.
			"""
			try:
				while True:
					# THIS IS THE FIX: Receive raw text and forward it directly.
					# The client must send a JSON-formatted string.
					text_data = await websocket.receive_text()
					await elevenlabs_ws.send(text_data)
			except (WebSocketDisconnect, asyncio.CancelledError):
				# This is a clean disconnect, do nothing.
				pass
			except Exception as e:
				print(f"Error in forward_text_to_elevenlabs: {e}")

		async def forward_audio_to_client():
			"""Forwards synthesized audio from ElevenLabs to the client."""
			try:
				# Receive a message (audio data) from ElevenLabs
				async for msg in elevenlabs_ws:
					if isinstance(msg, str):
						try:
							# Forward the received message (JSON) directly to the client
							await websocket.send_text(msg)
						except (WebSocketDisconnect, RuntimeError):
							break  # Break the loop if the client disconnects
			except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
				# Do nothing if the connection was closed normally or the task was cancelled
				pass
			except Exception as e:
				print(f"Error in forward_audio_to_client: {e}")

		# Connect to the ElevenLabs TTS WebSocket
		try:
			async with websockets.connect(
				elevenlabs_uri,
				ping_interval=10,
				ping_timeout=5,
			) as elevenlabs_ws:
				
				# 1. Send the authentication message first
				auth_payload = {
					"text": " ",
					"xi_api_key": api_key,
					"voice_settings": {
						"stability": 0.5,
						"similarity_boost": 0.75
					}
				}
				await elevenlabs_ws.send(json.dumps(auth_payload))

				# 2. Run the bidirectional streaming tasks concurrently
				await asyncio.gather(
					forward_text_to_elevenlabs(), 
					forward_audio_to_client()
				)

		except Exception as e:
			# Notify the client of connection errors, etc.
			print(f"Could not connect to ElevenLabs: {e}")
			try:
				await websocket.send_json({"type": "error", "message": str(e)})
			except RuntimeError:
				pass
			try:
				await websocket.close(code=1011)
			except RuntimeError:
				pass

	except Exception as e:
		print(f"An unexpected error occurred: {e}")
		try:
			# Close the connection if an unexpected error occurs
			await websocket.close(code=1011)
		except RuntimeError:
			pass


@router.websocket("/meeting-ws")
async def meeting_ws(websocket: WebSocket):
	"""WebSocket that receives the growing transcript (as a JSON list) and
	returns AI meeting-assistant tool-call suggestions in real time.

	Client workflow:
	1. Open WebSocket connection to this endpoint.
	2. Repeatedly send *text* messages containing a JSON-encoded list of objects,
	   e.g. [{"isUser": "hello"}, {"isSystem": "hi there"}, ...]. The list must
	   include the full transcript so far.
	3. The server analyses only the new entries since the previous message and
	   may send back JSON payloads representing tool calls:
	   {
		 "type": "meeting_tool_call",
		 "name": "create_suggestion" | "create_meeting_note_topic" | ... | "pass",
		 "arguments": { ... }
	   }
	4. When finished, simply close the WebSocket from the client side.
	"""

	await websocket.accept()

	assistant = MeetingAssistant()

	try:
		while True:
			try:
				data = await websocket.receive_text()
			except WebSocketDisconnect:
				break
			except Exception:
				break


			# Parse incoming JSON list
			try:
				transcript_items = json.loads(data)
			except json.JSONDecodeError:
				# Ignore malformed input
				continue	
			
			# Hand off to assistant (fire-and-forget)
			asyncio.create_task(assistant.handle_transcript_list(transcript_items, websocket))

	except (asyncio.CancelledError, WebSocketDisconnect):
		pass
	finally:
		try:
			await websocket.close()
		except Exception:
			pass 


@router.websocket("/suggestion-ws")
async def meeting_ws(websocket: WebSocket):
	"""WebSocket that receives the growing transcript (as a JSON list) and
	returns AI suggestions in real time.

	Client workflow:
	1. Open WebSocket connection to this endpoint.
	2. Repeatedly send *text* messages containing a JSON-encoded list of objects,
	   e.g. [{"isUser": "hello"}, {"isSystem": "hi there"}, ...]. The list must
	   include the full transcript so far.
	3. The server analyses only the new entries since the previous message and
	   may send back JSON payloads representing tool calls:
	   {
		 "type": "meeting_tool_call",
		 "name": "create_suggestion" | "create_meeting_note_topic" | ... | "pass",
		 "arguments": { ... }
	   }
	4. When finished, simply close the WebSocket from the client side.
	"""

	await websocket.accept()

	assistant = SuggestionsAssistant()

	try:
		while True:
			try:
				data = await websocket.receive_text()
			except WebSocketDisconnect:
				break
			except Exception:
				break

			# Parse incoming JSON list
			try:
				transcript_items = json.loads(data)
			except json.JSONDecodeError:
				# Ignore malformed input
				continue

			
			# Hand off to assistant (fire-and-forget)
			asyncio.create_task(assistant.handle_transcript_list(transcript_items, websocket))

	except (asyncio.CancelledError, WebSocketDisconnect):
		pass
	finally:
		try:
			await websocket.close()
		except Exception:
			pass 