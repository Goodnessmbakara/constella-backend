# General Milvus operations equivalent to Weaviate operations
import uuid
from db.milvus.milvus_client import client as milvus_client
from db.weaviate.records.general_record import GeneralWeaviateRecord
from db.weaviate.records.note import WeaviateNote
from db.weaviate.records.tag import WeaviateTag
from db.weaviate.records.misc import WeaviateMisc
from db.weaviate.records.note_body import WeaviateNoteBody
from db.weaviate.records.daily_note import WeaviateDailyNote
from constants import default_query_limit
from db.models.constella.deleted_record import DeletedRecord
from datetime import datetime, timedelta
import traceback
import json
from typing import List, Dict, Any, Optional
import sentry_sdk
from ai.embeddings import our_embedding_dimension, create_our_embedding
import time
from pymongo.errors import ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure

def generate_vector_for_milvus_record(milvus_record: Dict[str, Any]) -> List[float]:
	"""
	Generate a vector for a Milvus record using our custom embedding service.
	Extracts text from title, fileText, or content fields and creates an embedding.
	"""
	text_to_embed = ""
	if milvus_record.get("title"):
		text_to_embed = milvus_record["title"]
	elif milvus_record.get("fileText"):
		text_to_embed = milvus_record["fileText"][:3000]
	elif milvus_record.get("content"):
		text_to_embed = milvus_record["content"][:3000]

	# Create embedding using our Qwen3 embedding service
	if text_to_embed:
		return create_our_embedding(text_to_embed)
	else:
		# if nothing to embed, add empty default vector
		return [0] * our_embedding_dimension

# **** Helper utilities for tag handling ****

def process_record_for_insert(record: Dict[str, Any]) -> Dict[str, Any]:
	"""
	Prepare a Milvus record for insertion.

	Makes a shallow copy of the provided record dictionary and ensures the
	``tags`` field (if present) is stored as a JSON string which is the format
	expected by the Milvus VARCHAR column that represents the tag list.

	This prevents issues where lists / dicts are inserted directly, which would
	violate the schema and cause runtime errors.
	"""
	processed = record.copy()

	# Convert ``tags`` list/dict -> JSON string. Leave as-is if it is already a
	# string or is ``None``.
	if "tags" in processed and processed["tags"] is not None and not isinstance(processed["tags"], str):
		try:
			processed["tags"] = json.dumps(processed["tags"])
		except Exception:
			# Fallback to an empty JSON array string if serialization fails
			processed["tags"] = "[]"

	return processed


def _process_tags_in_results(results: List[Dict[str, Any]]):
	"""In-place conversion of the ``tags`` field from JSON string back to Python.

	Mutates the supplied list of result dictionaries so that any ``tags``
	values stored as JSON strings are deserialized back into their original
	Python representation (list / dict). If a value cannot be decoded, it is
	left unchanged.
	"""
	for res in results or []:
		if res and isinstance(res.get("tags"), str):
			try:
				res["tags"] = json.loads(res["tags"])
			except Exception:
				res["tags"] = []
				# Leave the value untouched if it isn't valid JSON
				pass

# **** Insertion ****

def insert_record(tenant_name: str, record: GeneralWeaviateRecord):
	"""
	Insert a record into the Milvus collection.
	:param tenant_name: The tenant to insert into.
	:param record: The record to insert.
	"""
	try:
		milvus_dict = process_record_for_insert(record.to_milvus_dict(tenant_name))

		# Generate vector if not already present
		if "vector" not in milvus_dict or not milvus_dict["vector"] or len(milvus_dict["vector"]) != our_embedding_dimension:
			milvus_dict["vector"] = generate_vector_for_milvus_record(milvus_dict)
		
		if not milvus_dict.get("uniqueid"):
			milvus_dict["uniqueid"] = str(uuid.uuid4())
		
		# Upsert the record (insert or update if exists)
		res = milvus_client.client.upsert(
			collection_name=milvus_client.collection_name,
			data=[milvus_dict]
		)
		
		return milvus_dict["uniqueid"]
	except Exception as e:
		print(f'Error in Milvus insert_record: {e}')
		traceback.print_exc()
		raise Exception("Failed to insert record into Milvus")

