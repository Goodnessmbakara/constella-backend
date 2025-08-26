# General node operations (note, tag, etc.)
import uuid
from db.weaviate.weaviate_client import (create_tenant, get_tenant_collection,
	parse_weaviate_result, parse_weaviate_results)
from weaviate.classes.query import Filter, MetadataQuery, Sort
from weaviate.exceptions import UnexpectedStatusCodeError
from constants import default_query_limit
from db.weaviate.records.general_record import GeneralWeaviateRecord
import traceback
from db.models.constella.deleted_record import DeletedRecord
from datetime import datetime, timedelta
import pytz
from db.weaviate.records.note import WeaviateNote
from db.weaviate.records.tag import WeaviateTag
from ai.embeddings import create_embedding, create_file_embedding
from db.models.constella.long_job import LongJob
from utils.constella.files.s3.s3 import upload_file_bytes_to_s3
from db.weaviate.records.misc import WeaviateMisc
import sentry_sdk

# Import Milvus operations
from db.milvus.operations import general as milvus_general

do_milvus_as_well = False
do_milvus_querying = False

# **** Insertion ****

def insert_record(tenant_name, record: GeneralWeaviateRecord):
	"""
	Insert a record into the Weaviate collection.
	:param tenant_name: The tenant to insert into.
	:param record: The record to insert.
	"""
	try:
		tenant_collection = get_tenant_collection(tenant_name)

		uniqueid = record.uniqueid

		if not uniqueid or uniqueid == "" or len(uniqueid) == 0:
			print("SETTING UNIQUEID")
			uniqueid = str(uuid.uuid4())
			record.uniqueid = uniqueid

		if not record.uniqueid:
			uniqueid = tenant_collection.data.insert(
				vector=record.vector,
				properties=record.properties,
			)
		else:
			uniqueid = tenant_collection.data.insert(
				vector=record.vector,
				properties=record.properties,
				uuid=record.uniqueid
			)

		# Also insert into Milvus
		if do_milvus_as_well:
			try:
				uniqueid = milvus_general.insert_record(tenant_name, record)
			except Exception as milvus_e:
				print(f"Error inserting into Milvus: {milvus_e}")

		return str(uniqueid)
	except UnexpectedStatusCodeError as e:
		print('Error in insert record: ', e)
		if e.status_code == 422 and "already exists" in str(e):
			return None
		raise
	except:
		# if already exists, wil throw 422 error
		print('Error in insert record')
		traceback.print_exc()
		raise Exception("Failed to insert record")

def upsert_records(tenant_name, records: list[GeneralWeaviateRecord], type='note', long_job_id='', last_update_device='', last_update_device_id=''):
	"""
	Upsert records into the Weaviate collection using batch insert.
	Unlike WeaviateRecord, this takes in a list[dict] of
	{
		vector: "...",
		properties: "..."
	}
	This is to avoid excess processing on the backend.
	:param tenant_name: The tenant to upsert into.
	:param records: A list of records to upsert.
	"""
	processed_records = []
	try:
		tenant_collection = get_tenant_collection(tenant_name)

		with tenant_collection.batch.dynamic() as batch:
			for i, record in enumerate(records):
				try:
					record["lastUpdateDevice"] = last_update_device
					record["lastUpdateDeviceId"] = last_update_device_id

					if type == 'note':
						if not record.get("title", ""):
							continue
						# convert to openai for standard format
						title = record.get("title", "")
						if title.startswith('<IMAGE-NOTE:> ') or title.startswith('<DOC-NOTE:> '):
							# record['vector'] = create_file_embedding(record.get("fileData", ""), record.get("fileType", "not existing"))
							url = upload_file_bytes_to_s3(tenant_name, record.get("fileData", ""), record.get("uniqueid", ""), record.get("fileType", ""))
							record["fileData"] = url
						# else:
						# 	record['vector'] = create_embedding(title)
						processed_record = WeaviateNote.from_rxdb(record)
						batch.add_object(
							# vector=record.vector,
							properties=processed_record.properties,
							uuid=processed_record.uniqueid
						)
						processed_records.append(processed_record)
					elif type == 'tag':
						processed_record = WeaviateTag.from_rxdb(record)
						batch.add_object(
							# vector=record.vector,
							properties=processed_record.properties,
							uuid=processed_record.uniqueid
						)
						processed_records.append(processed_record)
					elif type == 'misc':
						processed_record = WeaviateMisc.from_rxdb(record)
						batch.add_object(
							# vector=record.vector,
							properties=processed_record.properties,
							uuid=processed_record.uniqueid
						)
						processed_records.append(processed_record)

					records[i] = None
				except Exception as e:
					print(f"Error upserting record: {e}")
					traceback.print_exc()

		# Also upsert into Milvus
		if do_milvus_as_well:
			try:
				if processed_records:
					milvus_general.upsert_records(tenant_name, processed_records, type, long_job_id, last_update_device, last_update_device_id)
			except Exception as milvus_e:
				print(f"Error upserting into Milvus: {milvus_e}")

	except Exception as e:
		traceback.print_exc()
		raise e
	finally:
		LongJob.update_status(long_job_id, 'completed')
		records.clear()



