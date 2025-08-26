import json
from ai.openai_setup import openai_client
import time
import os
import requests
from anthropic import Anthropic
from google import genai
from google.genai import types
import traceback

from utils.constella.stella_chat import convert_anthropic_to_google


# Anthropic Client
anthropic_client = Anthropic(
	api_key=os.environ.get("ANTHROPIC_API_KEY"),
)

# Configure Google GenAI
try:
	genai_client = genai.Client(api_key=os.environ["GOOGLE_STUDIO_KEY"])
except Exception as e:
	print(f"Error configuring Google GenAI: {e}")


# Inflection API
inflection_api_key = os.getenv("INFLECTION_API_KEY")


def create_word_completion(
	messages: list,
	temperature: float = 0,
	max_tokens: int | None = 300,
	model: str | None = "gpt-3.5-turbo",
):
	response = None
	num_retries = 10
	warned_user = False
	print(
		f"Creating chat completion with model {model}, temperature {temperature},"
		f" max_tokens {max_tokens}"
	)
	for attempt in range(num_retries):
		backoff = 2 ** (attempt + 2)
		try:
			response = openai_client.responses.create(
				model=model,
				input=messages,
				temperature=temperature,
				max_output_tokens=max_tokens,
				stream=True
			)
			break
		except Exception as e:
			# Handle exceptions (you may want to add more specific exception handling)
			if attempt == num_retries - 1:
				break
			print(f"Error: API error. Waiting {backoff} seconds...")
			time.sleep(backoff)
	if response is None:
		print("FAILED TO GET RESPONSE FROM OPENAI")
		print(f"Failed to get response after {num_retries} retries")

	yield "Doxo_Thinking..."
	buffer = ""
	for event in response:
		# The Responses API streams events; capture text deltas
		if getattr(event, "type", "") == "response.output_text.delta":
			content = buffer + event.delta
			if " " in content:
				word, buffer = content.rsplit(" ", 1)
				yield word
			else:
				buffer = content

	# Yield the final word in the buffer
	if buffer:
		yield buffer

	yield "Doxo_Stopped..."


def create_chat_completion(
	messages: list,  # type: ignore
	temperature: float = 0,
	# adjust this to increase or decrease the speed, can create setting in UI that will increase or decrease output lenght
	max_tokens: int | None = 300,  # max of 500 tokens by default
	model: str | None = "gpt-3.5-turbo",  # change default model here
	response_format: str = "text",
) -> str:
	"""Create a chat completion using the OpenAI API

	Args:
		messages (list[dict[str, str]]): The messages to send to the chat completion
		model (str, optional): The model to use. Defaults to None.
		temperature (float, optional): The temperature to use. Defaults to 0.9.
		max_tokens (int, optional): The max tokens to use. Defaults to None.

	Returns:
	str: The response from the chat completion
	"""
	response = None
	num_retries = 4
	warned_user = False
	print(
		f"Creating chat completion with model {model}, temperature {temperature},"
		f" max_tokens {max_tokens}"
	)
	for attempt in range(num_retries):
		backoff = 2 ** (attempt + 2)
		try:
			response = openai_client.responses.create(
				model=model,
				input=messages,
				temperature=temperature,
				max_output_tokens=max_tokens,
				response_format={"type": response_format}
			)
			break
		except Exception as e:
			# Handle exceptions (you may want to add more specific exception handling)
			if attempt == num_retries - 1:
				break
			print(f"Error: API error. Waiting {backoff} seconds...")
			time.sleep(backoff)
	if response is None:
		print("FAILED TO GET RESPONSE FROM OPENAI")
		print(f"Failed to get response after {num_retries} retries")
		return ""

	# ----------------------------------------------
	# NEW: Parse the updated response format
	# ----------------------------------------------
	try:
		# The new OpenAI `response` object contains an `output` list with messages
		output_messages = getattr(response, "output", None)
		if output_messages is None and isinstance(response, dict):
			output_messages = response.get("output")

		if output_messages:
			first_msg = output_messages[0]
			content_items = getattr(first_msg, "content", None)
			if content_items is None and isinstance(first_msg, dict):
				content_items = first_msg.get("content")

			if content_items and isinstance(content_items, list):
				first_part = content_items[0]
				# Depending on SDK, the part may be a dict or an object with `text`
				if isinstance(first_part, dict):
					return first_part.get("text", "")
				else:
					return getattr(first_part, "text", "")
	except Exception:
		# If parsing fails, attempt legacy attribute for compatibility
		return getattr(response, "output_text", "")

	# Fallback – return empty string if nothing extracted
	return ""


