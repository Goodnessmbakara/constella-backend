from datetime import datetime
import json
from utils.notifs import send_ios_image_notification
from weaviate.exceptions import UnexpectedStatusCodeError
import fastapi
from fastapi import BackgroundTasks, WebSocket, WebSocketDisconnect, Query
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
from db.weaviate.records.note import WeaviateNote
from db.models.constella.long_job import LongJob
from constants import default_query_limit, image_note_prefix
from utils.constella.files.file_base64 import clean_base64
from utils.constella.files.s3.s3 import (get_file_url_from_path, get_signed_file_url,
	upload_file_bytes_to_s3, remove_signed_params_from_url)
from db.models.constella.constella_retry_queue import RetryQueue
from utils.constella.files.s3.s3_file_management import cloudfront_url_prefix
from ai.vision.images import (format_ocr_json_to_string, image_matches_instruction,
	openai_ocr_image_to_text)
from utils.websockets.notes_websocket import ws_manager
from utils.websockets.remote_broadcast import second_broadcast_event
from db.milvus.operations import general as milvus_general


router = APIRouter(
	prefix="/constella_db/note",
	tags=["constella_db_note"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

class RecordIn(BaseModel):
	tenant_name: str
	record: dict

class OCRNoteIn(BaseModel):
	tenant_name: str
	record: dict

class RecordsIn(BaseModel):
	tenant_name: str
	records: List[Dict[str, Any]]

class VectorUpdateIn(BaseModel):
	tenant_name: str
	unique_id: str
	new_vector: dict
	title: str = ''

class MetadataUpdateIn(BaseModel):
	tenant_name: str
	unique_id: str
	metadata_updates: Dict[str, Any]
	full_data: Optional[Dict[str, Any]] = None

class DeleteRecordIn(BaseModel):
	tenant_name: str
	unique_id: str
	s3_path: Optional[str] = None

class DeleteRecordsById(BaseModel):
	tenant_name: str
	unique_ids: List[str]
	s3_paths: Optional[List[str]] = None

class GetRecordsByIdsIn(BaseModel):
	tenant_name: str
	ids: List[str] = []

class GetRecordByIdIn(BaseModel):
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

class GetNotesWithTagsIn(BaseModel):
	tenant_name: str
	tag_ids: List[str]
	query_text: Optional[str] = None
	search_type: Optional[str] = "similarity"
	top_k: int = 1000 # For this, want to get all notes with tags so limit is high

class KeywordFilterQueryIn(BaseModel):
	tenant_name: str
	keyword: str
	filter: Dict[str, Any]
	top_k: int = default_query_limit

class GetMostRecentRecordsIn(BaseModel):
	tenant_name: str
	limit: int = 50

class GetImageToText(BaseModel):
	image_data: str

class EmbedText(BaseModel):
	text: str

class FileUploadIn(BaseModel):
	tenant_name: str
	file_data: str
	file_type: str
	unique_id: str
	slug: str = ''

class FileUrlIn(BaseModel):
	tenant_name: str
	file_name: str
	file_type: str
	slug: str = ''

class GetByTitlesIn(BaseModel):
	tenant_name: str
	titles: List[str]
	top_k: int = default_query_limit

@router.websocket("/ws/notes")
async def notes_websocket(websocket: WebSocket, tenant_name: str = fastapi.Query(...)):
	"""WebSocket endpoint for real-time note updates (scoped to tenant)."""
	await ws_manager.connect(tenant_name, websocket)
	try:
		while True:
			await websocket.receive_text()
	except WebSocketDisconnect:
		ws_manager.disconnect(tenant_name, websocket)
	except Exception as e:
		print(f"WebSocket error: {e}")
		ws_manager.disconnect(tenant_name, websocket)

@router.post("/insert_record")
async def route_insert_record(record_in: RecordIn, request: Request):
	try:
		# Normal embedding if no file data
		if not record_in.record.get("fileData", ""):
			record_in.record["vector"] = create_embedding(record_in.record.get("title", ""))
		else:
			if cloudfront_url_prefix in record_in.record.get("fileData", ""):
				record_in.record["fileData"] = remove_signed_params_from_url(record_in.record.get("fileData", ""))
			else:
				record_in.record["fileData"] = clean_base64(record_in.record.get("fileData", ""), record_in.record.get("fileType", "not existing"))
				# if file data, then have to create vector differently
				record_in.record["vector"] = create_file_embedding(record_in.record.get("fileData", ""), record_in.record.get("fileType", "not existing"), record_in.record.get("fileText", ""), record_in.record, is_mobile=request.state.device_type == "mobile")
				# Upload file data to s3 and then set fileData to url
				url = upload_file_bytes_to_s3(record_in.tenant_name, record_in.record.get("fileData", ""), record_in.record.get("uniqueid", ""), record_in.record.get("fileType", ""))
				record_in.record["fileData"] = url
				
		device_type = request.state.device_type
		device_id = request.state.device_id
		record_in.record["lastUpdateDevice"] = device_type
		record_in.record["lastUpdateDeviceId"] = device_id

		uniqueid = insert_record(record_in.tenant_name, WeaviateNote.from_rxdb(record_in.record))
		
		# Forward creation event to sync server
		await second_broadcast_event("note", {
			"event": "note_created",
			"tenant": record_in.tenant_name,
			"note": record_in.record,
			"uniqueid": uniqueid
		})
		
		return {"success": True, "uniqueid": uniqueid, "imageCaption": record_in.record.get("imageCaption", ""), "fileData": record_in.record.get("fileData", "")}
	except Exception as e:
		traceback.print_exc()
		# Add to retry queue
		retry_parameters = {
			"tenant_name": record_in.tenant_name,
			"record": record_in.record,
			"device_type": request.state.device_type,
			"device_id": request.state.device_id
		}
		RetryQueue.create("note_route_insert_record", retry_parameters)
		raise HTTPException(
			status_code=500,
			detail=str(e)
		)

@router.post("/upsert_notes")
async def route_upsert_records(records_in: RecordsIn, request: Request, background_tasks: BackgroundTasks):
	try:
		device_type = request.state.device_type
		device_id = request.state.device_id

		long_job_id = LongJob.insert('started', [])

		background_tasks.add_task(upsert_records, records_in.tenant_name, records_in.records, type='note', long_job_id=long_job_id, last_update_device=device_type, last_update_device_id=device_id)

		return {"message": "Records upserted successfully", "long_job_id": long_job_id}
	except Exception as e:
		print('Error upserting notes')
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_record_vector")
async def route_update_record_vector(vector_update: VectorUpdateIn, request: Request):
	try:
		# Create vector
		new_vector = create_embedding(vector_update.title)

		device_type = request.state.device_type
		device_id = request.state.device_id
		update_record_vector(vector_update.tenant_name, vector_update.unique_id, new_vector, {"lastUpdateDevice": device_type, "lastUpdateDeviceId": device_id})
		
		# Forward note vector update to sync server
		await second_broadcast_event("note", {
			"event": "note_vector_updated",
			"tenant": vector_update.tenant_name,
			"uniqueid": vector_update.unique_id,
			"title": vector_update.title
		})
		
		return {"message": "Record vector updated successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_record_metadata")
async def route_update_record_metadata(metadata_update: MetadataUpdateIn, request: Request):
	try:
		device_type = request.state.device_type
		device_id = request.state.device_id
		metadata_update.metadata_updates["lastUpdateDevice"] = device_type
		metadata_update.metadata_updates["lastUpdateDeviceId"] = device_id

		# if tags in metadata_updates, add tagIds to metadata_updates
		if "tags" in metadata_update.metadata_updates:
			metadata_update.metadata_updates["tagIds"] = [tag.get("uniqueid") for tag in metadata_update.metadata_updates.get("tags", [])]

		update_res = update_record_metadata(metadata_update.tenant_name, metadata_update.unique_id, metadata_update.metadata_updates)

		# If update failed, try to insert the record
		if update_res != 200 and metadata_update.full_data is not None and len(metadata_update.full_data) > 0:
			# Avoid inserting for the image file path updates getting called before insert
			if not ("<IMAGE-NOTE:>" in metadata_update.full_data.get("title", "") or "<DOC-NOTE:>" in metadata_update.full_data.get("title", "")):
				metadata_update.full_data["vector"] = create_embedding(metadata_update.full_data.get("title", ""))
				insert_record(metadata_update.tenant_name, WeaviateNote.from_rxdb(metadata_update.full_data))

		# Forward note metadata update to sync server
		await second_broadcast_event("note", {
			"event": "note_updated",
			"tenant": metadata_update.tenant_name,
			"uniqueid": metadata_update.unique_id,
			"metadata_updates": metadata_update.metadata_updates,
			"full_data": metadata_update.full_data
		})

		return {"message": "Record metadata updated successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_record")
async def route_delete_record(delete_record_in: DeleteRecordIn):
	try:
		delete_record(delete_record_in.tenant_name, delete_record_in.unique_id)
		print("Deleted record: ", delete_record_in.unique_id)
		cleaned_s3_path = None
		try:
			if delete_record_in.s3_path:
				cleaned_s3_path = remove_signed_params_from_url(delete_record_in.s3_path)
				cleaned_s3_path = cleaned_s3_path.replace(cloudfront_url_prefix, '')
		except Exception as e:
			print("Error cleaning s3 path: ", e)
		delete_record(delete_record_in.tenant_name, delete_record_in.unique_id, "note", cleaned_s3_path)
		
		# Forward note deletion to sync server
		await second_broadcast_event("note", {
			"event": "note_deleted",
			"tenant": delete_record_in.tenant_name,
			"uniqueid": delete_record_in.unique_id,
			"s3_path": delete_record_in.s3_path
		})
		
		return {"message": "Record deleted successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_records_by_id")
async def route_delete_records_by_id(delete_record_in: DeleteRecordsById):
	try:
		delete_records_by_ids(delete_record_in.tenant_name, delete_record_in.unique_ids, "note", delete_record_in.s3_paths)
		
		# Forward bulk note deletion to sync server
		await second_broadcast_event("note", {
			"event": "notes_deleted",
			"tenant": delete_record_in.tenant_name,
			"uniqueids": delete_record_in.unique_ids,
			"s3_paths": delete_record_in.s3_paths
		})
		
		return {"message": "Records deleted successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_all_records/{tenant_name}")
async def route_delete_all_records(tenant_name: str):
	try:
		delete_all_records(tenant_name)
		return {"message": "All records deleted successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/get_records_by_ids")
async def route_get_records_by_ids(get_records_in: GetRecordsByIdsIn):
	try:
		records = get_records_by_ids(get_records_in.tenant_name, get_records_in.ids)
		return {"records": records}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/get_record_by_id")
async def route_get_record_by_id(get_record_in: GetRecordByIdIn):
	try:
		record = get_record_by_id(get_record_in.tenant_name, get_record_in.record_id)
		if record is None:
			raise HTTPException(status_code=404, detail="Record not found")
		return {"record": record}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))


