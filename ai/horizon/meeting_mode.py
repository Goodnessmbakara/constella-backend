import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
import re

from ai.ai_api import openai_tool_calls
from ai.horizon.context_parsing.visual_audio_context import GeneralScreenAssistant
from ai.orb.prompts import get_custom_prompt

# ---------------------------------------------------------------------------
# OpenAI function-calling tool definitions
# ---------------------------------------------------------------------------

create_meeting_note_topic_tool = {
	"type": "function",
	"name": "create_meeting_note_topic",
	"description": "Start a NEW meeting-note topic when the discussion shifts to something substantially different.",
	"parameters": {
		"type": "object",
		"properties": {
			"title": {
				"type": "string",
				"description": "The title for the new meeting-note topic."
			}
		},
		"required": ["title"],
		"additionalProperties": False,
	},
}

create_meeting_note_bulletpoint_tool = {
	"type": "function",
	"name": "create_meeting_note_bulletpoint",
	"description": "Add a specific, detailed bullet-point based on the transcript so far with relevant new information that has not been mentioned before.\n\n This new i",
	"parameters": {
		"type": "object",
		"properties": {
			"text": {
				"type": "string",
				"description": "The bullet-point text."
			}
		},
		"required": ["text"],
		"additionalProperties": False,
	},
}

# create_follow_up_actions_tool = {
# 	"type": "function",
# 	"function": {
# 		"name": "create_follow_up_actions",
# 		"description": "Suggest actionable follow-up tasks that the user might want to take at this point in the conversation.",
# 		"parameters": {
# 			"type": "object",
# 			"properties": {
# 				"actions": {
# 					"type": "string",
# 					"description": "A concise description of the follow-up actions."
# 				}
# 			},
# 			"required": ["actions"],
# 			"additionalProperties": False,
# 		},
# 	},
# }

# Optional: tell the model it may decide no tool call is appropriate yet
pass_tool = {
	"type": "function",
	"name": "pass",
	"description": "No significant development has happened; wait for more transcript before taking action.",
	"parameters": {
		"type": "object",
		"properties": {},
		"additionalProperties": False,
	},
}

MEETING_ASSISTANT_TOOLS = [
	create_meeting_note_topic_tool,
	create_meeting_note_bulletpoint_tool,
	# create_follow_up_actions_tool,
	# pass_tool,
]

# ---------------------------------------------------------------------------
# Updated system prompt (suggestion logic removed)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
	"You are an AI meeting assistant. Your goal is to help the user by creating structured meeting notes based on a live transcript and other context you receive.\n"
	"You will receive a JSON object containing the following information:\n"
	"- 'new_text': The most recent additions to the conversation transcript.\n"
	"- 'old_transcript': The full history of the conversation before 'new_text'.\n"
	"- 'already_generated_notes': A list of meeting notes already created by you. At all costs, you must not repeat anything already generated here\n"
	"- 'user_screen_ocr': Text captured from the user's screen. Only consider this in the context of the transcript, the new text (the audio being discussed) as one piece. Do not base notes solely on this.\n"
	"- 'triggered_by_clicks': A boolean that is true if the user manually requested assistance.\n"
	"\n"
	"Rules:\n"
	"1. Your ONLY output should be a function call. Do not respond with plain text.\n"
	"2. Emit a function call only if it is genuinely helpful.\n"
	"3. If 'new_text' introduces a completely new topic, call 'create_meeting_note_topic'. Review 'notes' to avoid duplicates.\n"
	"4. If 'new_text' adds significant details to the current topic, call 'create_meeting_note_bulletpoint'.\n"
	"5. Use 'user_screen_ocr' text ONLY as supplementary information. Include key terms, names, or data in the meeting notes when relevant.\n"
	"6. If 'triggered_by_clicks' is true, be proactive.\n"
	"7. Generate notes that are meaningful and helpful for future review.\n"
	"8. If you have not generated any notes yet, MAKE SURE to generate a title first.\n"
	"9. Only take notes on transcript and text mentioned directly relevant to a professional meeting.\n"
	"10. If the new text is a side tangent or a random mention to something, completely ignore it and do not generate any notes.\n"
	"11. Do NOT address the user for the notes."
	"<already_generated_notes>\n"
	"1. Always look at what you have already generated and do not ever, ever generate a similar bulletpoint or topic note again.\n"
	# "2. Once the note bulletpoint has been generated and they are still talking about the same topic, then use the pass tool.\n"
	"2. Make sure to always reference the already_generated_notes the user gives you to determine whether to just skip creating a note or to generate a new bulletpoint or title.\n"
	"</already_generated_notes>\n"
	"<meeting_note_topic>\n"
	"1. If the topic has shifted, call this before generating more bulletpoints.\n"
	# "2. For small talk or unrelated discussion, call 'pass'.\n"
	"3. If the topic is now very different and even though the general topic is the same, but it's in a different context, call this.\n"
	"4. If more than 5 bulletpoints have been created inside a title-bulletpoint block, always make sure to call create_meeting_note_topic to start a new block.\n"
	"5. Give bias to the transcript and last text rather than the user_screen_ocr. Only incorporate the user_screen_ocr text when it's relevant when considering the overall context.\n"
	"</meeting_note_topic>\n"
	"<meeting_note_bulletpoint>\n"
	"1. Include specific details, proper nouns, numbers, ideas, or action items.\n"
	"2. Do not repeat information already captured.\n"
	# "3. Skip idle talk or pleasantries – just call 'pass'.\n"
	"4. Bulletpoints should always have the specific information mentioned. It should be a brief summary of the latest new text added and be as succinct as possible.\n"
	"4. No need to add explanation in the bulletpoint. Simply create a note that has the information so the user can reference it later.\n"
	"</meeting_note_bulletpoint>\n"
	"<triggered_by_clicks>\n"
	"1. If triggered by clicks is true, then ONLY generate notes using the user_screen_ocr if there is anything relevant there to the current topic / notes.\n"
	"2. The user may just be browsing around random things, so do not generate notes in this case.\n"
	"3. DO NOT again generate notes already taken via the transcript and last changed text if once again triggered by clicks.\n"
	"</triggered_by_clicks>\n"
)