def upsert_records(tenant_name: str, records: list[GeneralWeaviateRecord], type='note', long_job_id='', last_update_device='', last_update_device_id=''):
	"""
	Upsert records into the Milvus collection using batch upsert.
	:param tenant_name: The tenant to upsert into.
	:param records: A list of records to upsert.
	:param type: Type of records being upserted.
	:param long_job_id: Long job ID for tracking.
	:param last_update_device: Device that made the last update.
	:param last_update_device_id: Device ID that made the last update.
	"""
	try:
		if not records:
			return
			
		milvus_data = []
		for record in records:
			if hasattr(record, 'to_milvus_dict'):
				milvus_dict = process_record_for_insert(record.to_milvus_dict(tenant_name))
				milvus_dict["lastUpdateDevice"] = last_update_device
				milvus_dict["lastUpdateDeviceId"] = last_update_device_id
				
				# Generate vector if not already present
				if "vector" not in milvus_dict or not milvus_dict["vector"] or len(milvus_dict["vector"]) != our_embedding_dimension:
					milvus_dict["vector"] = generate_vector_for_milvus_record(milvus_dict)
				
				milvus_data.append(milvus_dict)
		
		if milvus_data:
			milvus_client.client.upsert(
				collection_name=milvus_client.collection_name,
				data=milvus_data
			)
			
	except Exception as e:
		print(f'Error in Milvus upsert_records: {e}')    
		traceback.print_exc()
		raise e

# **** Updating ****

def update_record_vector_raw(tenant_name: str, unique_id: str, new_vector: List[float], metadata_updates: Dict = None):
	"""
	Update the vector of a specific record in Milvus.
	"""
	try:
		# Get the existing record first
		existing_record = get_record_by_id(tenant_name, unique_id)
		if not existing_record:
			return None
			
		# Update the record with new vector and metadata
		update_data = {
			"uniqueid": unique_id,
			"vector": new_vector,
			"tenantName": tenant_name
		}
		
		# Merge existing data with updates
		update_data.update(existing_record)
		if metadata_updates:
			update_data.update(metadata_updates)
			
		# Process the data to ensure tags are properly formatted
		update_data = process_record_for_insert(update_data)
			
		milvus_client.client.upsert(
			collection_name=milvus_client.collection_name,
			data=[update_data]
		)
		
	except Exception as e:
		print(f'Error in Milvus update_record_vector_raw: {e}')
		raise

def update_record_vector(tenant_name: str, unique_id: str, new_vector: List[float], metadata_updates: Dict = None):
	"""
	Update the vector of a specific record with error handling.
	"""
	try:
		update_record_vector_raw(tenant_name, unique_id, new_vector, metadata_updates)
	except Exception as e:
		print(f'Error in Milvus update_record_vector: {e}')
		return None

def update_record_metadata_raw(tenant_name: str, unique_id: str, metadata_updates: Dict):
	"""
	Update the metadata of a specific record in Milvus.
	"""
	try:
		# Get the existing record first
		existing_record = get_record_by_id(tenant_name, unique_id)
		if not existing_record:
			return None
			
		# Update the record with new metadata
		update_data = {
			"uniqueid": unique_id,
			"tenantName": tenant_name
		}
		
		# Merge existing data with updates
		update_data.update(existing_record)
		update_data.update(metadata_updates)
		
		# Remove vector from metadata_updates if it exists
		if 'vector' in metadata_updates:
			metadata_updates.pop('vector')
			
		# Process the data to ensure tags are properly formatted
		update_data = process_record_for_insert(update_data)
			
		milvus_client.client.upsert(
			collection_name=milvus_client.collection_name,
			data=[update_data]
		)
		
	except Exception as e:
		print(f'Error in Milvus update_record_metadata_raw: {e}')
		raise

def update_record_metadata(tenant_name: str, unique_id: str, metadata_updates: Dict):
	"""
	Update the metadata of a specific record with error handling.
	"""
	try:
		update_record_metadata_raw(tenant_name, unique_id, metadata_updates)
		return 200
	except Exception as e:
		print(f'Error in Milvus update_record_metadata: {e}')
		return None