@router.post("/query_by_vector")
async def route_query_by_vector(query_in: QueryIn):
	try:
		query_vector = query_in.query_vector
		if not query_vector and query_in.query_text:
			query_vector = create_embedding(query_in.query_text, use_our_embedding=do_milvus_querying)
		start_time = datetime.now()
		results = query_by_vector(query_in.tenant_name, query_vector, query_in.top_k, query_in.similarity_setting)
		end_time = datetime.now()
		execution_time = (end_time - start_time).total_seconds()
		print(f"Vector query execution time: {execution_time} seconds")
		return {"results": results['results'], "execution_time_seconds": execution_time}
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

@router.post("/get_notes_with_tags")
async def route_get_notes_with_tags(get_notes_with_tags_in: GetNotesWithTagsIn):
	try:
		filter = None
		if do_milvus_querying:
			# According to Zilliz/Milvus docs, the idiomatic way to test that an ARRAY field
			# contains *any* member of a list is to use the ARRAY_CONTAINS_ANY operator:
			#     ARRAY_CONTAINS_ANY(field_name, [val1, val2, ...])
			#
			# Build that expression dynamically for the supplied tag IDs.
			import json
			if get_notes_with_tags_in.tag_ids:
				# json.dumps will serialise the list into the bracketed, quoted form Milvus expects
				tag_list_expr = json.dumps(get_notes_with_tags_in.tag_ids)
				filter = f'ARRAY_CONTAINS_ANY(tagIds, {tag_list_expr})' # for AND (has all tags), ARRAY_CONTAINS_ALL
				print("Milvus tagIds filter:", filter)
			else:
				# No tag IDs supplied → no additional filter
				filter = None
		else:
			# Weaviate / non-Milvus path
			filter = Filter.by_property("tagIds").contains_any(get_notes_with_tags_in.tag_ids)

		# If passed in a query_text, use that to filter with vector + tags
		if get_notes_with_tags_in.query_text:
			if get_notes_with_tags_in.search_type.lower() == "similarity":
				embedding = create_embedding(get_notes_with_tags_in.query_text, use_our_embedding=do_milvus_querying)
				results = query_by_vector_with_filter(
					get_notes_with_tags_in.tenant_name,
					embedding,
					filter,
					min(get_notes_with_tags_in.top_k, default_query_limit)
				)
			else:
				results = query_by_keyword_with_filter(
					get_notes_with_tags_in.tenant_name,
					get_notes_with_tags_in.query_text,
					filter,
					min(get_notes_with_tags_in.top_k, default_query_limit)
				)
		else:
			# If no query_text, just use the filter to get all notes with tags
			results = query_by_filter(
				get_notes_with_tags_in.tenant_name,
				filter,
				get_notes_with_tags_in.top_k,
				# get connected results to False because there can be thousands of notes
			)

		return {"results": results['results']}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))


