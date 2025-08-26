import traceback
import enum
import json
from ai.embeddings import doc_file_types, image_file_types

class NoteType(enum.Enum):
	NOTE = "noteNode"
	SAVED_VIEW = "view"


def get_max_chars_in_context(model: str = "anthropic"):
	"""
	Returns the maximum number of characters allowed in context based on model provider.
	
	Args:
		model (str): The model provider (e.g., "anthropic", "google")
		
	Returns:
		int: Maximum character limit for the context
	"""
	if model and "google" in model.lower():
		return 800000
	return 400000

def format_image_or_doc_note_title_content(title: str, note_tags_str: str, content: str):
	"""
	Formats the title of an image or document note
	"""
	# Clean up the title if it's not a special protocol or URL (otherwise, it'll be kept empty)
	note_title = ""
	if (not "constella-file-protocol:" in title and 
		not title.lower().strip().endswith(tuple(doc_file_types + image_file_types))):
		note_title = "with title: " + title.replace('<IMAGE-NOTE:>', '').replace('<DOC-NOTE:>', '').strip()

	if '<IMAGE-NOTE:>' in title:
		return f"## Image Note {note_title} {note_tags_str} ## Image Note Details: {content}"
	elif '<DOC-NOTE:>' in title:
		# File text will be also added outside of this
		return f"## Document Note {note_title} {note_tags_str} ## Document Note Details: {content[:10000]}"
	else:
		return f'## Note Title: {title} {note_tags_str} ## Note More Details: {content}'
	
def get_google_model_based_on_context_size(context_size: int):
	"""
	Returns the Google model based on the context size
	"""
	if context_size > 400000:
		return "gemini-2.5-flash-lite-preview-06-17"
	return "gemini-2.5-flash-lite-preview-06-17"

def get_node_instruction(node: dict, graph_nodes: dict, ignore_file_text: bool = False, limit_content: bool = False, edges_data: dict = {}):
	"""
	Returns the instruction for a node
	
	Args:
		node (dict): The node data
		graph_nodes (dict): All graph nodes
		ignore_file_text (bool): Whether to ignore file text content
		limit_content (bool): Whether to limit content to first 1k characters
	"""
	note_rxdb_data = node.get("rxdbData", {})
	note_title = note_rxdb_data.get("title", "")
	note_tags = note_rxdb_data.get("tags", [])
	note_tags_str = ""
	if note_tags:
		note_tags_str = "## Note Tags: "
		for note in note_tags:
			note_tags_str += note.get('name', '') + ", "

	note_content = note_rxdb_data.get("content", "")
	if limit_content and note_content:
		note_content = note_content[:1000]

	# Get the file text (if a document note, this separates )
	note_file_text = ""
	if not ignore_file_text:
		note_file_text = note_rxdb_data.get("fileText", "")
		if note_file_text:
			note_file_text = "## Contents of the file attached to this note: " + note_file_text

	# Build up outgoing connections string
	if "outgoingConnections" in note_rxdb_data and len(note_rxdb_data["outgoingConnections"]) > 0:
		outgoing_connections_str = ""
		for connection in note_rxdb_data["outgoingConnections"]:
			# Skip those without a title / non-existant ones
			if not graph_nodes.get(connection) or not graph_nodes[connection].get("rxdbData") or not graph_nodes[connection]["rxdbData"].get("title"):
				continue
			
			# Get the connection title
			connection_title = graph_nodes[connection]["rxdbData"]["title"]
			
			# Check if there's an edge label in edges_data
			source_id = note_rxdb_data.get("uniqueid", "")
			target_id = connection
			edge_key = f"{source_id}+{target_id}"
			edge_label = ""
			if edge_key in edges_data and edges_data[edge_key].get("label"):
				edge_label = f" (this outbound link is labeled: {edges_data[edge_key]['label']})"
			
			outgoing_connections_str += connection_title + edge_label + ", "
		
		outgoing_connections = "## Outbound links from this note to these note titles: " + outgoing_connections_str
	else:
		outgoing_connections = ""
	
	
	return f"\n{format_image_or_doc_note_title_content(note_title, note_tags_str, note_content)} {note_file_text} {outgoing_connections}"