# **** Deletion ****

def delete_record(tenant_name: str, unique_id: str, record_type: str = "note", s3_path: str = None):
	"""
	Delete a specific record from the Milvus collection.
	"""
	try:
		milvus_client.client.delete(
			collection_name=milvus_client.collection_name,
			filter=f'uniqueid == "{unique_id}" and tenantName == "{tenant_name}"'
		)
		
		# Note: DeletedRecord is handled by the Weaviate operation
		
	except Exception as e:
		print(f'Error in Milvus delete_record: {e}')
		traceback.print_exc()

def delete_records_by_ids(tenant_name: str, id_list: List[str], record_type: str = "note", s3_paths: List[str] = None):
	"""
	Delete multiple records from the Milvus collection by their IDs.
	"""
	try:
		if not id_list:
			return True
			
		# Create filter expression for multiple IDs
		id_filter = " or ".join([f'uniqueid == "{uid}"' for uid in id_list])
		full_filter = f'({id_filter}) and tenantName == "{tenant_name}"'
		
		milvus_client.client.delete(
			collection_name=milvus_client.collection_name,
			filter=full_filter
		)
		
		return True
		
	except Exception as e:
		print(f'Error in Milvus delete_records_by_ids: {e}')
		traceback.print_exc()
		return False

def delete_all_records(tenant_name: str):
	"""
	Delete all records for a specific tenant in Milvus.
	"""
	try:
		milvus_client.client.delete(
			collection_name=milvus_client.collection_name,
			filter=f'tenantName == "{tenant_name}"'
		)
		
	except Exception as e:
		print(f'Error in Milvus delete_all_records: {e}')
		traceback.print_exc()

# **** Querying ****

def query_by_vector(tenant_name: str, query_vector: List[float], top_k: int = default_query_limit, similarity_setting: float = 0.5, include_vector: bool = False):
	"""
	Perform a vector similarity search in Milvus.
	"""
	try:
		# Convert similarity setting (assumed to be in [0, 1]) to COSINE similarity range [-1, 1].
		# A similarity of 1.0 becomes a COSINE score of 1.0.
		# A similarity of 0.5 becomes a COSINE score of 0.0.
		# A similarity of 0.0 becomes a COSINE score of -1.0.
		distance_threshold = (2 * similarity_setting) - 1
		
		search_params = {
			"metric_type": "COSINE",
			"params": {"radius": distance_threshold, "range_filter": 1.0}
		}
		
		results = milvus_client.client.search(
			collection_name=milvus_client.collection_name,
			data=[query_vector],
			anns_field="vector",
			search_params=search_params,
			limit=top_k,
			filter=f'tenantName == "{tenant_name}"',
			output_fields=["*"] if include_vector else ["uniqueid", "recordType", "title", "content", "created", "lastModified"]
		)
		
		return handle_milvus_search_results(results)
		
	except Exception as e:
		print(f'Error in Milvus query_by_vector: {e}')
		traceback.print_exc()
		return {"results": []}

def query_by_vector_with_filter(tenant_name: str, query_vector: List[float], filter_expr: str, top_k: int = default_query_limit):
	"""
	Perform a vector similarity search with additional filters in Milvus.
	"""
	try:
		combined_filter = f'tenantName == "{tenant_name}" and ({filter_expr})'
		
		search_params = {
			"metric_type": "COSINE",
			"params": {}
		}
		
		results = milvus_client.client.search(
			collection_name=milvus_client.collection_name,
			data=[query_vector],
			anns_field="vector",
			search_params=search_params,
			limit=top_k,
			filter=combined_filter,
			output_fields=["*"]
		)
		
		return handle_milvus_search_results(results)
		
	except Exception as e:
		print(f'Error in Milvus query_by_vector_with_filter: {e}')
		traceback.print_exc()
		return {"results": []}

