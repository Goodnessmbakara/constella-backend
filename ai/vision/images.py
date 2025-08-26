from ai.openai_setup import openai_client
import base64
import uuid
import requests
import json
import os
def image_to_text(imageBase64: str):
	try:
		response = openai_client.chat.completions.create(
			model="gpt-4o-mini",
			messages=[
				{
					"role": "user",
					"content": [
						{"type": "text", "text": "Give a short 10 to 15 word description of the image as specific as possible. If the image contains only text, give the full, exact text instead. If there is partial text, then return the text first and then the description. Return just the result. Result: "},
						{
							"type": "image_url",
							"image_url": {
								"url": imageBase64,
							},
						},
					],
				}
			],
			max_tokens=200,
		)
		content = response.choices[0].message.content
		# Remove quotes if the content starts and ends with them
		if content.startswith('"') and content.endswith('"'):
			content = content[1:-1]
		return content
	except Exception as e:
		print(f"Error in image to text: {e}")
		return hf_image_to_text(imageBase64)

def openai_ocr_image_to_text(imageBase64: str):
	try:
		response = openai_client.chat.completions.create(
			model="gpt-4.1-mini",
			messages=[
				{
					"role": "user",
					"content": [
						{"type": "text", "text": "Convert the image to text. If there are different sections of texts with arrows or lines between them, mention which note it connects to. Return your response as JSON."},
						{
							"type": "image_url",
							"image_url": {
								"url": imageBase64,
							},
						},
					],
				}
			],
			max_tokens=800,
			response_format={ "type": "json_schema", "json_schema": {
				"name": "ocr_notes",
				"description": "Fetches the notes from the image",
				"strict": True,
				"schema": {
					"type": "object",
					"properties": {
						"notes": {
							"type": "array",
							"items": {
								"type": "object",
								"properties": {
									"text": {
										"type": "string",
										"description": "The text content of the note"
									},
									"id": {
										"type": "integer",
										"description": "Unique identifier for the note"
									},
									"relatesToIds": {
										"type": "array",
										"items": {
											"type": "integer"
										},
										"description": "IDs of related notes that this note connects to"
									}
								},
								"required": ["text", "id", "relatesToIds"],
								"additionalProperties": False
							}
						},
						"overall_img_description": {
							"type": "string",
							"description": "Brief summary of the image content in 15 words or less"
						}
					},
					"required": ["notes", "overall_img_description"],
					"additionalProperties": False
				},
			} }
		)
		content = response.choices[0].message.content
		return json.loads(content)
	except Exception as e:
		print(f"Error in image to text: {e}")
		return hf_image_to_text(imageBase64)

def format_ocr_json_to_string(ocr_json: dict) -> str:
    """
    Converts OCR JSON result to a readable string format.
    
    Args:
        ocr_json: Dictionary containing OCR results with 'overall_img_description' and 'notes'
        
    Returns:
        A formatted string representation of the OCR results
    """
    try:
        # Extract the overall summary
        overall_summary = ocr_json.get("overall_img_description", "Unknown content")
        
        # Start building the result string
        result = f"Overall Writing about {overall_summary} with notes inside: "
        
        # Create a dictionary to look up note texts by ID for relation references
        note_texts_by_id = {note["id"]: note["text"] for note in ocr_json.get("notes", [])}
        
        # Process each note
        for note in ocr_json.get("notes", []):
            # Add the note text
            result += f"\nNote Text: {note['text']}"
            
            # Add related notes if any
            related_ids = note.get("relatesToIds", [])
            if related_ids:
                related_texts = []
                for related_id in related_ids:
                    if related_id in note_texts_by_id:
                        # Use the first few words of the related note as a title
                        title = note_texts_by_id[related_id].split()[:3]
                        title = " ".join(title) + "..."
                        related_texts.append(title)
                
                if related_texts:
                    result += f"(Links to: {', '.join(related_texts)})"
        
        return result
    except Exception as e:
        print(f"Error formatting OCR JSON: {e}")
        return json.dumps(ocr_json)


def hf_image_to_text(file_data: str):
	try:
		API_URL = "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-large"
		headers = {"Authorization": f"Bearer {os.getenv('HUGGINGFACE_API_KEY', '')}"}
		
		# Remove data URL prefix if present
		if file_data.startswith('data:'):
			file_data = file_data.split(',')[1]
		
		# Convert base64 string to bytes
		image_bytes = base64.b64decode(file_data)
		
		response = requests.post(API_URL, headers=headers, data=image_bytes)
		result = response.json()
		
		if 'error' in result:
			raise Exception(f"Hugging Face API error: {result['error']}")
		
		print("TEXT: ", result[0]['generated_text'])
			
		return result[0]['generated_text'] if isinstance(result, list) else result
	except Exception as e:
		print("HUF ERROR: ", e)
		return "Image"

def image_matches_instruction(imageBase64: str, instruction: str):
	try:
		response = openai_client.chat.completions.create(
			model="gpt-4.1-mini",
			messages=[
				{
					"role": "user",
					"content": [
						{"type": "text", "text": f"Does this image match the instruction: {instruction}? Analyze and return your response as JSON."},
						{
							"type": "image_url",
							"image_url": {
								"url": imageBase64,
							},
						},
					],
				}
			],
			max_tokens=800,
			response_format={ "type": "json_schema", "json_schema": {
				"name": "ocr_notes",
				"description": "Fetches the notes from the image",
				"strict": True,
				"schema": {
					"type": "object",
					"properties": {
						"matches": {
							"type": "boolean",
							"description": "Whether the image matches the given instruction"
						},
						"explanation": {
							"type": "string",
							"description": "Explanation of why the image does or does not match the instruction"
						}
					},
					"required": ["matches", "explanation"],
					"additionalProperties": False
				},
			} }
		)
		content = response.choices[0].message.content
		return json.loads(content)
	except Exception as e:
		print(f"Error in image to text: {e}")
		return hf_image_to_text(imageBase64)