@router.post("/query_by_keyword")
async def route_query_by_keyword(keyword_query_in: KeywordQueryIn):
	try:
		if do_milvus_querying:
			filter_expr = 'recordType == "note"'
			results = milvus_general.query_by_keyword_with_filter(
				keyword_query_in.tenant_name,
				keyword_query_in.keyword,
				filter_expr,
				max(keyword_query_in.top_k, 50)
			)
			return {"results": results['results']}
		else:
			filter_weav = Filter.by_property("recordType").equal("note")
			results = query_by_keyword_with_filter(
				keyword_query_in.tenant_name,
				keyword_query_in.keyword,
				filter_weav,
				max(keyword_query_in.top_k, 50)
			)
			return {"results": results['results']}
	except Exception as e:
		try:
			# Fallback to a smaller result size
			if do_milvus_querying:
				filter_expr = 'recordType == "note"'
				results = milvus_general.query_by_keyword_with_filter(
					keyword_query_in.tenant_name,
					keyword_query_in.keyword,
					filter_expr,
					2
				)
			else:
				filter_weav = Filter.by_property("recordType").equal("note")
				results = query_by_keyword_with_filter(
					keyword_query_in.tenant_name,
					keyword_query_in.keyword,
					filter_weav,
					2
				)
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

@router.post("/get_most_recent_records")
async def route_get_most_recent_records(get_most_recent_records_in: GetMostRecentRecordsIn):
	try:
		results = get_most_recent_records(get_most_recent_records_in.tenant_name, get_most_recent_records_in.limit)
		return {"results": results['results']}
	except Exception as e:
		return {"results": []}

