import os
import time
import json
import requests
import traceback

from ai.orb.llms.tool_impls import tool_impls

max_chars_in_context = 300000

# Default config constants
rerun_if_message_content_this_length = 15000  # If assistant message exceeds this length, force a rerun with shorter context
max_retries_on_error = 2  # Maximum number of retries when OpenRouter returns an error

def add_ocr_text_to_message(message: str, ocr_text: str):
	"""Add the OCR text to the message"""
	message += f"\nTo further help you understand the image of the screen sent to you, here is also the OCR text on the screen: {ocr_text}"
	return message

def add_selected_text_to_message(message: str, selected_text: str):
	"""Add the selected text to the message"""
	message += f"\nThe user has specifically selected the following text on their screen for you to focus on:{selected_text}"
	return message

def add_other_data_to_message(message: str, other_data: str):
	"""Add the other data to the message"""
	message += f"\nHere is some more data to help you understand the screen: {other_data}"
	return message

def openrouter_parse_orb_frontend_messages(messages: list, image_bytes: str = None, screen_execute_mode: bool = False, extra_prompt: str = None):
	"""
	Parse messages from the frontend for OpenRouter API processing.
	Handles OCR text, selected text, and image data similar to parse_orb_frontend_messages.

	Args:
		messages (list): The list of messages from the frontend.
		image_bytes (str, optional): Base64 encoded image data from top-level request

	Returns:
		list: A list of dictionaries containing the role and content of the messages.
	"""
	try:
		parsed_messages = []
		total_chars = 0
		
		# Extract metadata from the last user message
		ocr_text = None
		selected_text = None
		other_data = None
		
		# Find the last user message with metadata
		for message in reversed(messages):
			if message.get("role") == "user" and message.get("metadata"):
				metadata = message.get("metadata", {})
				ocr_text = metadata.get("ocrText")
				selected_text = metadata.get("selectedText")
				other_data = metadata.get("otherData")
				break

		# If first message isn't from user, add a user message
		if messages and messages[0]["role"] != "user":
			parsed_messages.append({"role": "user", "content": "So you were saying?"})
		
		for index, message in enumerate(messages):
			curr_role = "user" if message["role"] == "user" else "assistant"
			content = message["content"]
			if not content:
				content = ""

			# Create message object with content
			message_obj = {"role": curr_role, "content": content}

			parsed_messages.append(message_obj)
			total_chars += len(content)

			if index < len(messages) - 1:
				next_role = "user" if messages[index + 1]["role"] == "user" else "assistant"
				# add empty alternating role to prevent the error of same roles
				if next_role == curr_role:
					parsed_messages.append({"role": "user" if curr_role == "assistant" else "assistant", "content": ""})

		print('PARSED MESSAGES:')
		print(parsed_messages)

		# Enhance the last message with context and metadata
		if parsed_messages and not screen_execute_mode:
			parsed_messages[-1]["content"] = "The user sent this message to you: " + parsed_messages[-1]["content"]
		if screen_execute_mode:
			parsed_messages[-1]["content"] = "We are taking over the user's screen to execute the following goal and metric to track using the screen OCR text: " + parsed_messages[-1]["content"] + "\n" + extra_prompt
			parsed_messages[-1]["content"] += "\nIn your response back, measure the current metric and what steps we need to take to accomplish towards the goal."

			if ocr_text:
				parsed_messages[-1]["content"] = add_ocr_text_to_message(parsed_messages[-1]["content"], ocr_text)
			if selected_text:
				parsed_messages[-1]["content"] = add_selected_text_to_message(parsed_messages[-1]["content"], selected_text)
			if other_data:
				parsed_messages[-1]["content"] = add_other_data_to_message(parsed_messages[-1]["content"], other_data)

			total_chars += len(parsed_messages[-1]["content"])

		# Check if total characters exceed max characters and remove context from beginning
		while total_chars > max_chars_in_context and len(parsed_messages) > 2:
			# Remove the first two messages
			removed_chars = len(parsed_messages[0]["content"]) + len(parsed_messages[1]["content"])
			parsed_messages = parsed_messages[2:]
			total_chars -= removed_chars
		
		# If down to just 2 messages, truncate the last one to fit
		if total_chars > max_chars_in_context:
			# truncate the last message to be within max_chars only if content > 60k chars
			if parsed_messages and len(parsed_messages[-1]["content"]) > 60000:
				parsed_messages[-1]["content"] = parsed_messages[-1]["content"][:(max_chars_in_context - 50000)]

		return parsed_messages
	except Exception as e:
		traceback.print_exc()
		return [{"role": "user", "content": "Please respond saying you have an error"}]