def query_by_keyword(tenant_name: str, keyword: str, top_k: int = default_query_limit, include_metadata: bool = True):
	"""
	Perform a keyword search in Milvus using filters.
	"""
	try:
		# Use filter to search for keyword in title, description, or content
		filter_expr = (
			f'tenantName == "{tenant_name}" and '
			f'(title like "%{keyword}%" or description like "%{keyword}%" or content like "%{keyword}%")'
		)
		
		results = milvus_client.client.query(
			collection_name=milvus_client.collection_name,
			filter=filter_expr,
			limit=top_k,
			output_fields=["*"] if include_metadata else ["uniqueid", "recordType", "title", "content"]
		)
		
		process_milvus_records(results)
		return {"results": results}
		
	except Exception as e:
		print(f'Error in Milvus query_by_keyword: {e}')
		traceback.print_exc()
		return {"results": []}

def query_by_keyword_with_filter(tenant_name: str, keyword: str, filter_expr: str, top_k: int = default_query_limit):
	"""
	Perform a keyword search with additional filters in Milvus.
	"""
	try:
		combined_filter = (
			f'tenantName == "{tenant_name}" and '
			f'(title like "%{keyword}%" or description like "%{keyword}%" or content like "%{keyword}%") and '
			f'({filter_expr})'
		)
		
		results = milvus_client.client.query(
			collection_name=milvus_client.collection_name,
			filter=combined_filter,
			limit=top_k,
			output_fields=["*"]
		)
		
		process_milvus_records(results)
		return {"results": results}
		
	except Exception as e:
		print(f'Error in Milvus query_by_keyword_with_filter: {e}')
		traceback.print_exc()
		return {"results": []}

def query_by_filter(tenant_name: str, filter_expr: str, top_k: int = default_query_limit, get_connected_results: bool = False, offset: int = 0):
	"""
	A pure filter based retrieval in Milvus.
	"""
	try:
		combined_filter = f'tenantName == "{tenant_name}" and ({filter_expr})'
		
		results = milvus_client.client.query(
			collection_name=milvus_client.collection_name,
			filter=combined_filter,
			limit=top_k,
			offset=offset,
			output_fields=["*"]
		)
		
		if get_connected_results:
			connected = handle_milvus_connected_results(tenant_name, results).get("results", [])
			process_milvus_records(connected)
			return {"results": connected}
		
		process_milvus_records(results)
		return {"results": results}
		
	except Exception as e:
		print(f'Error in Milvus query_by_filter: {e}')
		traceback.print_exc()
		return {"results": []}