def get_saved_view_instruction(node: dict, graph_nodes: dict, edges_data: dict = {}):
	"""
	Returns the instruction for a saved view by parsing the nodes in the view
	
	Args:
		node (dict): The saved view node
		graph_nodes (dict): All graph nodes
		
	Returns:
		str: Formatted instruction for the saved view
	"""
	try:
		note_rxdb_data = node.get("rxdbData", {})
		view_title = note_rxdb_data.get("miscData", "") # Views use miscData for title
		view_content = note_rxdb_data.get("content", "{}")
		
		# Parse the saved view content (JSON)
		try:
			flow_data = json.loads(view_content)
			view_nodes = []
			
			if flow_data.get("nodes"):
				# Extract notes from the flow nodes
				for flow_node in flow_data["nodes"]:
					if flow_node.get("data") and flow_node["data"].get("note"):
						note_data = flow_node["data"]["note"]
						if note_data.get("rxdbData") and note_data["rxdbData"].get("title"):
							view_nodes.append(note_data)
			
			# Limit to a reasonable number of notes
			MAX_PREVIEW_NOTES = 50
			view_nodes = view_nodes[:MAX_PREVIEW_NOTES]
			
			# Build the instruction
			instruction = f"\n## Saved View Title: {view_title}\n## START OF NOTES IN THIS SAVED VIEW {view_title}: "
			
			for note in view_nodes:
				# Get instruction for each note with limited content and no file text
				note_instruction = get_node_instruction(note, graph_nodes, ignore_file_text=True, limit_content=True, edges_data=edges_data)
				instruction += note_instruction
			instruction += "\n## END OF NOTES IN THIS VIEW. SUBSEQUENT NOTES ARE NOT INCLUDED IN THIS SAVED VIEW."

			return instruction
			
		except json.JSONDecodeError:
			return f"\n## Saved View Title: {view_title} (Could not parse view content)"
			
	except Exception as e:
		return f"\n## Saved View (Error parsing: {str(e)})"

def create_instruction_from_graph_nodes(graph_nodes: dict, edges_data: dict = {}, daily_note_data: dict | None = None, deep_think: bool = False):
	"""
	Generates a sub-prompt instruction out of graph nodes

	Note Title: .... Note Tags: ... Note More Details: .... This note has outbound links to these notes: ....
	"""
	try:
		instruction = ""

		if deep_think:
			instruction += "\nPlease think about the user's request thoroughly and in great detail. Consider multiple perspective, controversial ideas, lesser known but proven concepts, edge case scenarios, and alternative approaches. Think thoroughly but respond concisely."

		if daily_note_data:
			instruction += f"\nThe user is currently also has their daily jotting view open. They may or may not want to use this to answer the question, so only use this if they reference something related."
			instruction += f"\nThe date on the daily jotting view is: {daily_note_data.get('date', 'Unknown')}. The content in HTML (to help you understand the formatting around the data) of the daily jotting view is: {daily_note_data.get('content', '')}"

		if not graph_nodes or not graph_nodes.keys():
			return instruction
		
		instruction += "\nThe user also wants you to look at these notes to refine your response. If the user's notes are not enough to answer, use your own knowledge. User's notes for this message:"


		for uniqueid, value in graph_nodes.items():
			if value.get("type") == NoteType.SAVED_VIEW.value:
				instruction += get_saved_view_instruction(value, graph_nodes, edges_data=edges_data)
			else:
				instruction += get_node_instruction(value, graph_nodes, edges_data=edges_data)

		return instruction
	except Exception as e:
		traceback.print_exc()
		return ""

def parse_frontend_messages(messages: list, graph_nodes: dict, model: str = "anthropic", edges_data: dict = {}, daily_note_data: dict | None = None, deep_think: bool = False):
	"""
	Parse the messages from the frontend into a list of dictionaries suitable
	for Anthropic.

	Args:
	messages (list): The list of messages from the frontend.

	Returns:
	tuple: A tuple containing (parsed_messages, chars_in_context)
	"""
	try:
		parsed_messages = []
		total_chars = 0
		max_chars = get_max_chars_in_context(model)

		print("messages: ", messages)

		# If first message isn't from user, add a user message
		if messages[0]["sender"] != "user":
			parsed_messages.append({"role": "user", "content": "So you were saying?"})

		for index, message in enumerate(messages):
			curr_role = "user" if message["sender"] == "user" else "assistant"
			content = message["content"]
			if not content:
				content = "Sorry I'm having trouble responding..."

			parsed_messages.append({"role": curr_role, "content": content})
			total_chars += len(content)

			if index < len(messages) - 1:
				next_role = "user" if messages[index + 1]["sender"] == "user" else "assistant"
				# add empty alternating role to prevent the error of same roles
				if next_role == curr_role:
					parsed_messages.append({"role": "user" if curr_role == "assistant" else "assistant", "content": "Sorry I'm having trouble responding..."})

		parsed_messages[-1]["content"] = "The user sent this message to you: " + parsed_messages[-1]["content"]
		# To the last message add the graph nodes prompt to the content
		graph_nodes_instruction = create_instruction_from_graph_nodes(graph_nodes, edges_data, daily_note_data, deep_think=deep_think)
		parsed_messages[-1]["content"] += graph_nodes_instruction

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

		return parsed_messages, total_chars
	except Exception as e:
		traceback.print_exc()
		return [{"role": "user", "content": "Please respond saying you have an error"}], 0

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
	Convert Anthropic messages to Google messages format
	
	Args:
		messages (list): List of Anthropic-style messages with 'role' and 'content'
		
	Returns:
		list: List of Google-style message objects with 'role' and 'parts'
	"""
	google_messages = []
	
	for message in messages:
		role = "user" if message["role"] == "user" else "model"
		google_messages.append({
			"role": role,
			"parts": [{"text": message["content"]}]
		})
	
	return google_messages