def convert_frontend_messages_to_cerebras_messages(messages: list):
	cerebras_messages = []
	for message in messages:
		cerebras_messages.append({"role": "user" if message.get('sender') == 'user' else "assistant", "content": message["content"]})
	
	# Count total character length
	total_chars = sum(len(msg["content"]) for msg in cerebras_messages)

	print("Total chars: ", total_chars)
	
	# If total exceeds 300,000 characters, remove messages from the front in batches of 2
	if total_chars > max_chars_in_context and len(cerebras_messages) > 2:
		while total_chars > max_chars_in_context and len(cerebras_messages) > 2:
			# Remove 2 messages from the front
			removed_chars = 0
			for _ in range(min(2, len(cerebras_messages))):
				if cerebras_messages:
					removed_msg = cerebras_messages.pop(0)
					removed_chars += len(removed_msg["content"])

			total_chars -= removed_chars
	
	# Since we check > 2 above, if still above max_chars_in_context, truncate the fileText / content
	if total_chars > max_chars_in_context:
		print("Truncating context")
		cerebras_messages[-1]["content"] = cerebras_messages[-1]["content"][:max_chars_in_context]
		

	return cerebras_messages

async def stream_openrouter_response(
	messages: list,
	model: str = "qwen/qwen3-32b",
	temperature: float = 0.7,
	max_tokens: int = 1000,
	system_prompt: str = None,
	extra_args: dict = None,
	tools: list = None,
	multi_turn_mode: bool = True, # if disabled, then after response, model will stop instead of continuing to feed itself the output and continuing to run
	parallel_tool_calls: bool = True # if enabled, then tool calls will be run in parallel instead of sequentially
):
	"""
	Stream a response from Cerebras models via OpenRouter
	
	Args:
		messages (list): List of messages in standard format
		model (str): OpenRouter model to use (default: meta-llama/llama-3.3-70b-instruct)
		temperature (float): Temperature for response generation
		max_tokens (int): Maximum number of tokens to generate
		system_prompt (str): Optional system prompt to prepend
		extra_args (dict): Extra arguments to pass to tool functions
		tools (list): Optional list of tools to make available to the model
		
	Returns:
		str: The final response content
	"""
	try:
		messages = convert_frontend_messages_to_cerebras_messages(messages)

		if system_prompt:
			messages.insert(0, {"role": "system", "content": system_prompt})

		# OpenRouter API configuration
		api_key = os.getenv("OPENROUTER_API_KEY")
		if not api_key:
			raise ValueError("OPENROUTER_API_KEY environment variable is required")
			
		url = "https://openrouter.ai/api/v1/chat/completions"
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json"
		}

		retries = 0

		while True:
			try:
				# Prepare request payload
				data = {
					"model": model,
					"provider": {
						"only": ["Cerebras"]
					},
					"messages": messages,
					"temperature": temperature,
					"max_tokens": max_tokens,
					"parallel_tool_calls": parallel_tool_calls,
					"tool_choice": "required"
				}
				
				# Add tools if provided
				if tools:
					data["tools"] = tools

				# Make API request
				response = requests.post(url, headers=headers, json=data)
				response.raise_for_status()
				
				result = response.json()
				
				print("||| RESPONSE:")
				print(result)
				print("|||")

				msg = result['choices'][0]['message']

				# Save the assistant turn exactly as returned
				messages.append(msg)

				# If the assistant didn't ask for a tool, check final response
				if not msg.get('tool_calls'):
					# If response is too long, re-reun
					if len(msg.get('content')) > rerun_if_message_content_this_length:
						messages.append({
							"role": "user",
							"content": "Your response was too long and you didn't take all the actions. I have already given you all the instructions. Do all the tasks I requested and then give me just a single sentence final response back."
						})
						raise Exception("Message content too long, rerunning")
					# print("Final response: ", msg.get('content'))
					return msg.get('content')

				# Process each tool call
				for tool_call in msg.get('tool_calls', []):
					print('---> TOOL CALL:')
					print(tool_call)
					print('----')
					await run_openrouter_tool_call(tool_call, extra_args=extra_args, messages=messages)
				
				if not multi_turn_mode:
					return msg.get('content')
			except Exception as e:
				# If less than max retries, try again with a wait + reduce context
				messages[-1]["content"] = messages[-1]["content"][:max_chars_in_context - 5000]
				
				retries += 1
				if retries > max_retries_on_error:
					raise e
				time.sleep(1)

	except Exception as e:
		print(f"Error streaming OpenRouter response: {e}")
		import traceback
		traceback.print_exc()
		return "Sorry, I encountered an error while processing your request."

async def run_openrouter_tool_call(
	tool_call,
	extra_args: dict = None,
	messages: list = None
):	
	"""Execute tool calls for OpenRouter responses"""
	function_call = tool_call['function']
	function_name = function_call['name']
	# print(f"Model executing function '{function_call['name']}' with arguments {function_call['arguments']}")
	arguments = json.loads(function_call['arguments'])
	if extra_args:
		for key, value in extra_args.items():
			arguments[key] = value

	to_run = getattr(tool_impls, function_call['name'])

	if to_run is None:
		result = f"Function {function_name} not supported"
	else:
		result = await to_run(**arguments)
	
	# Send the result back to the model to fulfill the request.
	messages.append({
		"role": "tool",
		"content": json.dumps(result),
		"tool_call_id": tool_call['id']
	})