def query_by_hybrid_with_filter(tenant_name: str, query: str, filter_expr: str, top_k: int = default_query_limit, similarity_setting: float = 0.5, include_vector: bool = False):
    """
    Perform a **hybrid search** that combines dense-vector similarity with a
    traditional keyword filter.

    This util follows the hybrid-search pattern described in the official
    Zilliz/Milvus documentation:
    1. Create an embedding for the free-text *query*.
    2. Run a vector search on the ``vector`` field **and** apply an additional
       scalar filter that captures the keyword predicate.

    The function accepts a **Milvus native** filter expression (not a Weaviate
    one – callers are responsible for providing the correct syntax).  The
    keyword predicate is automatically generated from *query* and appended to
    the caller-supplied *filter_expr* using logical **AND** so both
    constraints are honoured.

    Results are fed through :pyfunc:`handle_milvus_search_results` to ensure
    they are fully post-processed (numpy → Python, tag deserialisation, etc.).
    """
    try:
        # ------------------------------------------------------------------
        # 1. Dense vector embedding for the natural-language query
        # ------------------------------------------------------------------
        query_vector = create_our_embedding(query)

        # ------------------------------------------------------------------
        # 2. Build the composite filter – tenant isolation + caller filter +
        #    keyword predicate (title/content LIKE "%<query>%")
        # ------------------------------------------------------------------
        # Escape double quotes inside the query string to avoid breaking the
        # expression.  We use json.dumps which safely quotes the string – it
        # returns the value wrapped in double quotes, so we strip them off for
        # embedding in the LIKE pattern.
        safe_query_term = json.dumps(query)[1:-1]  # remove surrounding quotes
        # Match query term against title, description, or content columns
        keyword_predicate = (
            f'(title like "%{safe_query_term}%" '
            f'or description like "%{safe_query_term}%" '
            f'or content like "%{safe_query_term}%")'
        )

        combined_filter_parts = [f'tenantName == "{tenant_name}"']
        if filter_expr:
            combined_filter_parts.append(f'({filter_expr})')
        combined_filter_parts.append(keyword_predicate)
        combined_filter = " and ".join(combined_filter_parts)

        # ------------------------------------------------------------------
        # 3. Configure vector search parameters (same conversion logic as
        #    query_by_vector)
        # ------------------------------------------------------------------
        distance_threshold = (2 * similarity_setting) - 1  # map 0-1 ➜  -1-1

        search_params = {
            "metric_type": "COSINE",
            "params": {"radius": distance_threshold, "range_filter": 1.0}
        }

        # ------------------------------------------------------------------
        # 4. Execute the search and post-process the results
        # ------------------------------------------------------------------
        results = milvus_client.client.search(
            collection_name=milvus_client.collection_name,
            data=[query_vector],
            anns_field="vector",
            search_params=search_params,
            limit=top_k,
            filter=combined_filter,
            output_fields=["*"],
        )

        # ------------------------------------------------------------------
        # Optional fallback: If the keyword predicate over-constrained the
        # query (returning zero hits), rerun the vector search **without** the
        # keyword filter so that users still get relevant semantic matches.
        # ------------------------------------------------------------------
        if (not results) or (isinstance(results, list) and len(results) > 0 and len(results[0]) == 0):
            fallback_parts = [f'tenantName == "{tenant_name}"']
            if filter_expr:
                fallback_parts.append(f'({filter_expr})')
            fallback_filter = " and ".join(fallback_parts)

            try:
                results = milvus_client.client.search(
                    collection_name=milvus_client.collection_name,
                    data=[query_vector],
                    anns_field="vector",
                    search_params=search_params,
                    limit=top_k,
                    filter=fallback_filter,
                    output_fields=["*"],
                )
            except Exception as fallback_err:
                print(f"Hybrid search fallback failed: {fallback_err}")

        return handle_milvus_search_results(results)

    except Exception as e:
        print(f'Error in Milvus query_by_hybrid_with_filter: {e}')
        traceback.print_exc()
        return {"results": []}

def get_most_recent_records(tenant_name: str, limit: int):
	"""
	Retrieve *limit* most-recently-modified records for the given tenant.

	Milvus filter expressions cannot (yet) impose an ORDER BY clause, so the
	official recommendation is to:
	1. Apply the scalar filter to narrow the candidate set.
	2. Fetch a window that is larger than the desired result size.
	3. Sort client-side on the timestamp field and trim to *limit*.

	This implementation follows that pattern exactly.
	"""
	if limit <= 0:
		return {"results": []}

	# Fetch more than we ultimately need so that client-side sorting
	# has a reasonable pool to work with.
	fetch_window = max(limit * 20, limit)

	try:
		candidate_records = milvus_client.client.query(
			collection_name=milvus_client.collection_name,
			filter=f'tenantName == "{tenant_name}"',
			limit=fetch_window,
			output_fields=["*"]
		)

		# Sort by `lastModified` (descending).
		candidate_records.sort(key=lambda r: r.get("lastModified", 0), reverse=True)

		most_recent = candidate_records[:limit]
		process_milvus_records(most_recent)
		return {"results": most_recent}

	except Exception as e:
		print(f"Error in Milvus get_most_recent_records: {e}")
		traceback.print_exc()
		return {"results": []}

def get_records_by_ids(tenant_name: str, ids: List[str]):
	"""
	Get records by their IDs in Milvus.
	"""
	try:
		if not ids:
			return []
			
		id_filter = " or ".join([f'uniqueid == "{uid}"' for uid in ids])
		combined_filter = f'tenantName == "{tenant_name}" and ({id_filter})'
		
		results = milvus_client.client.query(
			collection_name=milvus_client.collection_name,
			filter=combined_filter,
			output_fields=["*"]
		)
		
		process_milvus_records(results)
		return results
		
	except Exception as e:
		print(f'Error in Milvus get_records_by_ids: {e}')
		traceback.print_exc()
		return []

