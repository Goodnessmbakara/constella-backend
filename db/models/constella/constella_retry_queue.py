from db.mongodb import db
from datetime import datetime
from bson import ObjectId
from utils.json import parse_json

collection = db['retry_queue']

class RetryQueue:
    def __init__(self, function_name: str, parameters: dict, retries_left: int = 5):
        self.function_name = function_name
        self.parameters = parameters
        self.date_created = datetime.utcnow()
        self.retries_left = retries_left

    @staticmethod
    def create(function_name: str, parameters: dict, retries_left: int = 3):
        print('creating retry queue entry')
        retry_entry = RetryQueue(function_name, parameters, retries_left)
        result = collection.insert_one(retry_entry.__dict__)
        return str(result.inserted_id)

    @staticmethod
    def delete(entry_id: str):
        if not entry_id:
            return
        try:
            collection.delete_one({"_id": ObjectId(entry_id)})
        except Exception as e:
            print('error deleting retry queue entry: ' + str(e))

    @staticmethod
    def get_entry(_id: str, return_object: bool = False):
        entry_data = collection.find_one({"_id": ObjectId(_id)})
        if entry_data:
            if return_object:
                return parse_json(entry_data)
            return entry_data
        return None

    @staticmethod
    def get_pending_retries(limit: int = 10):
        """Get entries that still have retries remaining"""
        entries = collection.find({"retries_left": {"$gt": 0}}).limit(limit)
        return [parse_json(entry) for entry in entries]