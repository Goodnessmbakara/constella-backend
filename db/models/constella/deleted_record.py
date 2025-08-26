from db.mongodb import db
from datetime import datetime, timedelta
from utils.json import parse_json

collection = db['deleted_records']

class DeletedRecord:
	def __init__(self, uniqueid: str, recordType: str, lastModified: datetime, tenantName: str = None, s3_path: str = None):
		self.uniqueid = uniqueid
		self.recordType = recordType
		self.lastModified = lastModified
		self.tenantName = tenantName
		self.s3_path = s3_path

	def save(self):
		collection.insert_one(self.__dict__)

	@staticmethod
	def get_record(uniqueid: str):
		return parse_json(collection.find_one({"uniqueid": uniqueid}))

	@staticmethod
	def get_all():
		return list(collection.find({}))

	@staticmethod
	def delete_all():
		collection.delete_many({})

	@staticmethod
	def get_records_since(tenantName: str = None, timestamp: datetime = None):
		query = {"lastModified": {"$gte": timestamp}}
		if tenantName:
			query["tenantName"] = tenantName
		found_items = list(collection.find(query))
		return [parse_json(item) for item in found_items]
	
	@staticmethod
	def insert_many(records: list):
		"""
		Insert multiple DeletedRecord objects into the collection.
		:param records: List of DeletedRecord objects to insert.
		"""
		records_dicts = [record.__dict__ for record in records]
		collection.insert_many(records_dicts)

	@staticmethod
	def get_old_records_with_s3_path(hours: int = 1):
		"""
		Get records older than specified hours that have non-empty s3_path
		"""
		cutoff_time = datetime.utcnow() - timedelta(hours=hours)
		query = {
			"lastModified": {"$lte": cutoff_time},
			"s3_path": {"$ne": None, "$ne": "", "$exists": True}
		}
		return [parse_json(item) for item in collection.find(query)]