# **** Updating ****

def update_record_vector_raw(tenant_name, unique_id, new_vector, metadata_updates = None):
	tenant_collection = get_tenant_collection(tenant_name)

	if metadata_updates:
		tenant_collection.data.update(
			uuid=unique_id,
			vector=new_vector,
			properties=metadata_updates
		)
	else:
		tenant_collection.data.update(
			uuid=unique_id,
			vector=new_vector
		)

def update_record_vector(tenant_name, unique_id, new_vector, metadata_updates = None):
	"""
	Update the vector of a specific record.
	On error, update_record_metadata will do an insert with a vector so don't need to do it here
	:param tenant_name: The tenant containing the record.
	:param unique_id: The unique ID of the record to update.
	:param new_vector: The new vector to assign to the record.
	"""
	try:
		update_record_vector_raw(tenant_name, unique_id, new_vector, metadata_updates)
		
		# Also update in Milvus
		if do_milvus_as_well:
			try:
				milvus_general.update_record_vector(tenant_name, unique_id, new_vector, metadata_updates)
			except Exception as milvus_e:
				print(f"Error updating vector in Milvus: {milvus_e}")
			
	except UnexpectedStatusCodeError as e:
		try:
			create_tenant(tenant_name)
			update_record_vector_raw(tenant_name, unique_id, new_vector, metadata_updates)
			
			# Also update in Milvus after successful Weaviate update
			if do_milvus_as_well:
				try:
					milvus_general.update_record_vector(tenant_name, unique_id, new_vector, metadata_updates)
				except Exception as milvus_e:
					print(f"Error updating vector in Milvus: {milvus_e}")
				
		except UnexpectedStatusCodeError as e:
			return None
	except:
		return None

def update_record_metadata_raw(tenant_name, unique_id, metadata_updates):
	tenant_collection = get_tenant_collection(tenant_name)
	if 'vector' in metadata_updates:
		metadata_updates.pop('vector') # delete vector in case it exists

	tenant_collection.data.update(
		uuid=unique_id,
		properties=metadata_updates
	)

def update_record_metadata(tenant_name, unique_id, metadata_updates):
	"""
	Update the metadata of a specific record.
	:param tenant_name: The tenant containing the record.
	:param unique_id: The unique ID of the record to update.
	:param metadata_updates: A dictionary of metadata fields to update.
	"""
	try:
		update_record_metadata_raw(tenant_name, unique_id, metadata_updates)
		
		# Also update in Milvus
		if do_milvus_as_well:
			try:
				milvus_general.update_record_metadata(tenant_name, unique_id, metadata_updates)
			except Exception as milvus_e:
				print(f"Error updating metadata in Milvus: {milvus_e}")
			
		return 200
	except UnexpectedStatusCodeError as e:
		try:
			create_tenant(tenant_name)
			update_record_metadata_raw(tenant_name, unique_id, metadata_updates)
			
			# Also update in Milvus after successful Weaviate update
			if do_milvus_as_well:
				try:
					milvus_general.update_record_metadata(tenant_name, unique_id, metadata_updates)
				except Exception as milvus_e:
					print(f"Error updating metadata in Milvus: {milvus_e}")
				
			return 200
		except UnexpectedStatusCodeError as e:
			print('Update record metadata error #1: ', e)
			print('metadata_updates: ', metadata_updates)
			# object most likely doesn't exist
			return None
	except Exception as e:
		print('Updated record metadata error #2: ', e)
		print('metadata_updates: ', metadata_updates)
		return None

