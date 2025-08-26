import os
import time
import json
from cerebras.cloud.sdk import Cerebras
import ai.stella.assistants.tools.tool_implementations as tool_impls
import requests


max_chars_in_context = 40000
max_retries_on_error = 10
rerun_if_message_content_this_length = 300

client = Cerebras(
	# This is the default and can be omitted
	api_key=os.environ.get("CEREBRAS_API_KEY"),
)

from ai.stella.assistants.tools.tools_cerebras import (converse_with_user_tool, create_connection_tool,
	create_note_tool, delete_connection_tool, delete_note_tool, edit_note_title_tool,
	delete_part_of_note_content_tool, replace_part_of_note_content_tool,
	add_part_to_note_content_tool, get_website_url_content_tool, google_search_tool, 
	similarity_search_user_notes_tool, add_tags_to_note_tool, remove_tags_from_note_tool)

assistant_tools = [
	# similarity_search_user_notes_tool,
	google_search_tool,
	get_website_url_content_tool,
	# Note tools
	create_note_tool,
	add_tags_to_note_tool,
	remove_tags_from_note_tool,
	delete_part_of_note_content_tool,
	replace_part_of_note_content_tool,
	add_part_to_note_content_tool,
	delete_note_tool,
	# Connection tools
	create_connection_tool,
	delete_connection_tool,
	# It expects then a response so its better to just give a response at the end
	# converse_with_user_tool 
	# keyword_search_user_notes_tool
]

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

async def run_cerebras_tool_call(
	tool_call,
	extra_args: dict = None,
	messages: list = None
):	
	function_call = tool_call.function
	print(function_call)
	function_name = function_call.name
	# print(f"Model executing function '{function_call.name}' with arguments {function_call.arguments}")
	arguments = json.loads(function_call.arguments)
	if extra_args:
		for key, value in extra_args.items():
			arguments[key] = value

	to_run = getattr(tool_impls, function_call.name, None)

	if to_run is None:
		result = f"Function {function_name} not supported"
	else:
		result = await to_run(**arguments)
	
	# Send the result back to the model to fulfill the request.
	messages.append({
		"role": "tool",
		"content": json.dumps(result),
		"tool_call_id": tool_call.id
	})

async def stream_cerebras_response(
	messages: list,
	model: str = "qwen-3-32b",
	temperature: float = 0.7,
	max_tokens: int = 1000,
	system_prompt: str = None,
	extra_args: dict = None
):
	"""
	Stream a response from Cerebras models
	
	Args:
		messages (list): List of messages in standard format
		model (str): Cerebras model to use
		temperature (float): Temperature for response generation
		max_tokens (int): Maximum number of tokens to generate
		
	Returns:
		generator: A generator that yields response chunks
	"""
	try:
		messages = convert_frontend_messages_to_cerebras_messages(messages)

		if system_prompt:
			messages.insert(0, {"role": "system", "content": system_prompt})

		retries = 0

		while True:
			try:
				resp = client.chat.completions.create(
					messages=messages,
					model=model,
					temperature=temperature,
					max_tokens=max_tokens,
					tools=assistant_tools,
					# stream=True,
					# parallel_tool_calls=False 
				)

				msg = resp.choices[0].message

				# If the assistant didn't ask for a tool, give back final response
				if not msg.tool_calls:
					# print("Final response: ", msg.content)
					return msg.content

				# Save the assistant turn exactly as returned
				messages.append(msg.model_dump())    

				for tool_call in msg.tool_calls:
					await run_cerebras_tool_call(tool_call, extra_args=extra_args, messages=messages)
			except Exception as e:
				# If less than max retries, try again with a wait + reduce context
				messages[-1]["content"] = messages[-1]["content"][:max_chars_in_context - 5000]
				
				retries += 1
				if retries > max_retries_on_error:
					raise e
				time.sleep(1)
					
	except Exception as e:
		print(f"Error streaming Cerebras response: {e}")
		import traceback
		traceback.print_exc()

async def stream_openrouter_response(
	messages: list,
	model: str = "qwen/qwen3-32b",
	temperature: float = 0.7,
	max_tokens: int = 1000,
	system_prompt: str = None,
	extra_args: dict = None
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
					"tools": assistant_tools,
				}

				# Make API request
				response = requests.post(url, headers=headers, json=data)
				response.raise_for_status()
				
				result = response.json()
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
					await run_openrouter_tool_call(tool_call, extra_args=extra_args, messages=messages)
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