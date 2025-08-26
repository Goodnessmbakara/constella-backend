from datetime import datetime
import json
import asyncio  # <- for task management/cancellation support
from ai.orb.prompts import (get_execute_screen_system_prompt, get_orb_system_prompt,
	orb_system_prompt, parse_orb_frontend_messages)
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
from ai.ai_api import (openai_tool_calls, stream_anthropic_response,
	stream_google_response, stream_openai_response)
from fastapi import WebSocket, WebSocketDisconnect
from ai.horizon.assist_ai import get_horizon_system_prompt, parse_horizon_frontend_messages, convert_anthropic_to_google
from ai.orb.tools_openai import get_orb_tools
from ai.orb.llms.openrouter import stream_openrouter_response, openrouter_parse_orb_frontend_messages  # NEW IMPORT
from ai.orb.tools_cerebras import get_cerebras_orb_tools, get_screen_execute_cerebras_orb_tools
from ai.orb.debug import write_messages_to_file



router = APIRouter(
	prefix="/horizon/orb",
	tags=["horizon_orb"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)


@router.websocket("/orb-ws")
async def websocket_orb_endpoint(websocket: WebSocket):
	await websocket.accept()
# ---------- NEW IMPLEMENTATION WITH CANCELLATION SUPPORT ----------
	try:
		print('HORIZON ASSIST WS RECEIVED')

		# Task that handles the current generation (if any)
		current_generation_task: asyncio.Task | None = None

		while True:
			# -----------------------------
			# Wait for incoming message
			# -----------------------------
			try:
				req = await websocket.receive_json()
			except Exception as e:
				print("Orb receiving JSON payload over websocket:", e)
				try:
					await websocket.send_text("|ERROR:INVALID_JSON|")
				except Exception:
					pass
				break

			# Handle init handshake
			if 'init' in req:
				await websocket.send_text('|INIT|')
				continue

			# Handle explicit cancel from the client
			if req.get('type') == 'cancel':
				if current_generation_task and not current_generation_task.done():
					current_generation_task.cancel()
					await websocket.send_text('|CANCELLED|')
				continue

			# If another generation is already running, cancel it before starting a new one
			if current_generation_task and not current_generation_task.done():
				current_generation_task.cancel()

			# Spawn a new task to handle this generation so we can listen for future cancel msgs
			current_generation_task = asyncio.create_task(_handle_orb_generation(req, websocket))
	
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
		try:
			await websocket.close()
		except Exception:
			pass


# ------------------------------------------------------------------
# Helper coroutine that performs the OpenAI streaming and forwards it
# ------------------------------------------------------------------

async def _handle_orb_generation(req: dict, websocket: WebSocket):
	"""Stream a single OpenAI generation to the websocket.

	This runs in its own task so that it can be cancelled when the
	client sends a `{ "type": "cancel" }` message. When cancelled we
	ensure the OpenAI stream is also closed to free resources.
	"""
	stream = None
	try:
		# Extract options
		image_bytes = req.get('imageBytes')
		auto_execute = req.get('auto_execute', True)
		about_user = req.get('about_user', "")
		user_instructions = req.get('user_instructions', "")
		user_mode = req.get('user_mode', "")
		orb_tapped_to_hold = req.get('orb_tapped_to_hold', False)
		from_suggestion = req.get('from_suggestion', False)

		# write_messages_to_file(req['messages'])

		messages = parse_orb_frontend_messages(
			req['messages'],
			model="openai",
			image_bytes=image_bytes,
			from_suggestion=from_suggestion
		)

		# -------- Call OpenAI and begin streaming --------
		stream = openai_tool_calls(
			messages,
			max_tokens=req.get('max_tokens', 1024),
			system_prompt=get_orb_system_prompt(messages, about_user=about_user, user_instructions=user_instructions, user_mode=user_mode, orb_tapped_to_hold=orb_tapped_to_hold),
			tool_calls=get_orb_tools(auto_execute=auto_execute),
			stream=True,
			model='gpt-4o-2024-08-06' if not orb_tapped_to_hold else 'gpt-4.1-mini-2025-04-14'
		)

		tool_call_chunks: dict[int, dict] = {}
		has_tool_call = False
		has_streamed_normal_text = False

		for event in stream:
			# Yield control regularly so cancellation can propagate
			await asyncio.sleep(0)
			etype = getattr(event, "type", "")

			# 1. Plain text deltas
			if etype == "response.output_text.delta" and not has_tool_call:
				await websocket.send_text(getattr(event, "delta", ""))
				has_streamed_normal_text = True
				continue

			if has_streamed_normal_text:
				continue

			# Helper to safely extract dicts
			item = getattr(event, "item", None)
			item_type = ""
			if item is not None:
				item_type = getattr(item, "type", "") or (item.get("type") if isinstance(item, dict) else "")

			# a) new function call added
			if etype == "response.output_item.added" and item_type == "function_call":
				has_tool_call = True
				idx = getattr(event, "output_index", 0)
				chunk = tool_call_chunks.setdefault(idx, {
					"id": getattr(item, "id", "") if not isinstance(item, dict) else item.get("id", ""),
					"type": "tool_call",
					"function": {
						"name": getattr(item, "name", "") if not isinstance(item, dict) else item.get("name", ""),
						"arguments": ""
					}
				})
				continue

			# c) final full arguments string
			if etype == "response.function_call_arguments.done":
				idx = getattr(event, "output_index", 0)
				chunk = tool_call_chunks.setdefault(idx, {
					"id": getattr(event, "item_id", ""),
					"type": "tool_call",
					"function": {"name": "", "arguments": ""}
				})
				chunk["function"]["arguments"] = getattr(event, "arguments", chunk["function"].get("arguments", ""))
				break

			# 3. legacy events
			if etype in ("response.tool_calls", "response.tool_calls.delta"):
				has_tool_call = True
				for tc in getattr(event, "tool_calls", []):
					idx = getattr(tc, "index", 0)
					chunk = tool_call_chunks.setdefault(idx, {"id": "", "type": "tool_call", "function": {"name": "", "arguments": ""}})
					if tc.id:
						chunk["id"] = tc.id
					if tc.function.name:
						chunk["function"]["name"] = tc.function.name
					if tc.function.arguments:
						chunk["function"]["arguments"] += tc.function.arguments
				continue

		# After stream finishes
		if has_tool_call:
			tool_calls_response = list(tool_call_chunks.values())
			print('forwarding tool call: ', tool_calls_response)
			await websocket.send_json({"tool_calls": tool_calls_response})

	except asyncio.CancelledError:
		# Task was cancelled by client – ensure OpenAI streaming is closed
		if stream is not None:
			try:
				stream.close()  # openai-python ≥1.14 supports this
			except Exception:
				pass
		raise
	except Exception as e:
		print('Error in stream orb response: ', e)
		# Try anthropic as a backup if OpenAI fails (only if not cancelled)
		try:
			messages = parse_horizon_frontend_messages(
				req['messages'],
				model="anthropic",
				image_bytes=None
			)
			for word in stream_anthropic_response(
				messages,
				max_tokens=req.get('max_tokens', 1024),
				system_prompt=get_horizon_system_prompt(messages)
			):
				await websocket.send_text(word)
		except Exception as backup_e:
			print('Backup anthropic stream failed:', backup_e)

	finally:
		# Just in case ensure stream closed
		if stream is not None:
			try:
				stream.close()
			except Exception:
				pass


@router.websocket("/orb-ws-screen-execute")
async def websocket_orb_screen_execute_endpoint(websocket: WebSocket):
	await websocket.accept()
	
	# Store goal and metric tracking at websocket level
	goal = None
	metric_to_track = None
	description_of_screen = None
	metric_progress_history = []
	actions_done: list[dict] = []  # Track actions executed so far
	messages = []
	
	try:
		print('HORIZON ORB SCREEN EXECUTE WS RECEIVED')

		while True:
			# Receive request from the WebSocket connection and handle malformed JSON gracefully
			try:
				req = await websocket.receive_json()
			except Exception as e:
				print("Orb Ws Screen Execute receiving JSON payload over websocket:", e)
				try:
					await websocket.send_text("|ERROR:INVALID_JSON|")
				except Exception:
					pass
				break

			# If init key in request, then send init message and store goal/metric
			if 'init' in req:
				# Store goal and metric_to_track from initial connection
				goal = req.get('goal')
				metric_to_track = req.get('metric_to_track')
				description_of_screen = req.get('description_of_screen')
				
				if goal:
					print(f'Goal set: {goal}')
				if metric_to_track:
					print(f'Metric to track: {metric_to_track}')
				if description_of_screen:
					print(f'Screen description: {description_of_screen}')
				
				print('INIT MESSAGE RECEIVED')

			try:
				# Extra arguments passed to each tool implementation
				extra_args = {
					"websocket_tool_io": websocket,
				}

				# Extract image_bytes from top-level request
				image_bytes = req.get('imageBytes')

				# Update actions_done list if present in the request
				action_type = req.get('actionDone') or req.get('action_done')
				action_data = req.get('actionData') or req.get('action_data')
				if action_type:
					actions_done.append({"action_type": action_type, "action_data": action_data or ""})
					# Keep last 20 actions
					if len(actions_done) > 20:
						actions_done = actions_done[-20:]

				# -------------------------------------------------
				# 1. Metric evaluation BEFORE main decision
				# -------------------------------------------------
				latest_metric_evaluation = None
				if metric_to_track:
					try:
						metric_eval_messages = [
							{
								"role": "user",
								"content": f"""
								You are a progress evaluator AI. Based on the goal, metric, and actions completed so far, assess current progress toward the metric.
								
								Goal: {goal or 'Not specified'}
								Metric to Track: {metric_to_track}
								Description of screen: {description_of_screen}
								Recent Actions: {actions_done[-5:]}
								Previous Progress: {metric_progress_history[-1]['evaluation'] if metric_progress_history else 'No previous progress'}
								OCR of list of strings on the screen: {req.get('ocr_results')}
								
								Return your assessment in the format "PROGRESS: [score] - [assessment]" (score 0-100, 1 sentence assessment).
								"""
							}
						]

						latest_metric_evaluation = await stream_openrouter_response(
							messages=metric_eval_messages,
							extra_args={},
							system_prompt="You are a progress evaluator. Provide concise metric assessments.",
							tools=None
						)

						if latest_metric_evaluation and "PROGRESS:" in latest_metric_evaluation:
							timestamp = datetime.now().isoformat()
							metric_progress_history.append({
								"timestamp": timestamp,
								"evaluation": latest_metric_evaluation.strip(),
							})
							# keep last 10
							if len(metric_progress_history) > 10:
								metric_progress_history = metric_progress_history[-10:]

							# Send progress update to client
							await websocket.send_text(f"|METRIC_PROGRESS:|{latest_metric_evaluation}")
					except Exception as e:
						print(f'Error evaluating metric progress: {e}')

				# -------------------------------------------------
				# 2. Build extra prompt with latest info
				# -------------------------------------------------
				extra_prompt_parts = []
				if goal:
					extra_prompt_parts.append(f"GOAL: {goal}")
				if metric_to_track:
					extra_prompt_parts.append(f"METRIC TO TRACK: {metric_to_track}")
				if description_of_screen:
					extra_prompt_parts.append(f"INITIAL SCREEN DESCRIPTION (to help decide what elements to interact with, may have changed): {description_of_screen}")
				if latest_metric_evaluation:
					extra_prompt_parts.append(f"LATEST METRIC EVALUATION: {latest_metric_evaluation.strip()}")
				if actions_done:
					extra_prompt_parts.append(f"ACTIONS DONE SO FAR (do not do them again): {actions_done}")
				
				if req.get('ocr_results'):
					extra_prompt_parts.append(f"The current OCR on the screen, a list of detected texts. When deciding an action to click, return one of the texts exactly from the list: {req.get('ocr_results')}")

				extra_prompt = "\n".join(extra_prompt_parts)

				# Add the extra prompt to the messages
				messages.append({
					"role": "user",
					"content": ""
				})

				
				print('\n\n')
				print('INPUT MESSAGES:')
				print(messages)
				print('\n\n')
				
				# -------------------------------------------------
				# 3. Parse messages & get main decision
				# -------------------------------------------------
				messages = openrouter_parse_orb_frontend_messages(
					messages,
					image_bytes=image_bytes,
					screen_execute_mode=True,
					extra_prompt=extra_prompt
				)

				message_resp = await stream_openrouter_response(
					messages=messages,
					extra_args=extra_args,
					system_prompt=get_execute_screen_system_prompt(),
					tools=get_screen_execute_cerebras_orb_tools(),
					multi_turn_mode=False,
					parallel_tool_calls=False
				)

				print("AI response: ", message_resp)

				if message_resp is None:
					message_resp = "Sorry, I couldn't generate a response at this time."
				
				messages.append({
					"role": "assistant",
					"content": message_resp
				})

				# await websocket.send_text("|TEXT_RESPONSE:|" + message_resp)
				# await websocket.send_text('|DONE_STREAMING|')

			except Exception as e:
				print('Error in orb-ws-screen-execute response: ', e)
				traceback.print_exc()
				try:
					await websocket.send_json({"error": str(e)})
				except Exception:
					pass

	except WebSocketDisconnect:
		pass
	except Exception as e:
		print('Error in horizon orb screen execute chat request: ', e)
		traceback.print_exc()
		try:
			await websocket.send_json({"error": str(e)})
		except Exception:
			pass
	finally:
		try:
			await websocket.close()
		except Exception:
			pass



@router.websocket("/orb-ws-fast")
async def websocket_orb_fast_endpoint(websocket: WebSocket):
	await websocket.accept()
	try:
		print('HORIZON ORB FAST WS RECEIVED')

		while True:
			# Receive request from the WebSocket connection and handle malformed JSON gracefully
			try:
				req = await websocket.receive_json()
			except Exception as e:
				print("Orb Ws Fast receiving JSON payload over websocket:", e)
				try:
					await websocket.send_text("|ERROR:INVALID_JSON|")
				except Exception:
					pass
				break

			# If init key in request, then send init message
			if 'init' in req:
				await websocket.send_text('|INIT|')
				continue

			try:
				# Extra arguments passed to each tool implementation
				extra_args = {
					"websocket_tool_io": websocket,
				}
				
				# Extract image_bytes from top-level request
				image_bytes = req.get('imageBytes')
				
				# Parse messages with OCR data, selected text, and image handling
				messages = openrouter_parse_orb_frontend_messages(
					req.get('messages', []), 
					image_bytes=image_bytes
				)


				# Call the Cerebras-backed OpenRouter helper
				message_resp = await stream_openrouter_response(
					messages=messages,
					extra_args=extra_args,
					system_prompt=orb_system_prompt,
					tools=get_cerebras_orb_tools(auto_execute=True)
				)

				if message_resp is None:
					message_resp = "Sorry, I couldn't generate a response at this time."

				await websocket.send_text("|TEXT_RESPONSE:|" + message_resp)
				# Completion signal
				await websocket.send_text('|DONE_STREAMING|')

			except Exception as e:
				print('Error in orb-ws-fast response: ', e)
				traceback.print_exc()
				try:
					await websocket.send_json({"error": str(e)})
				except Exception:
					pass

	except WebSocketDisconnect:
		pass
	except Exception as e:
		print('Error in horizon orb fast chat request: ', e)
		traceback.print_exc()
		try:
			await websocket.send_json({"error": str(e)})
		except Exception:
			pass
	finally:
		try:
			await websocket.close()
		except Exception:
			pass