# **** Deletion ****

def delete_record(tenant_name, unique_id, record_type="note", s3_path=None):
	"""
	Delete a specific record from the collection.
	:param tenant_name: The tenant containing the record.
	:param unique_id: The unique ID of the record to delete.
	"""
	tenant_collection = get_tenant_collection(tenant_name)
	tenant_collection.data.delete_by_id(unique_id)

	# add to deleted mongodb
	DeletedRecord(uniqueid=unique_id, recordType=record_type, lastModified=datetime.utcnow(), tenantName=tenant_name, s3_path=s3_path).save()

	# Also delete from Milvus
	if do_milvus_as_well:
		try:
			milvus_general.delete_record(tenant_name, unique_id, record_type, s3_path)
		except Exception as milvus_e:
			print(f"Error deleting from Milvus: {milvus_e}")

def delete_records_by_ids(tenant_name, id_list, record_type="note", s3_paths=None):
	"""
	Delete multiple records from the collection by their IDs.
	:param tenant_name: The tenant containing the records.
	:param id_list: List of unique IDs of the records to delete.
	:param record_type: The type of records being deleted. Default is "note".
	"""
	try:
		tenant_collection = get_tenant_collection(tenant_name)

		# Delete records by IDs
		tenant_collection.data.delete_many(
			where=Filter.by_id().contains_any(id_list)
		)

		# Add to deleted mongodb
		current_time = datetime.utcnow()
		deleted_records = [
			DeletedRecord(
				uniqueid=unique_id,
				recordType=record_type,
				lastModified=current_time,
				tenantName=tenant_name,
				s3_path=s3_paths[i] if s3_paths and i < len(s3_paths) else None
			) for i, unique_id in enumerate(id_list)
		]
		DeletedRecord.insert_many(deleted_records)

		# Also delete from Milvus
		if do_milvus_as_well:
			try:
				milvus_general.delete_records_by_ids(tenant_name, id_list, record_type, s3_paths)
			except Exception as milvus_e:
				print(f"Error deleting from Milvus: {milvus_e}")

		return True
	except Exception as e:
		print('Error in delete_records_by_ids')
		traceback.print_exc()
		return False


def delete_all_records(tenant_name):
	"""
	Delete all records for a specific tenant.
	:param tenant_name: The tenant to clear.
	"""
	tenant_collection = get_tenant_collection(tenant_name)
	tenant_collection.data.delete_all()

	# Also delete all from Milvus
	if do_milvus_as_well:
		try:
			milvus_general.delete_all_records(tenant_name)
		except Exception as milvus_e:
			print(f"Error deleting all records from Milvus: {milvus_e}")