# ---------------------------------------------------------------------------
# Prompt used when *only* a title should be generated
# ---------------------------------------------------------------------------
FIRST_TITLE_PROMPT = (
	"You are an AI meeting assistant. Your ONLY task right now is to generate a _single_ meeting-note topic title that best describes the conversation so far.\n"
	"Return exactly one function call to `create_meeting_note_topic` and nothing else.\n"
	"You will receive a JSON object containing the following information:\n"
	"- 'new_text': The most recent additions to the conversation transcript.\n"
	"- 'old_transcript': The full history of the conversation before 'new_text'.\n"
	"- 'already_generated_notes': A list of meeting notes already created by you. At all costs, you must not repeat anything already generated here\n"
	"- 'user_screen_ocr': Text captured from the user's screen. Only consider this in the context of the transcript, the new text (the audio being discussed) as one piece. Do not base suggestions solely on this.\n"
	"- 'triggered_by_clicks': A boolean that is true if the user manually requested assistance.\n"
	"\n"
)


class MeetingAssistant(GeneralScreenAssistant):  # type: ignore
	"""Meeting note assistant built on the shared GeneralScreenAssistant.\n\n    The assistant now dynamically switches between the full tool-set and a **title-only**\n    mode:\n        1. If *no* topics have been created yet (`notes` list is empty), or\n        2. If the current topic already contains more than 5 bullet-points,\n    then only the `create_meeting_note_topic` tool is exposed and a simplified\n    prompt instructs the model to return just the first/new title.\n    """

	def __init__(self, word_diff_threshold: int = 20):
		super().__init__(
			system_prompt=SYSTEM_PROMPT,
			tool_calls=MEETING_ASSISTANT_TOOLS,
			word_diff_threshold=word_diff_threshold,
		)

	# ------------------------------------------------------------------
	# Override the sync analysis helper to support dynamic prompt/tool list
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
		"""Invoke the OpenAI API – but first decide whether we are in *title-only* mode."""

		notes = notes or []

		# ------------------------------------------------------------------
		# Decide whether the assistant should operate in *title‐only* mode
		# ------------------------------------------------------------------
		title_only_mode = False
		if not notes:
			# No titles created yet – need the very first topic title
			title_only_mode = True
		elif len(notes) > 0:
			last_note = notes[-1]
			# Expecting a structure like {"title": "...", "bulletpoints": [ ... ]}
			bulletpoints = last_note.get("bulletpoints", []) if isinstance(last_note, dict) else []
			print("len of bulletpoints: ", len(bulletpoints))
			if isinstance(bulletpoints, list) and len(bulletpoints) > 5:
				# Current topic is getting long – time to start a new topic
				title_only_mode = True

		print("Title only mode: ", title_only_mode)

		# Choose prompt and allowed tools
		if title_only_mode:
			prompt_base = FIRST_TITLE_PROMPT
			allowed_tools = [create_meeting_note_topic_tool]
		else:
			prompt_base = SYSTEM_PROMPT
			allowed_tools = MEETING_ASSISTANT_TOOLS

		# Append custom prompt if provided
		custom_prompt = get_custom_prompt(about_user, user_instructions, user_mode, "meeting assistant")
		if custom_prompt:
			prompt = prompt_base + "\n" + custom_prompt
		else:
			prompt = prompt_base

		# Build the payload expected by the model
		payload_dict = {
			"old_transcript": previous_transcript,
			# For triggered by clicks, do not duplicate generation the last changed text
			"new_text": new_sentence if not triggered_by_clicks else "",
			"already_generated_notes": notes,
			# It's causing the note generation around the text on screen, making it noisy
			"triggered_by_clicks": triggered_by_clicks,
		}
		
		if suggestions is not None:
			payload_dict["suggestions"] = suggestions

		if self._pass_ocr_to_prompt and watch_screen:
			payload_dict["user_screen_ocr"] = ocr_text

		user_payload = json.dumps(payload_dict)
		messages = [{"role": "user", "content": user_payload}]

		# Call the OpenAI API (blocking call executed in thread-pool by caller)
		response = openai_tool_calls(
			messages=messages,
			system_prompt=prompt,
			max_tokens=300,
			tool_calls=allowed_tools,
			model="gpt-4.1-mini-2025-04-14"
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
				# The new SDK returns each message with a type attribute
				msg_type = getattr(msg, "type", None) or (msg.get("type") if isinstance(msg, dict) else None)
				if msg_type != "function_call":
					continue  # We only care about function call messages

				# Extract function name and arguments depending on object/dict nature
				func_name = getattr(msg, "name", None) or (msg.get("name") if isinstance(msg, dict) else None)
				args_payload = getattr(msg, "arguments", None) or (msg.get("arguments") if isinstance(msg, dict) else None)

				# Ensure arguments is a dict
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