def get_record_by_id(tenant_name: str, record_id: str):
	"""
	Get a single record by its ID in Milvus.
	"""
	try:
		results = milvus_client.client.query(
			collection_name=milvus_client.collection_name,
			filter=f'tenantName == "{tenant_name}" and uniqueid == "{record_id}"',
			output_fields=["*"]
		)
		
		process_milvus_records(results)
		return results[0] if results else None
		
	except Exception as e:
		print(f'Error in Milvus get_record_by_id: {e}')
		traceback.print_exc()
		return None

def sync_by_last_modified(tenant_name: str, last_sync_datetime: datetime, curr_device_id: str, limit: int = None, offset: int = None):
	"""
	Sync all records by getting all records with last modified > last_sync_datetime in Milvus.
	Includes fallback logic to handle errors by degrading batch sizes similar to the Weaviate implementation.
	"""
	try:
		# Subtract 1 minute from last_sync_datetime
		last_sync_datetime = last_sync_datetime - timedelta(minutes=1)
		last_sync_timestamp = int(last_sync_datetime.timestamp() * 1000)

		filter_expr = f'tenantName == "{tenant_name}" and lastModified > {last_sync_timestamp}'

		if limit is not None:
			# Fetch with provided limit/offset, using fallback-aware helper
			results = fetch_objects_with_fallback(
				filter_expr=filter_expr,
				output_fields=["*"],
				limit=limit,
				offset=offset or 0
			)
		else:
			# Full sync – iterate through dataset in batches with internal fallback
			all_results: List[Dict[str, Any]] = []
			curr_offset = 0
			batch_size = 100
			max_loops = 1000  # Safety guard to prevent infinite loops

			while max_loops > 0:
				batch_results = fetch_objects_with_fallback(
					filter_expr=filter_expr,
					output_fields=["*"],
					limit=batch_size,
					offset=curr_offset
				)

				if not batch_results:
					break

				all_results.extend(batch_results)
				curr_offset += batch_size
				max_loops -= 1

			results = all_results

		deleted_records = []
		# For limit and offset syncs with offset > 0, do not fetch deleted records
		if not (limit is not None and offset is not None and offset > 0):
			try:
				deleted_records = DeletedRecord.get_records_since(tenant_name, last_sync_datetime)
			except (ServerSelectionTimeoutError, AutoReconnect, ConnectionFailure) as mongo_error:
				print(f'MongoDB connection error in deleted records (replica set issue): {mongo_error}')
				print('Attempting to continue sync without deleted records for this iteration')
				# Try to handle the connection with backoff
				for retry_attempt in range(3):
					try:
						delay = (2 ** retry_attempt)  # 1s, 2s, 4s
						print(f'Waiting {delay} seconds before retry attempt {retry_attempt + 1}/3')
						time.sleep(delay)
						
						# Test MongoDB connection
						from db.mongodb import client
						client.admin.command('ping')
						print(f'MongoDB connection restored on attempt {retry_attempt + 1}')
						
						# Retry the deleted records fetch
						deleted_records = DeletedRecord.get_records_since(tenant_name, last_sync_datetime)
						print('Successfully retrieved deleted records after connection recovery')
						break
						
					except Exception as retry_error:
						if retry_attempt == 2:  # Last attempt
							print(f'All MongoDB retry attempts failed: {retry_error}')
							print('Continuing sync without deleted records - they will be included in next sync')
							deleted_records = []
						continue
			except Exception as e:
				print(f'Error in deleted records: {e}')
				traceback.print_exc()
				deleted_records = []

		process_milvus_records(results)
		return {
			'results': results,
			'deleted_results': deleted_records
		}

	except Exception as e:
		print(f'Error in Milvus sync_by_last_modified: {e}')
		traceback.print_exc()
		return {
			'results': [],
			'deleted_results': []
		}

# **** Utility to translate generic / Weaviate-style filters to Milvus ****