def create_chat_message(role, content):
	"""
	Create a chat message with the given role and content.

	Args:
	role (str): The role of the message sender, e.g., "system", "user", or "assistant".
	content (str): The content of the message.

	Returns:
	dict: A dictionary containing the role and content of the message.
	"""
	return {"role": role, "content": content}

# get the number of AI messages in a list of messages
def numb_assistant_messages(messages):
	count = 0
	for message in messages:
		if message["role"] == "assistant":
			count += 1
	return count

def get_last_ai_message_in_chat(messages):
	"""
	Get the content of the last message from the assistant in a list of messages.

	Args:
	messages (list): The list of messages.

	Returns:
	str: The content of the last message from the assistant.
	"""
	for message in reversed(messages):
		if message["role"] == "assistant":
			return message["content"]
	return None


def create_inflection_request(prompt: str, metadata = None):
	url = "https://gateway.inf7cw9.com/external/api/inference"
	headers = {
		"Authorization": "Bearer c4af63af-3809-4f2f-b311-57572b668aa0",
		"Content-Type": "application/json"
	}


	# Add the prompt to the context
	context = [{"type": "Instruction", "text": prompt}]

	payload = {
		"config": "prod_fudge_6",
		"context": context
	}

	response = requests.post(url, headers=headers, json=payload)

	if response.status_code == 200:
		return response.json()["text"]
	else:
		print(f"Error: {response.text}")
		return None

def create_inflection_messages_request(messages: list[dict], metadata = None):
	url = "https://gateway.inf7cw9.com/external/api/inference"
	headers = {
		"Authorization": "Bearer c4af63af-3809-4f2f-b311-57572b668aa0",
		"Content-Type": "application/json"
	}

	payload = {
		"config": "prod_fudge_6",
		"context": messages
	}

	response = requests.post(url, headers=headers, json=payload)

	if response.status_code == 200:
		return response.json()["text"]
	else:
		print(f"Error: {response.text}")
		return None

# *** Anthropic API ***

def stream_anthropic_response(
	messages: list,
	model: str = "claude-sonnet-4-20250514",
	max_tokens: int = 200,
	temperature: float = 0.5,
	system_prompt="",
	thinking_enabled:bool = False,
	thinking_budget_tokens:int = 1024,
):
	"""
	Calls the Anthropic with the given prompt and streams the response.
	"""
	try:
		thinking_params = {
			"type": "enabled" if thinking_enabled else "disabled",
		}
		if thinking_enabled:
			thinking_params["budget_tokens"] = thinking_budget_tokens
			# Output tokens must be greater than thinking budget tokens
			if thinking_budget_tokens > max_tokens:
				thinking_budget_tokens = max_tokens - 1
			# Temperature must be 1 for thinking
			temperature = 1

		stream = anthropic_client.messages.create(
			max_tokens=max_tokens,
			messages=messages,
			model=model,
			system=system_prompt,
			stream=True,
			temperature=temperature,
			thinking=thinking_params
		)
		final_message = ""

		for event in stream:
			match event.type:
				case "content_block_delta":
					if event.delta.type == "text_delta":
						final_message += event.delta.text
						yield event.delta.text
	except Exception as e:
		traceback.print_exc()
		return


def create_anthropic_request(
    messages: list,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 200,
    temperature: float = 0.5,
    system_prompt: str = "",
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 1024,
):
    """
    Calls the Anthropic API with the given messages and returns the response.

    Args:
        messages (list): List of message dictionaries with 'role' and 'content'
        model (str): Anthropic model to use
        max_tokens (int): Maximum number of tokens in the response
        temperature (float): Temperature for response generation
        system_prompt (str): System instructions for the model
        thinking_enabled (bool): Whether to enable thinking mode
        thinking_budget_tokens (int): Token budget for thinking when enabled

    Returns:
        str: The model's response text
    """
    try:
        thinking_params = {
            "type": "enabled" if thinking_enabled else "disabled",
        }
        if thinking_enabled:
            thinking_params["budget_tokens"] = thinking_budget_tokens
            # Output tokens must be greater than thinking budget tokens
            if thinking_budget_tokens > max_tokens:
                thinking_budget_tokens = max_tokens - 1
            # Temperature must be 1 for thinking
            temperature = 1

        response = anthropic_client.messages.create(
            max_tokens=max_tokens,
            messages=messages,
            model=model,
            system=system_prompt,
            temperature=temperature,
            thinking=thinking_params
        )

        return response.content[0].text
    except Exception as e:
        print(f"Error generating content with Anthropic: {e}")
        traceback.print_exc()
        return None


