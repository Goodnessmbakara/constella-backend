converse_with_user = {
    "type": "function",
    "name": "converse_with_user",
    "description": "Tell the user something or respond to their request.",
    "parameters": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message to tell the user. Make it as long as needed and with formatting of bullet-points, headings, and titles as required."
            }
        },
        "required": [
            "message"
        ],
        "additionalProperties": False
    }
}

input_text_field = {
    "type": "function",
    "name": "input_text",
    "description": "Input text into the current application or field that the user is focused on.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to input into the current application.\n\nShould be only the exact text to input based on the situation and no explanation or any other text besides what should go into the input."
            }
        },
        "required": [
            "text"
        ],
        "additionalProperties": False
    }
}


start_long_screen_execution = {
    "type": "function",
    "name": "start_long_screen_execution",
    "description": "If the user's request is to perform a long sequence of actions to accomplish a goal, call this tool to start the execution. Anything that involves more than 1 click should be done in this tool (i.e not a quick response or single click or typing request).",
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The goal of the user's request as defined by how will we know, based on the screen text, that we have accomplished it."
            },
            "metric_to_track": {
                "type": "string",
                "description": "Each turn after doing some actions, the metric to track. Make it as quantative as possible (i.e. 20 approvals done so far, 5 profiles found) or if it's a done or not done metric, what to track based on the screen text to indicate if it's done or not."
            },
            "description_of_screen": {
                "type": "string",
                "description": "A description of the screen for future requests. Describe fully what type of window the user is on, what type of elements there are, and where the expected string of texts to click on would be. For example, if the user is on a social media, form, or a code editor. For social media, the text would be in center of screen, a form, the text would be in the center of the screen, and a code editor, the text could be around, everywhere, but maybe for the task it's just the text at the top (i.e. if asked to click tabs)."
            }
        },
        "required": [
            "goal",
            "metric_to_track"
        ],
        "additionalProperties": False
    }
}



def get_orb_tools(auto_execute: bool = True):
	"""
	Return the list of tools available to the Orb assistant.

	Parameters
	----------
	auto_execute : bool, optional
	    If True, include tools that should be executed automatically.
	    If False, return only the basic conversational tool.
	"""
	tools = []
	if auto_execute:
		tools.append(input_text_field)
		# In future, can add long running screen execution tool
		# tools.append(start_long_screen_execution)
	return tools