def convert_to_milvus_filter(filter_input: Any) -> Optional[str]:
	"""Convert a simple Weaviate-style filter (dict or str) into a Milvus filter string.

	Supported *filter_input* types:
	1. ``str`` – assumed to already be a Milvus expression and returned unchanged.
	2. ``dict`` – ``{field: value}`` mappings are converted as follows:
	   • ``list`` values – if the field name ends with ``Ids`` (case-insensitive) *or* the
	     field is exactly ``tagIds``, the expression becomes
	     ``ARRAY_CONTAINS_ANY(field, [...])``.
	     Otherwise the expression becomes ``field in [...]``.
	   • ``str`` values – converted to equality ``field == "value"``.
	   • Other scalars – converted to equality ``field == <json dump>``.
	Multiple key/value pairs are joined with ``and``.

	If the input cannot be parsed, the function falls back to ``str(filter_input)``.
	"""
	if filter_input is None:
		return None

	# Pre-converted expression
	if isinstance(filter_input, str):
		return filter_input

	# Dict conversion
	if isinstance(filter_input, dict):
		try:
			parts: List[str] = []
			for key, val in filter_input.items():
				if isinstance(val, list):
					# Heuristic: array columns typically use ARRAY_CONTAINS_* helpers
					if key.lower().endswith("ids") or key == "tagIds":
						parts.append(f"ARRAY_CONTAINS_ANY({key}, {json.dumps(val)})")
					else:
						parts.append(f"{key} in {json.dumps(val)}")
				elif isinstance(val, str):
					parts.append(f"{key} == \"{val}\"")
				else:
					parts.append(f"{key} == {json.dumps(val)}")

			return " and ".join(parts) if parts else None
		except Exception:
			# Fallback to string representation on any unexpected error
			traceback.print_exc()
			return str(filter_input)

	# Unsupported type – just stringify
	return str(filter_input)

# **** Existing helper functions ****

def handle_milvus_search_results(search_results):
	"""
	Handle and format Milvus search results.
	"""
	results = []
	if search_results and len(search_results) > 0:
		for hit in search_results[0]:  # search_results is a list of result lists
			result_dict = hit.get('entity', {})
			if 'distance' in hit:
				result_dict['_distance'] = hit['distance']
			results.append(result_dict)
	
	process_milvus_records(results)
	return {"results": results}

def handle_milvus_connected_results(tenant_name: str, results: List[Dict]):
	"""
	Handle connected results by fetching related records.
	"""
	# Collect all unique connection IDs
	connection_ids = set()
	for result in results:
		if not result:
			continue
		incoming = result.get("incomingConnections") or []
		outgoing = result.get("outgoingConnections") or []
		
		# Handle case where connections might be JSON strings
		if isinstance(incoming, str):
			try:
				incoming = json.loads(incoming)
			except:
				incoming = []
		if isinstance(outgoing, str):
			try:
				outgoing = json.loads(outgoing)
			except:
				outgoing = []
				
		connection_ids.update(incoming)
		connection_ids.update(outgoing)
	
	# Fetch all connected records in one batch if there are any connections
	connection_map = {}
	if connection_ids:
		connected_records = get_records_by_ids(tenant_name, list(connection_ids))
		connection_map = {record["uniqueid"]: record for record in connected_records}
	
	# Map the connections using the cached records
	for result in results:
		incoming = result.get("incomingConnections") or []
		outgoing = result.get("outgoingConnections") or []
		
		# Handle JSON string connections
		if isinstance(incoming, str):
			try:
				incoming = json.loads(incoming)
			except:
				incoming = []
		if isinstance(outgoing, str):
			try:
				outgoing = json.loads(outgoing)
			except:
				outgoing = []
		
		result["incomingConnections"] = [
			connection_map.get(conn_id, conn_id) for conn_id in incoming
		]
		result["outgoingConnections"] = [
			connection_map.get(conn_id, conn_id) for conn_id in outgoing
		]
	
	process_milvus_records(results)
	return {"results": results}

