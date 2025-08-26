from pymongo import MongoClient
from db.mongodb import db
from datetime import datetime
from utils.json import parse_json

collection = db['constella_auth']

class ConstellaAuth:
	def __init__(self, authReqId: str, auth_user_id: str, auth_email: str):
		self.authReqId = authReqId
		self.auth_user_id = auth_user_id
		self.auth_email = auth_email

	def save(self):
		collection.insert_one(self.__dict__)

	@staticmethod
	def get_auth_info(authReqId: str):
		return parse_json(collection.find_one({"authReqId": authReqId}))

	@staticmethod
	def get_by_user_id(auth_user_id: str):
		return parse_json(collection.find_one({"auth_user_id": auth_user_id}))

	@staticmethod
	def get_by_email(auth_email: str):
		return parse_json(collection.find_one({"auth_email": auth_email}))
	
	@staticmethod
	def update_one(authReqId: str, auth_user_id: str, auth_email: str):
		collection.update_one({"authReqId": authReqId}, {"$set": {"auth_user_id": auth_user_id, "auth_email": auth_email}})

	@staticmethod
	def get_all():
		return list(collection.find({}))
