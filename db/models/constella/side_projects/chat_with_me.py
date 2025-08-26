from db.mongodb import db
from datetime import datetime
from utils.json import parse_json

collection = db['chat_with_me']

class ChatWithMe:
	def __init__(self, tenantName: str, custom_prompt: str = None, api_key: str = None):
		self.tenantName = tenantName
		self.custom_prompt = custom_prompt
		self.api_key = api_key
		self.created_at = datetime.utcnow()
		self.updated_at = datetime.utcnow()

	def save(self):
		result = collection.insert_one(self.__dict__)
		return {"_id": str(result.inserted_id)}

	def update(self):
		"""Update an existing record"""
		self.updated_at = datetime.utcnow()
		collection.update_one({"tenantName": self.tenantName}, {"$set": self.__dict__})
		# Get the updated record to return its _id
		updated_record = collection.find_one({"tenantName": self.tenantName})
		return {"_id": str(updated_record["_id"])} if updated_record else None

	@staticmethod
	def get_by_tenant(tenantName: str):
		return parse_json(collection.find_one({"tenantName": tenantName}))

	@staticmethod
	def get_by_id(id: str):
		"""Get a record by its MongoDB _id"""
		from bson.objectid import ObjectId
		try:
			return parse_json(collection.find_one({"_id": ObjectId(id)}))
		except Exception as e:
			print(f"Error getting ChatWithMe by id: {e}")
			return None

	@staticmethod
	def get_all():
		return [parse_json(item) for item in collection.find({})]

	@staticmethod
	def delete(tenantName: str):
		collection.delete_one({"tenantName": tenantName})

	@staticmethod
	def delete_all():
		collection.delete_many({})