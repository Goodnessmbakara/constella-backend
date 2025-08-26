import traceback
import time
from db.models.constella.constella_retry_queue import RetryQueue
from ai.embeddings import create_embedding, create_file_embedding
from utils.constella.files.file_base64 import clean_base64
from utils.constella.files.s3.s3 import upload_file_bytes_to_s3
from db.weaviate.operations.general import insert_record
from db.weaviate.records.note import WeaviateNote
from pymongo.errors import ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure

def handle_mongodb_connection_error(func_name, entry_id, error, max_retries=3):
	"""Handle MongoDB connection errors with exponential backoff"""
	if isinstance(error, (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure)):
		print(f"MongoDB connection error in {func_name} for entry {entry_id}: {str(error)}")
		
		# For MongoDB connection issues, we want to retry but with a delay
		for attempt in range(max_retries):
			try:
				delay = (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
				print(f"Waiting {delay} seconds before retry attempt {attempt + 1}/{max_retries}")
				time.sleep(delay)
				
				# Try to test the connection
				from db.mongodb import client
				client.admin.command('ping')
				print(f"MongoDB connection restored on attempt {attempt + 1}")
				return True
				
			except Exception as retry_error:
				if attempt == max_retries - 1:
					print(f"All MongoDB connection retry attempts failed: {retry_error}")
					return False
				continue
	
	return False

def process_insert_record(entry_id: str, parameters: dict):
	"""Process an insert record retry attempt"""
	try:		
		record = parameters['record']
		tenant_name = parameters['tenant_name']
		
		# Create vector
		if not record.get("fileData", ""):
			record["vector"] = create_embedding(record.get("title", ""))
		else:
			record["fileData"] = clean_base64(
				record.get("fileData", ""), 
				record.get("fileType", "not existing")
			)
			# Create vector for file data
			record["vector"] = create_file_embedding(
				record.get("fileData", ""),
				record.get("fileType", "not existing"),
				record.get("fileText", "")
			)
			# Upload to S3
			url = upload_file_bytes_to_s3(
				tenant_name,
				record.get("fileData", ""),
				record.get("uniqueid", ""),
				record.get("fileType", "")
			)
			record["fileData"] = url

		# Set device info
		record["lastUpdateDevice"] = parameters.get('device_type', '')
		record["lastUpdateDeviceId"] = parameters.get('device_id', '')

		# Insert record
		insert_record(tenant_name, WeaviateNote.from_rxdb(record))
		
		# If successful, delete the retry entry
		RetryQueue.delete(entry_id)
		print(f"Successfully processed retry entry {entry_id}")
		
	except (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure) as mongo_error:
		print(f"MongoDB connection error processing retry entry {entry_id}: {str(mongo_error)}")
		
		# Try to handle the MongoDB connection error
		if handle_mongodb_connection_error("process_insert_record", entry_id, mongo_error):
			# If connection was restored, retry the operation once
			try:
				insert_record(tenant_name, WeaviateNote.from_rxdb(record))
				RetryQueue.delete(entry_id)
				print(f"Successfully processed retry entry {entry_id} after connection recovery")
				return
			except Exception as retry_error:
				print(f"Retry after connection recovery failed for entry {entry_id}: {str(retry_error)}")
		
		# Handle as a regular retry if MongoDB connection couldn't be restored
		handle_retry_queue_error(entry_id, mongo_error)
		
	except Exception as e:
		print(f"Error processing retry entry {entry_id}: {str(e)}")
		traceback.print_exc()
		handle_retry_queue_error(entry_id, e)

def handle_retry_queue_error(entry_id: str, error: Exception):
	"""Handle retry queue errors with proper retry logic"""
	try:
		# Get the entry to check retries left
		entry = RetryQueue.get_entry(entry_id)
		if entry and entry.get('retries_left', 0) > 1:
			# Update retries left
			new_retries = entry['retries_left'] - 1
			print(f"Retrying entry {entry_id} with {new_retries} retries left")
			RetryQueue.create(entry['function_name'], entry['parameters'], new_retries)
		else:
			print(f"No more retries left for entry {entry_id}")
		
		# Delete the current entry
		RetryQueue.delete(entry_id)
		
	except (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure) as mongo_error:
		print(f"MongoDB error while handling retry queue error for entry {entry_id}: {str(mongo_error)}")
		# In this case, we can't safely delete or update the entry, so we'll let it be retried later
		
	except Exception as cleanup_error:
		print(f"Error during retry queue cleanup for entry {entry_id}: {str(cleanup_error)}")
		traceback.print_exc()

def process_retry_queue(batch_size: int = 100):
	"""Process pending entries in the retry queue"""
	try:
		pending_entries = RetryQueue.get_pending_retries(batch_size)
		
		if not pending_entries:
			print("No pending retry entries to process")
			return
		
		print(f"Processing {len(pending_entries)} retry entries")
		
		for entry in pending_entries:
			try:
				function_name = entry.get('function_name')
				entry_id = str(entry.get('_id'))
				parameters = entry.get('parameters', {})
				
				# Switch statement for different function types
				if function_name == 'note_route_insert_record':
					print(f"Processing retry entry {entry_id} for function {function_name}")
					process_insert_record(entry_id, parameters)
				else:
					print(f"Unknown function type in retry queue: {function_name}")
					RetryQueue.delete(entry_id)
					
			except Exception as entry_error:
				print(f"Error processing individual retry entry: {str(entry_error)}")
				traceback.print_exc()
				# Continue processing other entries
				continue
				
	except (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure) as mongo_error:
		print(f"MongoDB connection error while fetching retry queue entries: {str(mongo_error)}")
		
		# Try to handle the connection error
		if handle_mongodb_connection_error("process_retry_queue", "batch", mongo_error):
			print("Connection restored, retry queue processing can be attempted again")
		else:
			print("Could not restore MongoDB connection, retry queue processing will be skipped this round")
			
	except Exception as e:
		print(f"Unexpected error in process_retry_queue: {str(e)}")
		traceback.print_exc()