@router.post("/image-to-text")
async def route_image_to_text(get_image_request_to_text: GetImageToText):
	try:
		if not get_image_request_to_text.image_data:
			raise HTTPException(status_code=400, detail="No image data provided")
		get_image_request_to_text.image_data = clean_base64(get_image_request_to_text.image_data)
		return {"text": get_image_to_text(get_image_request_to_text.image_data)}
	except Exception as e:
		raise HTTPException(status_code=500, detail="Internal error") from e


@router.post("/embed-text")
async def route_embed_text(embed_text: EmbedText):
	"""
	If the user's computer can't embed, will embed here
	TODO: can cost optimize + secure to registered users to prevent abuse
	"""
	try:
		return {"embedding": create_embedding(embed_text.text)}
	except Exception as e:
		raise HTTPException(status_code=500, detail="Internal error") from e

@router.post("/upload-file")
async def route_upload_file(file_upload: FileUploadIn):
	"""
	Upload a file to S3 and return the URL
	"""
	try:
		cleaned_file_data = clean_base64(file_upload.file_data, file_upload.file_type)
		url = upload_file_bytes_to_s3(
			file_upload.tenant_name,
			cleaned_file_data,
			file_upload.unique_id,
			file_upload.file_type,
			"constella-users",
			file_upload.slug
		)
		return {"url": url}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/get-file-url")
