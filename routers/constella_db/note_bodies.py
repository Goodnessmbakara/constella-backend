from datetime import datetime
import json
from utils.notifs import send_ios_image_notification
from weaviate.exceptions import UnexpectedStatusCodeError
import fastapi
from fastapi import BackgroundTasks
from weaviate.classes.query import Filter, MetadataQuery
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import traceback
import sentry_sdk
from typing import List, Dict, Any, Optional
from db.weaviate.operations.general import (delete_all_records, delete_record,
	delete_records_by_ids, get_most_recent_records, get_record_by_id, get_records_by_ids,
	insert_record, query_by_filter, query_by_keyword, query_by_keyword_with_filter, query_by_vector,
	query_by_vector_with_filter, update_record_metadata, update_record_vector, upsert_records, do_milvus_querying)
from ai.embeddings import create_embedding, create_file_embedding, get_image_to_text
from db.weaviate.records.note_body import WeaviateNoteBody, BodyType
from db.models.constella.long_job import LongJob
from constants import default_query_limit, image_note_prefix
from utils.constella.files.file_base64 import clean_base64
from utils.constella.files.s3.s3 import (get_file_url_from_path, get_signed_file_url,
	upload_file_bytes_to_s3, remove_signed_params_from_url)
from db.models.constella.constella_retry_queue import RetryQueue
from utils.constella.files.s3.s3_file_management import cloudfront_url_prefix
from ai.vision.images import (format_ocr_json_to_string, image_matches_instruction,
	openai_ocr_image_to_text)
from db.milvus.operations import general as milvus_general