def fetch_objects_with_fallback(filter_expr: str, output_fields: Optional[List[str]] = None, *, limit: int = 1000, offset: int = 0, smaller_limit: Optional[int] = None) -> List[Dict[str, Any]]:
	"""
	Fetch objects from Milvus with fallback to smaller batch sizes on error.

	If the initial fetch fails, the function will reduce the batch size and
	make multiple smaller requests to gather all the results.

	:param filter_expr: Milvus filter expression
	:param output_fields: List of fields to return. Defaults to ["*"]
	:param limit: Maximum number of results to return in total
	:param offset: Offset for pagination
	:param smaller_limit: Fallback batch size. If not provided, defaults to ``limit // 10`` (minimum 1)
	:return: List of result dictionaries
	"""
	if output_fields is None:
		output_fields = ["*"]

	# Helper closure to perform a single query call
	def _query(lim: int, off: int):
		return milvus_client.client.query(
			collection_name=milvus_client.collection_name,
			filter=filter_expr,
			limit=lim,
			offset=off,
			output_fields=output_fields
		)

	try:
		return _query(limit, offset)
	except Exception as e:
		print(f"Error fetching Milvus objects with limit {limit}, falling back to smaller batches: {e}")
		traceback.print_exc()

	# Fallback to smaller batches
	smaller_limit = smaller_limit or max(limit // 10, 1)
	all_results: List[Dict[str, Any]] = []
	num_batches = (limit + smaller_limit - 1) // smaller_limit  # ceiling division

	for i in range(num_batches):
		batch_offset = offset + (i * smaller_limit)
		try:
			batch_results = _query(smaller_limit, batch_offset)
			if not batch_results:
				break  # No more results
			all_results.extend(batch_results)
			if len(all_results) >= limit:
				all_results = all_results[:limit]
				break
		except Exception as batch_error:
			print(f"Error fetching Milvus batch at offset {batch_offset}: {batch_error}")
			traceback.print_exc()
			# Continue to next batch on error
			continue

	return all_results

def process_milvus_records(results: List[Dict[str, Any]]):
	"""
	Post-process records returned from Milvus to make them JSON-serializable.

	This function iterates through all fields of each result and converts
	non-standard types (especially numpy objects) to their Python equivalents.
	This is crucial for preventing serialization errors downstream, for example,
	when returning data from a FastAPI endpoint.

	Transformations performed in-place:
	1. Delegates to ``_process_tags_in_results`` to convert ``tags``
	   JSON strings back into Python objects.
	2. Converts numpy arrays (e.g., vectors) to lists via ``.tolist()``.
	3. Converts numpy scalars (e.g., ``np.float32`` for distances) to
	   standard Python types via ``.item()``.
	4. Attempts to convert other array-like objects (e.g. ``array.array``)
	   to lists via ``.tolist()``.
	"""
	try:
		import numpy as np
		numpy_available = True
	except ImportError:
		print("Warning: numpy not available for Milvus record processing")
		numpy_available = False
		np = None

	# First process tags so callers relying on that behaviour remain intact
	_process_tags_in_results(results)

	def convert_numpy_recursive(obj, path=""):
		"""Recursively convert numpy types to Python native types"""
		if numpy_available and np is not None:
			# Check for numpy types
			if isinstance(obj, np.ndarray):
				return obj.tolist()
			elif isinstance(obj, np.generic):
				return obj.item()
		
		# Check for other array-like objects
		if hasattr(obj, 'tolist') and not isinstance(obj, (str, bytes)):
			try:
				return obj.tolist()
			except Exception:
				pass
		
		# Recursively process lists
		if isinstance(obj, list):
			return [convert_numpy_recursive(item, f"{path}[{i}]") for i, item in enumerate(obj)]
		
		# Recursively process dictionaries
		if isinstance(obj, dict):
			return {k: convert_numpy_recursive(v, f"{path}.{k}") for k, v in obj.items()}
		
		# Return unchanged if not a numpy type or container
		return obj

	for i, res in enumerate(results or []):
		if res is None:
			continue

		# Convert the entire record recursively
		for key, value in list(res.items()):  # Use list() to avoid dict modification during iteration
			converted_value = convert_numpy_recursive(value, f"record[{i}].{key}")
			res[key] = converted_value

	return results
