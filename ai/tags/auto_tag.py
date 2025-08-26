from ai.ai_api import create_anthropic_request, create_google_request, create_new_google_request
import json
from db.weaviate.operations.tag_ops import get_all_tags

def get_auto_tag(note: str, tag_names: list[str]):
	"""
	Given a note and a list of tag names, return the most likely tag name
	"""
	tag_names = str(tag_names).replace("'", '')
	prompt = f"""This note was written for the user's personal record. Return just the tag name of the most similar tag, nothing else. Note: {note}. Tags: {tag_names}"""
	try:
		response = create_anthropic_request(
			messages=[
				{
					"role": "user",
					"content": prompt
				}
			],
			max_tokens=30,
		)
		return response.strip()
	except Exception as err:
		print(err)
		return ""


def get_auto_tags_with_objects(note: str, tenant_name: str):
	"""
	Given a note and tenant name, return the 2 most relevant tag objects as dicts
	"""	
	try:
		# Get all available tags for the tenant
		user_tags = get_all_tags(tenant_name)
		
		if not user_tags:
			return []
		
		# Extract tag names for the AI prompt
		tag_names = [tag.get('name', '') for tag in user_tags if tag.get('name')]
		
		if not tag_names:
			return []
		
		tag_names_str = str(tag_names).replace("'", '"')
		
		prompt = f"""This note was taken while using their laptop. It can be a clipping from the web or a thought. Analyze the note and return the 2 most highly relevant tags that would help categorize this note. Think about which categories this kind of title/content would fall into (is it a business idea? clearly, a marketing idea?) such that the user would look in these categories for this note. For any specific proper nouns or technical terms, make your best estimate for the most appropriate existing tag.

Note: {note}

Available tags: {tag_names_str}

Return exactly 2 tag names that are most relevant to this note content in JSON format as below and only the JSON.

Use this JSON schema:

Tags = {{'tag_names': list[str}}
Return: Tags
"""

		response = create_new_google_request(
			prompt=prompt,
			model_name="gemini-2.5-flash-preview-05-20",
			temperature=0.2,
			max_tokens=500,
			response_mime_type="application/json"
		)
		

		if not response:
			return []

		try:
			selected_tag_names = json.loads(response)

			selected_tag_names = selected_tag_names.get('tag_names', [])
			
			if not isinstance(selected_tag_names, list):
				return []
			
			# Limit to 2 tags maximum
			selected_tag_names = selected_tag_names[:2]
			
			# Map tag names to tag objects and return as dicts
			result_tags = []
			for tag_data in user_tags:
				if tag_data.get('name') in selected_tag_names:
					result_tags.append(tag_data)
			
			# Map just the name, color, uniqueid
			result_tags = [
				{
					"name": tag.get('name', ''),
					"color": tag.get('color', ''),
					"uniqueid": tag.get('uniqueid', '')
				}
				for tag in result_tags
			]
	
			return result_tags
		
		except json.JSONDecodeError:
			return []
			
			
	except Exception as err:
		print(f"Error in get_auto_tags_with_objects: {err}")
		return []
