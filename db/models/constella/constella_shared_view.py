from pymongo import MongoClient
from db.mongodb import db
from datetime import datetime
from utils.json import parse_json
from bson import ObjectId
from utils.constella.files.s3.s3 import sign_url

collection = db['constella_shared_views']

class ConstellaSharedView:
	def __init__(self, sharing_user_email: str, shared_view_data: dict, shared_url: str = None):
		self.sharing_user_email = sharing_user_email
		self.shared_view_data = shared_view_data
		self.shared_url = shared_url
		self.shared_date = datetime.utcnow()

	def save(self):
		result = collection.insert_one(self.__dict__)
		return {
			"_id": str(result.inserted_id),
			"sharing_user_email": self.sharing_user_email,
			"shared_url": self.shared_url,
			"shared_view_data": self.shared_view_data,
			"shared_date": self.shared_date
		}

	@staticmethod
	def get_all():
		found_items = list(collection.find({}))
		# parse json on each item
		for i in range(len(found_items)):
			found_items[i] = parse_json(found_items[i])
		return found_items
	
	@staticmethod
	def get_by_user_id(user_id: str):
		return list(collection.find({"sharing_user_email": user_id}))

	@staticmethod
	def get_by_id(_id: str):
		"""
		Get a shared view by its _id
		while signing any urls in file paths.
		"""
		res = collection.find_one({"_id": ObjectId(_id)})
		if res:
			parsed_json = parse_json(res)
			# For any file paths that contain 'cloudfront', sign the url
			for node in parsed_json.get('shared_view_data', {}).get('nodes', []):
				if node.get('data', {}).get('note', {}).get('rxdbData', {}).get('filePath', ''):
					if 'cloudfront' in node['data']['note']['rxdbData']['filePath']:
						node['data']['note']['rxdbData']['filePath'] = sign_url(node['data']['note']['rxdbData'].get('filePath', ''))
			return parsed_json
		return None

	@staticmethod
	def delete_all():
		collection.delete_many({})

	@staticmethod
	def delete_by_id(_id: str):
		result = collection.delete_one({"_id": ObjectId(_id)})
		return result.deleted_count > 0

	@staticmethod
	def update_by_id(_id: str, update_data: dict):
		"""
		Update a shared view by its _id
		Args:
			_id: string ID of the document to update
			update_data: dictionary containing the fields to update
		Returns:
			True if successful, False if not found
		"""
		result = collection.update_one(
			{"_id": ObjectId(_id)},
			{"$set": update_data}
		)
	
		
		return True if result.matched_count > 0 else False
