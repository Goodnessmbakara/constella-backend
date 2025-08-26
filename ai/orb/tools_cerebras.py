converse_with_user = {
	"type": "function",
	"function": {
		"name": "converse_with_user",
		"strict": True,
		"description": "Tell the user something or respond to their request.",
		"parameters": {
			"type": "object",
			"properties": {
				"message": {
					"type": "string",
					"description": "The message to tell the user."
				}
			},
			"required": [
				"message"
			],
			"additionalProperties": False
		}
	}
}

# ---------------------------------------------------------------------------
# Execute tool calls
# - input_text_field (input text into the current application or field that the user is focused on)
# - click_text (click the text that the user is focused on)
# ---------------------------------------------------------------------------


input_text_field = {
	"type": "function",
	"function": {
		"name": "input_text",
		"strict": True,
		"description": "Input text into the current application or field that the user is focused on.",
		"parameters": {
			"type": "object",
			"properties": {
				"text": {
					"type": "string",
					"description": "The text to input into the current application."
				}
			},
			"required": [
				"text"
			],
			"additionalProperties": False
		}
	},
}

click_text = {
	"type": "function",
	"function": {
		"name": "click_text",
		"strict": True,
		"description": "Based on the user's goal, click this text to try to perform an action towards it.\\nUsing the texts given, infer which seems like a clickable, interactable text based on your knowledge of UI.",
		"parameters": {
			"type": "object",
			"properties": {
				"text": {
					"type": "string",
					"description": "The exact text to click on from the list of texts given."
				}
			},
			"required": [
				"text"
			],
			"additionalProperties": False
		}
	},
}




def get_cerebras_orb_tools(auto_execute: bool = True):
	"""
	Return the list of tools available to the Orb assistant.

	Parameters
	----------
	auto_execute : bool, optional
	    If True, include tools that should be executed automatically.
	    If False, return only the basic conversational tool.
	"""
	tools = [converse_with_user]
	if auto_execute:
		tools.append(input_text_field)
		tools.append(click_text)
	return tools

def get_screen_execute_cerebras_orb_tools():
	tools = [input_text_field, click_text]
	return tools