async def route_get_file_url(file_url_in: FileUrlIn):
	"""
	Get the cloudfront URL for a file
	"""
	try:
		url = get_file_url_from_path(
			file_url_in.tenant_name,
			file_url_in.file_name,
			file_url_in.file_type,
			file_url_in.slug
		)
		signed_url = get_signed_file_url(url)
		return {"url": signed_url}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/get-by-titles")
async def route_get_by_titles(get_by_titles_in: GetByTitlesIn):
	"""
	Get all notes whose title matches any value in the provided list.
	"""
	try:
		if do_milvus_querying:
			filter_expr = milvus_general.convert_to_milvus_filter({"title": get_by_titles_in.titles})
			results = milvus_general.query_by_filter(
				get_by_titles_in.tenant_name,
				filter_expr,
				get_by_titles_in.top_k,
				get_connected_results=False
			)
			return {"results": results['results']}
		else:
			filter = Filter.by_property("title").contains_any(get_by_titles_in.titles)
			results = query_by_filter(
				get_by_titles_in.tenant_name,
				filter,
				get_by_titles_in.top_k,
				get_connected_results=False
			)
			return {"results": results['results']}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/ocr-note")
async def route_ocr_note(ocr_note_in: OCRNoteIn, request: Request):
	try:
		# Normal embedding if no file data
		ocr_note_in.record["fileData"] = clean_base64(ocr_note_in.record.get("fileData", ""), ocr_note_in.record.get("fileType", "not existing"))

		ocr_json = openai_ocr_image_to_text(ocr_note_in.record["fileData"])

		image_summary = ocr_json.get("overall_img_description", "")

		# if file data, then have to create vector differently
		ocr_note_in.record["vector"] = create_embedding(image_summary)

		# Upload file data to s3 and then set fileData to url
		url = upload_file_bytes_to_s3(ocr_note_in.tenant_name, ocr_note_in.record.get("fileData", ""), ocr_note_in.record.get("uniqueid", ""), ocr_note_in.record.get("fileType", ""))
		ocr_note_in.record["fileData"] = url

		# Update the title + fileText
		ocr_note_in.record["title"] = image_note_prefix + image_summary
		ocr_note_in.record["fileText"] = format_ocr_json_to_string(ocr_json)

		device_type = request.state.device_type
		device_id = request.state.device_id
		ocr_note_in.record["lastUpdateDevice"] = device_type
		ocr_note_in.record["lastUpdateDeviceId"] = device_id

		uniqueid = insert_record(ocr_note_in.tenant_name, WeaviateNote.from_rxdb(ocr_note_in.record))
		
		# Forward OCR note creation to sync server
		await second_broadcast_event("note", {
			"event": "note_created",
			"tenant": ocr_note_in.tenant_name,
			"note": ocr_note_in.record,
			"uniqueid": uniqueid,
			"ocr_data": ocr_json
		})
	
		return {"success": True, "ocr_data": ocr_json, "image_record": ocr_note_in.record}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(
			status_code=500,
			detail=str(e)
		)

class ImageMatchesInstructionIn(BaseModel):
	image_data: str
	instruction: str

@router.post("/image-matches-instruction")
async def route_image_matches_instruction(instruction_in: ImageMatchesInstructionIn):
	try:
		matches = image_matches_instruction(instruction_in.image_data, instruction_in.instruction)
		return {"matches": matches.get("matches", False), "explanation": matches.get("explanation", "")}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/broadcast-event")
async def route_notes_broadcast_event(message: Dict[str, Any]):
    """Receive a note broadcast *from* the sync server and fan-out to in-process clients."""
    await ws_manager.broadcast(message)
    return {"success": True}