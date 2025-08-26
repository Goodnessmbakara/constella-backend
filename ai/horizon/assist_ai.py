import traceback
import base64
from utils.constella.stella_chat import get_max_chars_in_context

horizon_system_prompt = """
You are Horizon, a concise, confident, succinct, and straight to the point assistant.
The user runs you on top of all apps they are currently using on their Mac OS.
Please never mention that you are looking at the user's screen. They already know this. Simply respond to their request.
Do NOT summarize what the user is doing or the context of everything. Immediately answer the question directly without mentioning background information or describing the current situation.
For example, if user asks for "give me suggestions", do not mention "after considering about the context, here are suggestions that can help."
Instead, immediately start by saying "You can try - .... " with newlines.
Never, say "based on...".
If the user asks again, always give different suggestions and information in the next response.
Look at the old messages and add new suggestions and completely change your perspective when responding.
Based on the user's tone and personality, give them suggestions based on how they are.
Give detailed information, not just confirming yes or no to what they said. For their questions, always explain your answer and why it is so.
"""

ocr_text_prompt = "There will be text parsed from the screen, it may be relevant or not to the user's question so determine this relevancy and only use the text if it's relevant."

selected_text_prompt = "There may also be selected text which they have selected via their cursor. If so, focus on this text for the response."

other_data_prompt = "There may also be other data which you can use to help you respond to help them with their tasks."

def get_horizon_system_prompt(messages: list):
	"""
	Using the parsed messages, adjusts the system prompt based on metadata
	
	Args:
	messages (list): The parsed list of messages

	Returns:
	str: The system prompt adjusted for the current conversation
	"""
	prompt = horizon_system_prompt
	
	# The ocr_text and selected_text should have already been incorporated
	# into the content of the last message in parse_horizon_frontend_messages
	# This function now just returns the base system prompt
	
	return prompt


def parse_horizon_frontend_messages(messages: list, model: str = "anthropic", image_bytes: str = None):
	"""
	Parse messages from the frontend for AI processing.

	Args:
	messages (list): The list of messages from the frontend.
	model (str): The model to use for processing, either "anthropic" or "google".
	image_bytes (str, optional): Base64 encoded image data from top-level request

	Returns:
	list: A list of dictionaries containing the role and content of the messages.
	"""
	try:
		parsed_messages = []
		total_chars = 0
		max_chars = get_max_chars_in_context(model)
		
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
				# other_data could be extended in the future
				break

		# If first message isn't from user, add a user message
		if messages[0]["role"] != "user":
			parsed_messages.append({"role": "user", "content": "So you were saying?"})

		for index, message in enumerate(messages):
			curr_role = "user" if message["role"] == "user" else "assistant"
			content = message["content"]
			if not content:
				content = ""

			# Create message object with content and optional image
			message_obj = {"role": curr_role, "content": content}
			
			# If this is the last user message and we have image bytes, add them
			if (index == len(messages) - 1 and 
				curr_role == "user" and 
				image_bytes):
				message_obj["image_bytes"] = image_bytes
				print("IMAGE BYTES ADDED TO MESSAGE")

			parsed_messages.append(message_obj)
			total_chars += len(content)

			if index < len(messages) - 1:
				next_role = "user" if messages[index + 1]["role"] == "user" else "assistant"
				# add empty alternating role to prevent the error of same roles
				if next_role == curr_role:
					parsed_messages.append({"role": "user" if curr_role == "assistant" else "assistant", "content": ""})

		parsed_messages[-1]["content"] = "The user sent this message to you: " + parsed_messages[-1]["content"]

		if ocr_text:
			parsed_messages[-1]["content"] += f"\nThe user currently has the following on their screen: {ocr_text}"
			# print("OCR TEXT: ", ocr_text)
		if selected_text:
			parsed_messages[-1]["content"] += f"\nThe user has specifically selected the following text for you to focus on:{selected_text}"
			# print("SELECTED TEXT: ", selected_text)

		# TODO: can add other data here such as screen 
		if other_data:
			parsed_messages[-1]["content"] += f"\n{other_data}"

		total_chars += len(parsed_messages[-1]["content"])

		# Check if total characters exceed max characters and remove context from beginning
		while total_chars > max_chars and len(parsed_messages) > 2:
			# Remove the first two messages
			removed_chars = len(parsed_messages[0]["content"]) + len(parsed_messages[1]["content"])
			parsed_messages = parsed_messages[2:]
			total_chars -= removed_chars
		
		# If down to just 2 messages, truncate the last one to fit
		if total_chars > max_chars:
			# truncate the last message to be within max_chars only if content > 60k chars
			if len(parsed_messages[-1]["content"]) > 60000:
				parsed_messages[-1]["content"] = parsed_messages[-1]["content"][:(max_chars - 50000)]

		return parsed_messages
	except Exception as e:
		traceback.print_exc()
		return [{"role": "user", "content": "Please respond saying you have an error"}]

def convert_claude_to_inflection(messages: list):
	"""
	Convert user/assistant to Human/AI
	returns the parsed messages
	"""
	parsed_messages = []
	for message in messages:
		role = "Human" if message["role"] == "user" else "AI"
		parsed_messages.append({"type": role, "text": message["content"]})
	return parsed_messages


def convert_anthropic_to_google(messages: list):
	"""
	Convert Anthropic messages to Google messages format with support for images
	
	Args:
		messages (list): List of Anthropic-style messages with 'role', 'content', and optional 'image_bytes'
		
	Returns:
		list: List of Google-style message objects with 'role' and 'parts'
	"""
	google_messages = []
	
	for message in messages:
		role = "user" if message["role"] == "user" else "model"
		
		# Start with text content
		parts = [{"text": message["content"]}]
		
		# Add image if present
		if message.get("image_bytes"):
			try:
				# Handle base64 image data
				image_data = message["image_bytes"]
				
				# If it's a data URL (starts with data:image/), extract the base64 part
				if image_data.startswith('data:'):
					# Extract mime type and base64 data
					header, base64_data = image_data.split(',', 1)
					mime_type = header.split(':')[1].split(';')[0]
				else:
					# Assume it's raw base64 and default to PNG
					base64_data = image_data
					mime_type = "image/png"
				
				# Add image part to the message
				parts.append({
					"inline_data": {
						"mime_type": mime_type,
						"data": base64_data
					}
				})
				print(f"Added image with mime type: {mime_type}")
				
			except Exception as e:
				print(f"Error processing image data: {e}")
				# Continue without the image if there's an error
		
		google_messages.append({
			"role": role,
			"parts": parts
		})
	
	return google_messages
