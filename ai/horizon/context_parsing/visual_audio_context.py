import asyncio
import json
import logging
from typing import List, Dict, Any, Optional

from ai.ai_api import openai_tool_calls
from ai.orb.prompts import get_custom_prompt

# ---------------------------------------------------------------------------
# Shared configuration
# ---------------------------------------------------------------------------
# If the number of NEW words detected in the last `LAST_TRANSCRIPT_ITEMS` items of
# `full_transcript` exceeds this threshold, the assistant will run the analysis.
WORD_DIFF_THRESHOLD = 20  # Default threshold; can be overridden per assistant

# ---------------------------------------------------------------------------
# Helper functions (currently stubs)
# ---------------------------------------------------------------------------

def extract_context_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
	"""Extract additional screen / audio context from a payload.

	This is currently a placeholder so that other modules can safely import it.
	The implementation can be filled in later without touching the assistant
	classes.
	"""
	return {}


# ---------------------------------------------------------------------------
# General assistant implementation
# ---------------------------------------------------------------------------

class GeneralScreenAssistant:
	"""Stateful helper that builds the running transcript and asynchronously
	invokes the OpenAI model to generate tool-call suggestions.

	Concrete assistants (e.g. MeetingAssistant, SuggestionsAssistant) should
	subclass this and *only* provide their custom `system_prompt` and
	`tool_calls` via the constructor.
	"""

	def __init__(
		self,
		*,
		system_prompt: str,
		tool_calls: List[Dict[str, Any]],
		word_diff_threshold: int = WORD_DIFF_THRESHOLD,
		include_suggestions: bool = False,
		pass_ocr_to_prompt: bool = True, # by default pass ocr (but watch_screen can toggle it on / off)
		max_tokens: int = 300,
	):
		self.system_prompt = system_prompt
		self.tool_calls = tool_calls
		self._word_diff_threshold = word_diff_threshold
		self._include_suggestions = include_suggestions
		self._pass_ocr_to_prompt = pass_ocr_to_prompt  # NEW: control inclusion of OCR text
		self._max_tokens = max_tokens
		self._lock = asyncio.Lock()
		self._last_full_transcript_text: str = ""

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	async def handle_transcript_list(self, items: list, websocket):
		"""Entry point – process an incoming transcript list.

		The `items` payload is expected to be a *list* where the first element
		must be a dict containing at least a `full_transcript` key. This is the
		structure produced by the Horizon client.
		"""
		if (
			not isinstance(items, list)
			or not items
			or not isinstance(items[0], dict)
			or "full_transcript" not in items[0]
		):
			return  # Ignore malformed payloads

		await self._handle_structured_payload(items, websocket)

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------

	async def _handle_structured_payload(self, items: list, websocket) -> None:
		"""Process the structured transcript payload and emit tool calls."""

		first_item = items[0]
		full_transcript_items = first_item.get("full_transcript", [])
		notes = first_item.get("notes", [])
		ocr_text = first_item.get("ocr", "")
		triggered_by_clicks = bool(first_item.get("triggered_by_clicks", False))
		raw_suggestions = first_item.get("suggestions", [])
		suggestions = raw_suggestions if self._include_suggestions else None
		# NEW: Extract user personalization data
		about_user = first_item.get("about_user", "")
		user_instructions = first_item.get("user_instructions", "")
		user_mode = first_item.get("user_mode", "")
		# NEW: Extract watch_screen preference
		watch_screen = bool(first_item.get("watch_screen", False))

		# --- 1. Convert the full transcript to a single string ---
		current_full_text_parts = []
		for itm in full_transcript_items:
			if isinstance(itm, dict):
				current_full_text_parts.append(itm.get("text", ""))
			else:
				current_full_text_parts.append(str(itm))
		current_full_text = " ".join(p.strip() for p in current_full_text_parts if p).strip()

		# --- 2. Find what's new since the last run ---
		new_text = ""
		previous_transcript_str = self._last_full_transcript_text
		if current_full_text.startswith(previous_transcript_str):
			new_text = current_full_text[len(previous_transcript_str):].strip()
		elif current_full_text:
			# Transcript has diverged (e.g. corrections) – treat whole text as new.
			new_text = current_full_text
			previous_transcript_str = ""

		# --- 3. Check for significant change ---
		word_count = len(new_text.split())
		significant_change = word_count >= self._word_diff_threshold

		if not (significant_change or triggered_by_clicks):
			return  # Nothing meaningful to do yet

		async with self._lock:
			# Update cache to prevent re-processing the same text the next time
			self._last_full_transcript_text = current_full_text

		# --- 4. Run the blocking model call on a thread pool executor ---
		loop = asyncio.get_running_loop()
		tool_calls = await loop.run_in_executor(
			None,
			self._analyse_sentence_sync,
			previous_transcript_str,
			new_text,
			notes,
			ocr_text,
			suggestions,
			triggered_by_clicks,
			about_user,
			user_instructions,
			user_mode,
			watch_screen,
		)

		# --- 5. Forward tool calls back to the client ---
		for call in tool_calls:
			try:
				print("TOOL CALL NAME:", call["name"])
				response = {
					"type": "meeting_tool_call",
					"name": call["name"],
					"arguments": call["arguments"],
				}
				await websocket.send_json(response)
			except Exception:
				logging.exception("Failed to send assistant tool call")

	# ------------------------------------------------------------------
	# Synchronous helpers (run in executor)
	# ------------------------------------------------------------------

	def _analyse_sentence_sync(
		self,
		previous_transcript: str,
		new_sentence: str,
		notes: Optional[List[Any]] = None,
		ocr_text: str = "",
		suggestions: Optional[List[Any]] = None,
		triggered_by_clicks: bool = False,
		about_user: str = "",
		user_instructions: str = "",
		user_mode: str = "",
		watch_screen: bool = False,
	) -> List[Dict[str, Any]]:
		"""Call the OpenAI API synchronously and extract any tool calls."""

		notes = notes or []  # normalise default

		payload_dict = {
			"old_transcript": previous_transcript,
			"new_text": new_sentence,
			"notes": notes,
			"triggered_by_clicks": triggered_by_clicks,
		}

		# Include OCR text only if BOTH watch_screen is True AND pass_ocr_to_prompt is enabled
		if self._pass_ocr_to_prompt and watch_screen:
			payload_dict["user_screen_ocr"] = ocr_text

		if suggestions is not None:
			payload_dict["existing_suggestions"] = suggestions
			print("EXISTING SUGGESTIONS:", suggestions)

		user_payload = json.dumps(payload_dict)

		messages = [{"role": "user", "content": user_payload}]

		# --------------------------------------------------
		# Append custom prompt to the system prompt if provided
		# --------------------------------------------------
		system_prompt = self.system_prompt
		custom_prompt = get_custom_prompt(about_user, user_instructions, user_mode)
		if custom_prompt:
			system_prompt = system_prompt + "\n" + custom_prompt

		response = openai_tool_calls(
			messages=messages,
			system_prompt=system_prompt,
			max_tokens=self._max_tokens,
			tool_calls=self.tool_calls,
			model='gpt-4o-mini-2024-07-18'
		)

		if not response:
			return []

		try:
			# ----------------------------------------------
			# UPDATED PARSING FOR OPENAI "responses" LIBRARY
			# ----------------------------------------------
			output_messages = getattr(response, "output", None)
			if output_messages is None and isinstance(response, dict):
				output_messages = response.get("output")

			if not output_messages:
				return []

			results = []
			for msg in output_messages:
				msg_type = getattr(msg, "type", None) or (msg.get("type") if isinstance(msg, dict) else None)
				if msg_type != "function_call":
					continue

				func_name = getattr(msg, "name", None) or (msg.get("name") if isinstance(msg, dict) else None)
				args_payload = getattr(msg, "arguments", None) or (msg.get("arguments") if isinstance(msg, dict) else None)

				if isinstance(args_payload, str):
					try:
						args_dict = json.loads(args_payload)
					except Exception:
						args_dict = {"raw": args_payload}
				elif isinstance(args_payload, dict):
					args_dict = args_payload
				else:
					args_dict = {}

				results.append({
					"name": func_name,
					"arguments": args_dict,
				})

			return results
		except Exception:
			logging.exception("Error parsing assistant response")
		return []