def create_google_request(prompt: str, model_name: str = "gemini-2.0-flash-lite", temperature: float = 1, top_p: float = 0.95, top_k: int = 40, max_tokens: int = 100, response_mime_type: str = "text/plain"):
	try:
		response = genai_client.models.generate_content(
			model=model_name,
			contents=prompt,
			config={
				"temperature": temperature,
				"top_p": top_p,
				"top_k": top_k,
				"max_output_tokens": max_tokens,
				"response_mime_type": response_mime_type,
			}
		)
		print(response)
		return response.text
	except Exception as e:
		print(f"Error generating content with Google GenAI: {e}")
		return None

def create_new_google_request(prompt: str, model_name: str = "gemini-2.5-flash-preview-05-20", response_mime_type: str = "text/plain", temperature: float = 1, max_tokens: int = 100, thinking_budget_tokens: int = 100):
	"""
	Create a new Google GenAI request with streaming response

	Args:
		prompt (str): The input text prompt
		model_name (str): The model to use
		response_mime_type (str): The response format

	Returns:
		str: The complete response text
	"""
	try:
		contents = [
			types.Content(
				role="user",
				parts=[
					types.Part.from_text(text=prompt),
				],
			),
		]
		generate_content_config = types.GenerateContentConfig(
			response_mime_type=response_mime_type,
			temperature=temperature,
			max_output_tokens=max_tokens,
			thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget_tokens) # 0 disables it
		)

		response = genai_client.models.generate_content(
			model=model_name,
			contents=contents,
			config=generate_content_config,
		)

		return response.text
	except Exception as e:
		print(f"Error generating content with Google GenAI: {e}")
		traceback.print_exc()
		return None

def stream_google_response(messages: list, system_prompt: str = None, max_tokens: int = 1000, model="gemini-2.5-pro-preview-03-25", convert_func=None, thinking_budget_tokens: int = 0):
	"""
	Stream a response from Google's Gemini model

	Args:
		messages (list): List of messages in Anthropic format
		system_prompt (str, optional): System instructions for the model
		convert_func (function, optional): Function to convert messages to Google format

	Returns:
		generator: A generator that yields response chunks
	"""
	# Use provided conversion function or default
	if convert_func is None:
		convert_func = convert_anthropic_to_google

	# Convert messages to Google format
	google_messages = convert_func(messages)

	# Prepare request configuration
	config = None
	if system_prompt or max_tokens:
		config = types.GenerateContentConfig(
			system_instruction=system_prompt,
			max_output_tokens=max_tokens,
			thinking_config=types.ThinkingConfig(thinking_budget=0) # 0 disables it
		)

	# Stream the response
	response = genai_client.models.generate_content_stream(
		model=model,
		contents=google_messages,
		config=config
	)


	# Return the streaming response
	for chunk in response:
		try:
			if hasattr(chunk, 'text'):
				yield chunk.text
		except Exception as e:
			print("Error: ", e)
			traceback.print_exc()


def stream_openai_response(
	messages: list,
	system_prompt: str = None,
	max_tokens: int = 1000,
	model: str = "gpt-4.1-2025-04-14",
	temperature: float = 0.7
):
	"""
	Stream a response from OpenAI's models

	Args:
		messages (list): List of messages in standard OpenAI format
		system_prompt (str, optional): System instructions for the model
		max_tokens (int): Maximum number of tokens to generate
		model (str): OpenAI model to use
		temperature (float): Temperature for response generation

	Returns:
		generator: A generator that yields response chunks
	"""
	try:
		# If system prompt is provided, prepend it to messages
		if system_prompt:
			messages = [{"role": "system", "content": system_prompt}] + messages

		# Create streaming response
		stream = openai_client.responses.create(
			model=model,
			input=messages,
			temperature=temperature,
			max_output_tokens=max_tokens,
			stream=True
		)

		# Stream the response chunks
		for event in stream:
			if getattr(event, "type", "") == "response.output_text.delta":
				yield event.delta

	except Exception as e:
		print(f"Error streaming OpenAI response: {e}")
		traceback.print_exc()

