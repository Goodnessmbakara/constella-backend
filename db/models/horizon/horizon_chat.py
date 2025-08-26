from db.mongodb import db
from datetime import datetime
from utils.json import parse_json
from bson.objectid import ObjectId

# MongoDB collection for storing Horizon chats
collection = db['horizon_chats']

class HorizonChat:
	"""Represents a chat session in Horizon.

	Attributes
	----------
	created : datetime
		Timestamp when the chat was created.
	lastModified : datetime
		Timestamp when the chat was last modified (e.g., a message was added or the title was changed).
	title : str
		User-defined title of the chat.
	messages : list[dict]
		List of message objects, each containing at minimum a ``role`` and ``content`` key.
	"""

	def __init__(self, title: str, tenant_name: str, messages: list[dict] | None = None):
		self.created = datetime.utcnow()
		self.lastModified = self.created
		self.title = title
		self.tenantName = tenant_name
		self.messages = messages or []

	def save(self) -> dict:
		"""Insert the chat into MongoDB and return the persisted record as JSON-serialisable dict."""
		result = collection.insert_one(self.__dict__)
		return parse_json(collection.find_one({"_id": result.inserted_id}))

	@staticmethod
	def add_message(chat_id: str, tenant_name: str, message: dict) -> dict | None:
		"""Append a message to the chat and update ``lastModified`` enforcing tenant isolation."""
		try:
			collection.update_one(
				{"_id": ObjectId(chat_id), "tenantName": tenant_name},
				{"$push": {"messages": message}, "$set": {"lastModified": datetime.utcnow()}}
			)
			return parse_json(collection.find_one({"_id": ObjectId(chat_id), "tenantName": tenant_name}))
		except Exception as e:
			print(f"Error adding message to HorizonChat {chat_id}: {e}")
			return None

	@staticmethod
	def rename(chat_id: str, tenant_name: str, new_title: str) -> dict | None:
		"""Rename a chat and update ``lastModified`` enforcing tenant isolation."""
		try:
			collection.update_one(
				{"_id": ObjectId(chat_id), "tenantName": tenant_name},
				{"$set": {"title": new_title, "lastModified": datetime.utcnow()}}
			)
			return parse_json(collection.find_one({"_id": ObjectId(chat_id), "tenantName": tenant_name}))
		except Exception as e:
			print(f"Error renaming HorizonChat {chat_id}: {e}")
			return None

	@staticmethod
	def search_by_title(query: str, tenant_name: str) -> list[dict]:
		"""Search chats whose title matches the supplied query for a specific tenant (case-insensitive substring match)."""
		cursor = collection.find({
			"tenantName": tenant_name,
			"title": {"$regex": query, "$options": "i"}
		})
		return [parse_json(item) for item in cursor]

	@staticmethod
	def get(chat_id: str, tenant_name: str) -> dict | None:
		"""Retrieve a chat by its ``_id`` and tenant."""
		try:
			return parse_json(collection.find_one({"_id": ObjectId(chat_id), "tenantName": tenant_name}))
		except Exception:
			return None

	@staticmethod
	def delete(chat_id: str, tenant_name: str):
		"""Delete a chat by its ``_id`` and tenant."""
		try:
			collection.delete_one({"_id": ObjectId(chat_id), "tenantName": tenant_name})
		except Exception as e:
			print(f"Error deleting HorizonChat {chat_id}: {e}")
