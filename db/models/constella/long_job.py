from db.mongodb import db
from datetime import datetime
from utils.json import parse_json
from bson import ObjectId

collection = db['long_jobs']

class LongJob:
	def __init__(self, status: str, results:any, type: str = '', user_id: str = ''):
		self.status = status
		self.results = results
		self.created_at = datetime.utcnow()
		self.type = type
		self.user_id = user_id
	
	@staticmethod
	def insert(status: str, results:any, type: str = '', user_id: str = ''):
		print('inserting long job')
		job = LongJob(status, results, type, user_id)
		result = collection.insert_one(job.__dict__)
		return str(result.inserted_id)

	@staticmethod
	def update_status(job_id: str, status: str, results:any = None):
		if not job_id:
			return
		try:
			print('job_id type: ' + str(type(job_id)))
			job_id = str(job_id)
			
			# Convert any UUID objects in results to strings
			if results and isinstance(results, dict):
				# Handle results array
				if 'results' in results:
					for item in results['results']:
						# Convert UUID in tagIds
						if 'tagIds' in item and item['tagIds']:
							item['tagIds'] = [str(tag_id) for tag_id in item['tagIds']]
						# Convert UUID in tags
						if 'tags' in item and item['tags']:
							for tag in item['tags']:
								if 'uniqueid' in tag and hasattr(tag['uniqueid'], 'hex'):
									tag['uniqueid'] = str(tag['uniqueid'])
						# Convert UUID in uniqueid
						if 'uniqueid' in item and hasattr(item['uniqueid'], 'hex'):
							item['uniqueid'] = str(item['uniqueid'])
						
						# do str on startId and endId
						if 'startId' in item and hasattr(item['startId'], 'hex'):
							item['startId'] = str(item['startId'])
						if 'endId' in item and hasattr(item['endId'], 'hex'):
							item['endId'] = str(item['endId'])
				# Convert any other top-level UUIDs
				for key, value in results.items():
					if hasattr(value, 'hex'):
						results[key] = str(value)
			
			collection.update_one({"_id": ObjectId(job_id)}, {"$set": {"status": status, "results": results}})
		except Exception as e:
			print('error updating long job status: ' + str(e))
			with open('results-error.txt', 'w') as f:
				f.write("RESULTS: " + str(results))

	@staticmethod
	def get_status(_id: str, return_object: bool = False):
		job_data = collection.find_one({"_id": ObjectId(_id)})
		if job_data:
			if return_object:
				return parse_json(job_data)
			return job_data.get("status", '')
		return None