def openai_tool_calls(
	messages: list,
	system_prompt: str = None,
	max_tokens: int = 1000,
	model: str = "gpt-4o-2024-08-06", # has higher speed than 4.1 mini apparently
	temperature: float = 0.7,
	tool_calls: list = None,
	parallel_tool_calls: bool = False,
	stream: bool = False
):
	"""
	Get a structured response from OpenAI's models using response_format

	Args:
		messages (list): List of messages in standard OpenAI format
		response_format (dict): JSON schema for structured output
		system_prompt (str, optional): System instructions for the model
		max_tokens (int): Maximum number of tokens to generate
		model (str): OpenAI model to use (must support structured outputs)
		temperature (float): Temperature for response generation

	Returns:
		dict: Parsed JSON response matching the specified format
	"""
	try:
		# If system prompt is provided, prepend it to messages
		if system_prompt:
			messages = [{"role": "system", "content": system_prompt}] + messages

		# Create structured response
		response = openai_client.responses.create(
			model=model,
			input=messages,
			temperature=temperature,
			max_output_tokens=max_tokens,
			tools=tool_calls,
			parallel_tool_calls=parallel_tool_calls,
			stream=stream
		)

		return response

	except Exception as e:
		print(f"Error getting OpenAI structured response: {e}")
		traceback.print_exc()
		return None


def create_json_schema(name: str, properties: dict, required_fields: list = None):
	"""
	Create a JSON schema for structured outputs

	Args:
		name (str): Name of the schema
		properties (dict): Properties definition
		required_fields (list): List of required field names

	Returns:
		dict: JSON schema formatted for OpenAI structured outputs
	"""
	if required_fields is None:
		required_fields = list(properties.keys())

	return {
		"type": "json_schema",
		"json_schema": {
			"name": name,
			"strict": True,
			"schema": {
				"type": "object",
				"properties": properties,
				"required": required_fields,
				"additionalProperties": False
			}
		}
	}


def openai_structured_output(
	messages: list,
	response_format: dict,
	system_prompt: str = None,
	max_tokens: int = 1000,
	model: str = "gpt-4o-2024-08-06",
	temperature: float = 0.7
):
	"""
	Get a structured JSON response from OpenAI's models using Structured Outputs

	Args:
		messages (list): List of messages in standard OpenAI format
		response_format (dict): JSON schema for structured output (created with create_json_schema)
		system_prompt (str, optional): System instructions for the model
		max_tokens (int): Maximum number of tokens to generate
		model (str): OpenAI model to use (must support structured outputs)
		temperature (float): Temperature for response generation

	Returns:
		dict: Parsed JSON response matching the specified format
	"""
	try:
		# If system prompt is provided, prepend it to messages
		if system_prompt:
			messages = [{"role": "system", "content": system_prompt}] + messages

		# Create structured response using chat completions API (supports response_format)
		response = openai_client.chat.completions.create(
			model=model,
			messages=messages,
			temperature=temperature,
			max_tokens=max_tokens,
			response_format=response_format
		)

		# Parse the structured response from the new format
		try:
			# Primary: parse content from chat completion choices
			if hasattr(response, 'choices') and response.choices:
				content = response.choices[0].message.content
				if isinstance(content, str):
					return json.loads(content)
				# In some SDK versions, the structured output may be returned as list of content parts
				if isinstance(content, list) and len(content) > 0:
					first_part = content[0]
					if isinstance(first_part, dict) and 'text' in first_part:
						return json.loads(first_part['text'])

			# Secondary: legacy Responses API structure
			if hasattr(response, 'output') and response.output:
				first_msg = response.output[0]
				if hasattr(first_msg, 'content') and first_msg.content:
					first_part = first_msg.content[0]
					if hasattr(first_part, 'text'):
						return json.loads(first_part.text)

		except (json.JSONDecodeError, AttributeError) as parse_error:
			print(f"Error parsing structured response: {parse_error}")
			return None

		return None

	except Exception as e:
		print(f"Error getting OpenAI structured response: {e}")
		traceback.print_exc()
		return None