router = APIRouter(
	prefix="/constella_db/note_body",
	tags=["constella_db_note_body"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

class NoteBodyIn(BaseModel):
	tenant_name: str
	record: dict

class NoteBodysIn(BaseModel):
	tenant_name: str
	records: List[Dict[str, Any]]

class VectorUpdateIn(BaseModel):
	tenant_name: str
	unique_id: str
	new_vector: dict
	text: str = ''

class MetadataUpdateIn(BaseModel):
	tenant_name: str
	unique_id: str
	metadata_updates: Dict[str, Any]
	full_data: Optional[Dict[str, Any]] = None

class DeleteNoteBodyIn(BaseModel):
	tenant_name: str
	unique_id: str

class DeleteNoteBodysById(BaseModel):
	tenant_name: str
	unique_ids: List[str]

class GetNoteBodysByIdsIn(BaseModel):
	tenant_name: str
	ids: List[str] = []

class GetNoteBodyByIdIn(BaseModel):
	tenant_name: str
	record_id: str

class QueryIn(BaseModel):
	tenant_name: str
	query_vector: List[float] = None
	query_text: str = None
	top_k: int = default_query_limit
	similarity_setting: float = 0.5

class FilterQueryIn(BaseModel):
	tenant_name: str
	query_vector: List[float]
	filter: Dict[str, Any]
	top_k: int = default_query_limit

class KeywordQueryIn(BaseModel):
	tenant_name: str
	keyword: str
	top_k: int = default_query_limit

class KeywordFilterQueryIn(BaseModel):
	tenant_name: str
	keyword: str
	filter: Dict[str, Any]
	top_k: int = default_query_limit

class GetMostRecentNoteBodysIn(BaseModel):
	tenant_name: str
	limit: int = 50

class GetByReferenceIdIn(BaseModel):
	tenant_name: str
	reference_id: str
	top_k: int = default_query_limit

@router.post("/insert_note_body")
async def route_insert_note_body(note_body_in: NoteBodyIn, request: Request):
	try:
		# Create the vector from the text
		note_body_in.record["vector"] = create_embedding(note_body_in.record.get("text", ""))
		
		device_type = request.state.device_type
		device_id = request.state.device_id
		note_body_in.record["lastUpdateDevice"] = device_type
		note_body_in.record["lastUpdateDeviceId"] = device_id
		
		uniqueid = insert_record(note_body_in.tenant_name, WeaviateNoteBody.from_rxdb(note_body_in.record))
		return {"success": True, "uniqueid": uniqueid}
	except Exception as e:
		traceback.print_exc()
		# Add to retry queue
		retry_parameters = {
			"tenant_name": note_body_in.tenant_name,
			"record": note_body_in.record,
			"device_type": request.state.device_type,
			"device_id": request.state.device_id
		}
		RetryQueue.create("note_body_route_insert_note_body", retry_parameters)
		raise HTTPException(
			status_code=500,
			detail=str(e)
		)

@router.post("/upsert_note_bodies")
async def route_upsert_note_bodies(note_bodies_in: NoteBodysIn, request: Request, background_tasks: BackgroundTasks):
	try:
		device_type = request.state.device_type
		device_id = request.state.device_id

		long_job_id = LongJob.insert('started', [])

		background_tasks.add_task(upsert_records, note_bodies_in.tenant_name, note_bodies_in.records, type='noteBody', long_job_id=long_job_id, last_update_device=device_type, last_update_device_id=device_id)

		return {"message": "Note bodies upserted successfully", "long_job_id": long_job_id}
	except Exception as e:
		print('Error upserting note bodies')
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_note_body_vector")
async def route_update_note_body_vector(vector_update: VectorUpdateIn, request: Request):
	try:
		# Create vector
		new_vector = create_embedding(vector_update.text)

		device_type = request.state.device_type
		device_id = request.state.device_id
		update_record_vector(vector_update.tenant_name, vector_update.unique_id, new_vector, {"lastUpdateDevice": device_type, "lastUpdateDeviceId": device_id})
		return {"message": "Note body vector updated successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_note_body_metadata")
async def route_update_note_body_metadata(metadata_update: MetadataUpdateIn, request: Request):
	try:
		device_type = request.state.device_type
		device_id = request.state.device_id
		metadata_update.metadata_updates["lastUpdateDevice"] = device_type
		metadata_update.metadata_updates["lastUpdateDeviceId"] = device_id

		update_res = update_record_metadata(metadata_update.tenant_name, metadata_update.unique_id, metadata_update.metadata_updates)

		# If update failed, try to insert the record
		if update_res != 200 and metadata_update.full_data is not None and len(metadata_update.full_data) > 0:
			metadata_update.full_data["vector"] = create_embedding(metadata_update.full_data.get("text", ""))
			insert_record(metadata_update.tenant_name, WeaviateNoteBody.from_rxdb(metadata_update.full_data))

		return {"message": "Note body metadata updated successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_note_body")
async def route_delete_note_body(delete_note_body_in: DeleteNoteBodyIn):
	try:
		delete_record(delete_note_body_in.tenant_name, delete_note_body_in.unique_id)
		return {"message": "Note body deleted successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_note_bodies_by_id")
async def route_delete_note_bodies_by_id(delete_note_bodies_in: DeleteNoteBodysById):
	try:
		delete_records_by_ids(delete_note_bodies_in.tenant_name, delete_note_bodies_in.unique_ids, "noteBody")
		return {"message": "Note bodies deleted successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_all_note_bodies/{tenant_name}")
async def route_delete_all_note_bodies(tenant_name: str):
	try:
		delete_all_records(tenant_name, "noteBody")
		return {"message": "All note bodies deleted successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/get_note_bodies_by_ids")
async def route_get_note_bodies_by_ids(get_note_bodies_in: GetNoteBodysByIdsIn):
	try:
		records = get_records_by_ids(get_note_bodies_in.tenant_name, get_note_bodies_in.ids, "noteBody")
		return {"records": records}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/get_note_body_by_id")
async def route_get_note_body_by_id(get_note_body_in: GetNoteBodyByIdIn):
	try:
		record = get_record_by_id(get_note_body_in.tenant_name, get_note_body_in.record_id, "noteBody")
		if record is None:
			raise HTTPException(status_code=404, detail="Note body not found")
		return {"record": record}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/query_by_vector")
async def route_query_by_vector(query_in: QueryIn):
	try:
		query_vector = query_in.query_vector
		if not query_vector and query_in.query_text:
			query_vector = create_embedding(query_in.query_text)
		if do_milvus_querying:
			# Restrict to noteBody records only during Milvus search
			filter_expr = 'recordType == "noteBody"'
			results = milvus_general.query_by_vector_with_filter(
				query_in.tenant_name,
				query_vector,
				filter_expr,
				query_in.top_k
			)
		else:
			results = query_by_vector(query_in.tenant_name, query_vector, query_in.top_k, query_in.similarity_setting)
		return {"results": results['results']}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/query_by_vector_with_filter")
async def route_query_by_vector_with_filter(filter_query_in: FilterQueryIn):
	try:
		if do_milvus_querying:
			filter_expr = milvus_general.convert_to_milvus_filter(filter_query_in.filter)
			results = milvus_general.query_by_vector_with_filter(
				filter_query_in.tenant_name,
				filter_query_in.query_vector,
				filter_expr,
				filter_query_in.top_k
			)
			return {"results": results}
		else:
			results = query_by_vector_with_filter(
				filter_query_in.tenant_name,
				filter_query_in.query_vector,
				filter_query_in.filter,
				filter_query_in.top_k
			)
			return {"results": results}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/query_by_keyword")
async def route_query_by_keyword(keyword_query_in: KeywordQueryIn):
	try:
		if do_milvus_querying:
			filter_expr = 'recordType == "noteBody"'
			results = milvus_general.query_by_keyword_with_filter(
				keyword_query_in.tenant_name,
				keyword_query_in.keyword,
				filter_expr,
				max(keyword_query_in.top_k, 50)
			)
			return {"results": results['results']}
		else:
			filter_weav = Filter.by_property("recordType").equal("noteBody")
			results = query_by_keyword_with_filter(keyword_query_in.tenant_name, keyword_query_in.keyword, filter_weav, max(keyword_query_in.top_k, 50))
			return {"results": results['results']}
	except Exception as e:
		try:
			# Fallback to smaller result size
			if do_milvus_querying:
				filter_expr = 'recordType == "noteBody"'
				results = milvus_general.query_by_keyword_with_filter(
					keyword_query_in.tenant_name,
					keyword_query_in.keyword,
					filter_expr,
					2
				)
			else:
				filter_weav = Filter.by_property("recordType").equal("noteBody")
				results = query_by_keyword_with_filter(keyword_query_in.tenant_name, keyword_query_in.keyword, filter_weav, 2)
			sentry_sdk.capture_exception(Exception(f"Error in query_by_keyword: {e}"))
			return {"results": results['results']}
		except Exception as e:
			raise HTTPException(status_code=500, detail=str(e))

@router.post("/query_by_keyword_with_filter")
async def route_query_by_keyword_with_filter(keyword_filter_query_in: KeywordFilterQueryIn):
	try:
		if do_milvus_querying:
			filter_expr = milvus_general.convert_to_milvus_filter(keyword_filter_query_in.filter)
			results = milvus_general.query_by_keyword_with_filter(
				keyword_filter_query_in.tenant_name,
				keyword_filter_query_in.keyword,
				filter_expr,
				max(keyword_filter_query_in.top_k, 50)
			)
			return {"results": results['results']}
		else:
			results = query_by_keyword_with_filter(
				keyword_filter_query_in.tenant_name,
				keyword_filter_query_in.keyword,
				keyword_filter_query_in.filter,
				max(keyword_filter_query_in.top_k, 50)
			)
			return {"results": results['results']}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/get_most_recent_note_bodies")
async def route_get_most_recent_note_bodies(get_most_recent_note_bodies_in: GetMostRecentNoteBodysIn):
	try:
		results = get_most_recent_records(get_most_recent_note_bodies_in.tenant_name, get_most_recent_note_bodies_in.limit)
		return {"results": results['results']}
	except Exception as e:
		return {"results": []}

@router.post("/get_by_reference_id")
async def route_get_by_reference_id(get_by_reference_id_in: GetByReferenceIdIn):
	"""
	Get all note bodies with the specified reference ID
	"""
	try:
		if do_milvus_querying:
			filter_expr = milvus_general.convert_to_milvus_filter({"referenceId": get_by_reference_id_in.reference_id})
			results = milvus_general.query_by_filter(
				get_by_reference_id_in.tenant_name,
				filter_expr,
				get_by_reference_id_in.top_k,
				get_connected_results=False
			)
			return {"results": results['results']}
		else:
			filter = Filter.by_property("referenceId").equal(get_by_reference_id_in.reference_id)
			results = query_by_filter(
				get_by_reference_id_in.tenant_name,
				filter,
				get_by_reference_id_in.top_k,
				get_connected_results=False
			)
			return {"results": results['results']}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))