# **** Querying ****
def query_vector_with_fallback(tenant_collection, near_vector, limit, tenant_name, 
							  filters=None, include_vector=False, 
							  return_metadata=None, max_distance=None,
							  get_connected_results=True, text_query=None):
	"""
	Performs vector queries with fallback to smaller batches if the initial query fails.
	
	:param tenant_collection: The Weaviate collection to query
	:param near_vector: The vector to search for similar vectors
	:param limit: Maximum number of results to return
	:param tenant_name: The tenant name for result handling
	:param filters: Optional filters to apply to the query
	:param include_vector: Whether to include vector data
	:param return_metadata: Metadata to return
	:param max_distance: Maximum distance allowed for vector similarity
	:param get_connected_results: Whether to include connected results
	:return: Results in the format {"results": []}
	"""
	# Set default metadata safely
	if return_metadata is None:
		return_metadata = MetadataQuery(distance=True)
	
	# Try with original limit
	query_args = {
		"near_vector": near_vector,
		"limit": limit,
		"return_metadata": return_metadata,
		"include_vector": include_vector
	}
	
	if filters:
		query_args["filters"] = filters
	
	if max_distance is not None:
		query_args["distance"] = max_distance
	
	try:
		query_result = tenant_collection.query.near_vector(**query_args)
		
		return handle_search_results(tenant_name, query_result, get_connected_results)
	except Exception as e:
		print(f"Error in vector query with limit {limit}, falling back to smaller batches: {e}")
		
		# Use fixed batch size of 10
		smaller_limit = 10
		offset = 0

		# Calculate how many smaller batches we need
		num_batches = (limit + smaller_limit - 1) // smaller_limit
		
		# Create a mock result object to store all batched results
		class MockQueryResult:
			def __init__(self):
				self.objects = []
		
		mock_result = MockQueryResult()
		
		# Fetch in smaller batches
		for i in range(num_batches):
			batch_offset = offset + (i * smaller_limit)

			try:				
				query_args["limit"] = smaller_limit
				query_args["offset"] = batch_offset

				batch_results = tenant_collection.query.near_vector(**query_args)
				
				if not batch_results.objects:
					break  # No more results to fetch
				
				mock_result.objects.extend(batch_results.objects)
				
				# If we've gathered enough results, stop
				if len(mock_result.objects) >= limit:
					mock_result.objects = mock_result.objects[:limit]  # Truncate to requested limit
					break
			except Exception as batch_error:
				print(f"Error fetching batch in vector query: {batch_error}")
				# Continue with next batch
		
		return handle_search_results(tenant_name, mock_result, get_connected_results)

