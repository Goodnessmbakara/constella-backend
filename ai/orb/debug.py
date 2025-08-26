# write this to a file
import base64
from typing import List, Dict, Any
import json

def write_image_to_file(image_bytes: str):
	# Decode base64 string to bytes before writing
	image_data = base64.b64decode(image_bytes)
	with open("image_bytes.png", "wb") as f:
		f.write(image_data)


def write_messages_to_file(messages: List[Dict[str, Any]]):
	# If want to debug, uncomment this
	try:
		with open("messages.json", "w") as f:
			json.dump(messages, f, indent=2)
	except Exception as e:
		print(f"Error writing messages to messages.json: {e}")