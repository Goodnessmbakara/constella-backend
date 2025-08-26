from pymongo import MongoClient
#from db.mongodb import db
from datetime import datetime
from utils.json import parse_json
from bson import ObjectId

def get_collection():
    """Lazy loading of MongoDB collection to avoid circular imports"""
    from db.mongodb import db
    return db['constella_feature_requests']

class ConstellaFeatureRequest:
	def __init__(self, request_text: str, ip_address: str):
		self.request_text = request_text
		self.ip_address = ip_address
		self.numb_votes = 1

	def save(self):
		collection = get_collection()
		result = collection.insert_one(self.__dict__)
		return {
			"_id": str(result.inserted_id),
			"request_text": self.request_text,
			"ip_address": self.ip_address,
			"numb_votes": self.numb_votes,
			"status": "voting", # voting, in_progress, completed
		}

	@staticmethod
	def get_all():
		collection = get_collection()
		found_items = list(collection.find({}))
		# parse json on each item
		for i in range(len(found_items)):
			found_items[i] = parse_json(found_items[i])
		return found_items
	
	@staticmethod
	def get_by_ip(ip_address: str):
		collection = get_collection()
		return list(collection.find({"ip_address": ip_address}))
	
	@staticmethod
	def adjust_votes(_id: str, vote_change: int):
		collection = get_collection()
		collection.update_one({"_id": ObjectId(_id)}, {"$inc": {"numb_votes": vote_change}})

	@staticmethod
	def delete_all():
		collection = get_collection()
		collection.delete_many({})