def query_keyword_with_fallback(tenant_collection, query, limit, tenant_name, 
                              filters=None, include_vector=False, 
                              return_metadata=None,
                              get_connected_results=True, query_properties=None):
    """
    Performs keyword (BM25) queries with fallback to smaller batches if the initial query fails.
    
    :param tenant_collection: The Weaviate collection to query
    :param query: The search keyword/text to look for
    :param limit: Maximum number of results to return
    :param tenant_name: The tenant name for result handling
    :param filters: Optional filters to apply to the query
    :param include_vector: Whether to include vector data
    :param return_metadata: Metadata to return
    :param get_connected_results: Whether to include connected results
    :param query_properties: Optional specific properties to search within
    :return: Results in the format {"results": []}
    """
    # Set default metadata safely
    if return_metadata is None:
        return_metadata = MetadataQuery(score=True)
    
    # Try with original limit
    query_args = {
        "query": query,
        "limit": limit,
        "return_metadata": return_metadata,
        "include_vector": include_vector
    }
    
    if filters:
        query_args["filters"] = filters
    
    if query_properties:
        query_args["query_properties"] = query_properties
    
    try:
        query_result = tenant_collection.query.bm25(**query_args)
        
        return handle_search_results(tenant_name, query_result, get_connected_results)
    except Exception as e:
        print(f"Error in keyword query with limit {limit}, falling back to smaller batches: {e}")
        
        # Reduce batch size
        smaller_limit = max(limit // 10, 1)
        offset = 0

        # Calculate how many smaller batches we need
        num_batches = (limit + smaller_limit - 1) // smaller_limit
        
        # Create a mock result object to store all batched results
        class MockQueryResult:
            def __init__(self):
                self.objects = []
        
        mock_result = MockQueryResult()
        
        # Fetch in smaller batches
        for i in range(num_batches):
            batch_offset = offset + (i * smaller_limit)

            try:                
                query_args["limit"] = smaller_limit
                query_args["offset"] = batch_offset

                batch_results = tenant_collection.query.bm25(**query_args)
                
                if not batch_results.objects:
                    break  # No more results to fetch
                
                mock_result.objects.extend(batch_results.objects)
                
                # If we've gathered enough results, stop
                if len(mock_result.objects) >= limit:
                    mock_result.objects = mock_result.objects[:limit]  # Truncate to requested limit
                    break
            except Exception as batch_error:
                print(f"Error fetching batch in keyword query: {batch_error}")
                # Continue with next batch
        
        return handle_search_results(tenant_name, mock_result, get_connected_results)

def query_by_vector(tenant_name, query_vector, top_k=default_query_limit, similarity_setting=0.5, include_vector=False):
	"""
	Perform a vector similarity search.
	:param tenant_name: The tenant to search in.
	:param query_vector: The query vector.
	:param top_k: The number of results to return. Default is 10.
	:param include_metadata: Whether to include the metadata in the results. Default is True.
	:return: { "results": [{...}, {...}, ...]}
	"""
	try:
		# If using Milvus, call Milvus method and return its results
		if do_milvus_querying:
			try:
				milvus_results = milvus_general.query_by_vector(tenant_name, query_vector, top_k, similarity_setting, include_vector)
				return milvus_results
			except Exception as milvus_e:
				print(f"Error querying Milvus: {milvus_e}")
				# Fall back to Weaviate if Milvus fails
		
		tenant_collection = get_tenant_collection(tenant_name)

		max_distance_allowed = 2 -  (2 *similarity_setting)

		similarity_setting = max(similarity_setting - 0.3, 0.1)

		# for default value up to the right, add a small bias
		if similarity_setting >= 0.5:
			max_distance_allowed -= 0.15
			max_distance_allowed = max(max_distance_allowed, 0.05)

		weaviate_results = query_vector_with_fallback(
			tenant_collection=tenant_collection,
			near_vector=query_vector,
			limit=top_k,
			include_vector=include_vector,
			max_distance=max_distance_allowed,
			filters=None,
			tenant_name=tenant_name,
			return_metadata=MetadataQuery(distance=True, last_update_time=True)
		)

		return weaviate_results
	except:
		print('Error in query_by_vector')
		traceback.print_exc()

def query_by_vector_with_filter(tenant_name, query_vector, filter, top_k=default_query_limit):
	"""
	Perform a vector similarity search.
	See https://weaviate.io/developers/weaviate/search/similarity#filter-results
	:param tenant_name: The tenant to search in.
	:param query_vector: The query vector.
	:param filter: The filter to apply to the query. For Milvus, this should be a filter expression string.
	:param top_k: The number of results to return.
	:param include_metadata: Whether to include the metadata in the results. Default is True.
	"""
	try:
		if do_milvus_querying:
			try:
				if isinstance(filter, str):
					milvus_results = milvus_general.query_by_vector_with_filter(tenant_name, query_vector, filter, top_k)
					return milvus_results
				else:
					print("Milvus query requires a string filter expression. Falling back to Weaviate.")
			except Exception as milvus_e:
				print(f"Error querying Milvus with filter: {milvus_e}")

		tenant_collection = get_tenant_collection(tenant_name)
		
		return query_vector_with_fallback(
			tenant_collection=tenant_collection,
			near_vector=query_vector,
			limit=top_k,
			filters=filter,
			tenant_name=tenant_name,
			get_connected_results=True
		)
	except:
		print('Error in query_by_vector_with_filter')
		traceback.print_exc()
		return {"results": []}


def query_by_keyword(tenant_name, keyword, top_k=default_query_limit, include_metadata=True):
	"""
	Perform a keyword search that filters by metadata, checking if the passed keyword is contained in the note's title.
	:param tenant_name: The tenant to search in.
	:param keyword: The keyword to search for in the title.
	:param top_k: The number of results to return.
	:param include_metadata: Whether to include the metadata in the results. Default is True.
	"""
	try:
		# If using Milvus, call Milvus method and return its results
		if do_milvus_querying:
			try:
				milvus_results = milvus_general.query_by_keyword(tenant_name, keyword, top_k, include_metadata)
				return milvus_results
			except Exception as milvus_e:
				print(f"Error querying Milvus by keyword: {milvus_e}")
				# Fall back to Weaviate if Milvus fails
		
		tenant_collection = get_tenant_collection(tenant_name)

		weaviate_results = query_keyword_with_fallback(
			tenant_collection=tenant_collection,
			query=keyword,
			limit=top_k,
			tenant_name=tenant_name,
			include_vector=include_metadata
		)

		return weaviate_results
	except Exception as e:
		print('Error in query_by_keyword')
		traceback.print_exc()
		return {"results": []}

def query_by_keyword_with_filter(tenant_name, keyword, filter, top_k=default_query_limit):
	"""
	Perform a keyword search that filters by metadata, checking if the passed keyword is contained in the note's title.
	:param tenant_name: The tenant to search in.
	:param keyword: The keyword to search for in the title.
	:param top_k: The number of results to return.
	:param include_metadata: Whether to include the metadata in the results. Default is True.
	"""
	try:
		tenant_collection = get_tenant_collection(tenant_name)
		
		return query_keyword_with_fallback(
			tenant_collection=tenant_collection,
			query=keyword,
			limit=top_k,
			filters=filter,
			tenant_name=tenant_name,
			get_connected_results=True
		)
	except Exception as e:
		print('Error in query_by_keyword_with_filter')
		traceback.print_exc()
		return {"results": []}

def query_by_filter(tenant_name, filter, top_k=default_query_limit, get_connected_results=False):
	"""
	A pure filter based retrieval
	:param tenant_name: The tenant to search in.
	:param top_k: The number of results to return.
	:param include_metadata: Whether to include the metadata in the results. Default is True.
	"""
	try:
		tenant_collection = get_tenant_collection(tenant_name)

		query_result = tenant_collection.query.fetch_objects(
			filters=filter,
			include_vector=True,
			limit=top_k
		)

		return handle_search_results(tenant_name=tenant_name, query_result=query_result, get_connected_results=get_connected_results)
	except Exception as e:
		traceback.print_exc()
		sentry_sdk.capture_exception(Exception(f"Error in query_by_filter: {e}"))
		try:
			# Try again with just 5 results
			tenant_collection = get_tenant_collection(tenant_name)
			query_result = tenant_collection.query.fetch_objects(
				filters=filter,
				include_vector=True,
				limit=5
			)
			return handle_search_results(tenant_name=tenant_name, query_result=query_result, get_connected_results=get_connected_results)
		except Exception as fallback_e:
			sentry_sdk.capture_exception(Exception(f"Error in query_by_filter fallback: {fallback_e}"))
			return {"results": []}


def fetch_objects_with_fallback(tenant_collection, filters, include_vector=True, return_metadata=None, limit=1000, offset=0, sort=None, smaller_limit=None):
	"""
	Fetches objects from Weaviate with fallback to smaller batch sizes on error.
	
	If the initial fetch fails, this function will reduce the batch size and
	make multiple smaller requests to gather all the results.
	
	:param tenant_collection: The Weaviate collection to query
	:param filters: Query filters to apply
	:param include_vector: Whether to include vector data
	:param return_metadata: Metadata to return
	:param limit: Maximum number of results to return
	:param offset: Offset for pagination
	:param sort: Optional sort criteria
	:return: List of objects from the query
	"""
	query_args = {
		"filters": filters,
		"include_vector": include_vector,
		"limit": limit,
		"offset": offset
	}
	
	if return_metadata is not None:
		query_args["return_metadata"] = return_metadata
		
	if sort is not None:
		query_args["sort"] = sort
	try:
		# Try with original limit
		results = tenant_collection.query.fetch_objects(**query_args)
		return results.objects
	except Exception as e:
		print(f"Error fetching with limit {limit}, falling back to smaller batches: {e}")
		
		# Reduce batch size
		smaller_limit = smaller_limit or max(limit // 10, 1)
		all_objects = []
		
		# Calculate how many smaller batches we need
		num_batches = (limit + smaller_limit - 1) // smaller_limit
		
		# Fetch in smaller batches
		for i in range(num_batches):
			batch_offset = offset + (i * smaller_limit)
			
			try:
				query_args["limit"] = smaller_limit
				query_args["offset"] = batch_offset
				
				batch_results = tenant_collection.query.fetch_objects(**query_args)
				
				if not batch_results.objects:
					break  # No more results to fetch
					
				all_objects.extend(batch_results.objects)
				
				# If we've gathered enough results, stop
				if len(all_objects) >= limit:
					all_objects = all_objects[:limit]  # Truncate to requested limit
					break
					
			except Exception as batch_error:
				print(f"Error fetching batch at offset {batch_offset}: {batch_error}")
				# Continue with next batch
		
		return all_objects

def get_most_recent_records(tenant_name: str, limit: int):
	"""
	Get the most recent records for a tenant
	:param tenant_name: The tenant to get records for.
	:param limit: The number of records to return.
	"""
	try:
		tenant_collection = get_tenant_collection(tenant_name)

		if do_milvus_querying:
			try:
				milvus_results = milvus_general.get_most_recent_records(tenant_name, limit)
				return milvus_results
			except Exception as milvus_e:
				print(f"Error getting most recent records with Milvus: {milvus_e}")
				# Fall back to Weaviate if Milvus fails

		query_result_objects = fetch_objects_with_fallback(
			tenant_collection=tenant_collection,
			filters=None,
			include_vector=True,
			limit=limit,
			offset=0,
			return_metadata=MetadataQuery(last_update_time=True),
			sort=Sort.by_property(name="lastModified", ascending=False),
			smaller_limit=10
		)
		
		# Create a mock query result to pass to handle_search_results
		class MockQueryResult:
			def __init__(self, objects):
				self.objects = objects
				
		mock_result = MockQueryResult(query_result_objects)
		
		return handle_search_results(tenant_name, mock_result)
	except Exception as e:
		print('Error in get_most_recent_records')
		sentry_sdk.capture_exception(Exception(f"Error in get_most_recent_records: {e}"))
		# If error, try with just 10
		try:
			tenant_collection = get_tenant_collection(tenant_name)

			query_result_objects = fetch_objects_with_fallback(
				tenant_collection=tenant_collection,
				filters=None,
				include_vector=True,
				limit=limit // 2,
				offset=0,
				return_metadata=MetadataQuery(last_update_time=True),
				sort=Sort.by_property(name="lastModified", ascending=False),
				smaller_limit=5
			)
			
			# Create a mock query result to pass to handle_search_results
			class MockQueryResult:
				def __init__(self, objects):
					self.objects = objects
					
			mock_result = MockQueryResult(query_result_objects)
			
			return handle_search_results(tenant_name, mock_result)
		except Exception as inner_e:
			print(f"Error in get_most_recent_records fallback: {inner_e}")
			sentry_sdk.capture_exception(Exception(f"Error in get_most_recent_records fallback: {inner_e}"))
			return {"results": []}

def get_records_by_ids(tenant_name: str, ids: list[str]):
	"""
	Get records by their ids
	:param ids: A list of ids to get records for.
	"""
	if do_milvus_querying:
		try:
			return milvus_general.get_records_by_ids(tenant_name, ids)
		except Exception as milvus_e:
			print(f"Error getting records by IDs from Milvus: {milvus_e}")
			# Fallback to weaviate

	tenant_collection = get_tenant_collection(tenant_name)

	try:
		tenant_collection = get_tenant_collection(tenant_name)

		# Find records by IDs
		response = tenant_collection.query.fetch_objects(
			filters=Filter.by_id().contains_any(ids)
		)

		return parse_weaviate_results(response.objects)

	except:
		print('Error in finding records by ids')
		traceback.print_exc()
		return []

def get_record_by_id(tenant_name, id):
	if do_milvus_querying:
		try:
			return milvus_general.get_record_by_id(tenant_name, id)
		except Exception as milvus_e:
			print(f"Error getting record by ID from Milvus: {milvus_e}")
			# Fallback to weaviate
	try:
		tenant_collection = get_tenant_collection(tenant_name)
		return parse_weaviate_result(tenant_collection.query.fetch_object_by_id(id))
	except:
		return None

def sync_by_last_modified(tenant_name, last_sync_datetime, curr_device_id, limit=None, offset=None):
	"""
	Sync all records by getting all records with last modified > last_sync_datetime
	and that came from mobile devices
	:param tenant_name: The tenant to sync.
	:param last_sync_timestamp: The last sync timestamp.
	:param limit: Optional limit for batch size
	:param offset: Optional offset for batch pagination
	"""

	# If using Milvus, call Milvus method and return its results
	if do_milvus_as_well:
		try:
			milvus_sync_result = milvus_general.sync_by_last_modified(tenant_name, last_sync_datetime, curr_device_id, limit, offset)
			return milvus_sync_result
		except Exception as milvus_e:
			print(f"Error syncing with Milvus: {milvus_e}")
			# Fall back to Weaviate if Milvus fails

	# Subtract 1 minute from last_sync_datetime
	last_sync_datetime = last_sync_datetime - timedelta(minutes=1)

	tenant_collection = get_tenant_collection(tenant_name)
	query_result = None

	def get_records_since():
		if limit is not None and offset is not None:
			# Use provided limit and offset for batching
			filters = Filter.by_update_time().greater_than(last_sync_datetime)
			return fetch_objects_with_fallback(
				tenant_collection=tenant_collection,
				filters=filters,
				include_vector=True,
				return_metadata=MetadataQuery(last_update_time=True),
				limit=limit,
				offset=offset
			)
		else:
			# Original implementation for full sync
			all_results = []
			curr_offset = 0
			max_loops = 1000
			batch_size = 100

			while True:
				filters = Filter.by_update_time().greater_than(last_sync_datetime)
				new_results = fetch_objects_with_fallback(
					tenant_collection=tenant_collection,
					filters=filters,
					include_vector=True,
					return_metadata=MetadataQuery(last_update_time=True),
					limit=batch_size,
					offset=curr_offset
				)

				if not new_results:
					break

				all_results.extend(new_results)
				curr_offset += batch_size

				# just a safety measure to prevent infinite loops
				max_loops -= 1
				if max_loops <= 0:
					break

			return all_results

	try:
		query_result = get_records_since()
	except:
		create_tenant(tenant_name)
		query_result = get_records_since()

	deleted_records = []

	# For limit and offset syncs with offset > 0, do not fetch deleted records
	# For all other cases, they will be fetched
	if not(limit is not None and offset is not None and offset > 0):
		# Get deleted records since last sync
		deleted_records = DeletedRecord.get_records_since(tenant_name, last_sync_datetime)

	weaviate_sync_result = {
		'results': parse_weaviate_results(query_result) if query_result else [],
		'deleted_results': deleted_records
	}

	return weaviate_sync_result

def handle_search_results(tenant_name, query_result, get_connected_results = True):
	"""
	Parse the results and handle any connected notes
	:param get_connected_results: Whether to update the connections with actual records rather than Ids (just 1 layer, not for the connection of connection)
	"""
	parsed_results = parse_weaviate_results(query_result.objects)
	
	if get_connected_results:
		# Collect all unique connection IDs
		connection_ids = set()
		for result in parsed_results:
			if not result:
				continue
			# Handle cases where the fields exist but are None
			incoming = result.get("incomingConnections") or []
			outgoing = result.get("outgoingConnections") or []
			connection_ids.update(incoming)
			connection_ids.update(outgoing)
		
		# Fetch all connected records in one batch if there are any connections
		connection_map = {}
		if connection_ids:
			connected_records = get_records_by_ids(tenant_name, list(connection_ids))
			connection_map = {record["uniqueid"]: record for record in connected_records}
		
		# Map the connections using the cached records, preserving IDs if record not found
		for result in parsed_results:
			result["incomingConnections"] = [
				connection_map.get(id, id)
				for id in (result.get("incomingConnections") or [])
			]
			result["outgoingConnections"] = [
				connection_map.get(id, id)
				for id in (result.get("outgoingConnections") or [])
			]
	
	return {
		"results": parsed_results,
	}
