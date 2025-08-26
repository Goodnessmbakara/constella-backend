from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
import traceback
from weaviate.classes.query import Filter
from typing import List, Dict, Any
from db.weaviate.operations.general import (delete_all_records, delete_record, insert_record,
	query_by_filter, query_by_keyword, query_by_keyword_with_filter, query_by_vector,
	query_by_vector_with_filter, update_record_metadata, update_record_vector, upsert_records, do_milvus_querying)
from db.weaviate.records.general_record import GeneralWeaviateRecord
from ai.embeddings import create_embedding
from db.weaviate.records.tag import WeaviateTag
from db.weaviate.operations.tag_ops import get_all_tags
from constants import default_query_limit
from ai.tags.auto_tag import get_auto_tag
from utils.websockets.tags_websocket import tags_ws_manager as ws_manager
from utils.websockets.remote_broadcast import second_broadcast_event
from db.milvus.operations import general as milvus_general
import json

router = APIRouter(
	prefix="/constella_db/tag",
	tags=["constella_db_tag"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

class TagIn(BaseModel):
	tenant_name: str
	record: dict

class TagsIn(BaseModel):
	tenant_name: str
	records: List[Dict[str, Any]]

class VectorUpdateIn(BaseModel):
	tenant_name: str
	unique_id: str
	new_vector: dict

class MetadataUpdateIn(BaseModel):
	tenant_name: str
	unique_id: str
	metadata_updates: Dict[str, Any]

class DeleteTagIn(BaseModel):
	tenant_name: str
	unique_id: str

class QueryIn(BaseModel):
	tenant_name: str
	query_vector: List[float] = None
	query_text: str = None
	top_k: int = default_query_limit

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

class GetAllTagsIn(BaseModel):
	tenant_name: str

class GetAutoTagIn(BaseModel):
	note: str
	tag_names: List[str]

@router.post("/insert_tag")
async def route_insert_tag(tag_in: TagIn, request: Request):
	try:
		device_type = request.state.device_type
		device_id = request.state.device_id
		tag_in.record["lastUpdateDevice"] = device_type
		tag_in.record["lastUpdateDeviceId"] = device_id

		uniqueid = insert_record(tag_in.tenant_name, WeaviateTag.from_rxdb(tag_in.record))
		
		tag_in.record["uniqueid"] = uniqueid
		
		# Forward tag creation event to sync server
		await second_broadcast_event("tag", {
			"event": "tag_created",
			"tenant": tag_in.tenant_name,
			"tag": tag_in.record,
			"uniqueid": uniqueid
		})
		
		return {"message": "Tag inserted successfully", "uniqueid": uniqueid}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/upsert_tags")
async def route_upsert_tags(tags_in: TagsIn, request: Request, background_tasks: BackgroundTasks):
	try:
		device_type = request.state.device_type
		device_id = request.state.device_id

		# Create an immutable copy of the records to avoid race conditions
		# between broadcast_updates and upsert_records tasks
		records_copy = list(tags_in.records)

		# Add a background task to broadcast updates after upsert completes
		async def broadcast_updates():
			for record in records_copy:
				if record is not None:  # Additional safety check
					await second_broadcast_event("tag", {
						"event": "tag_updated",
						"tenant": tags_in.tenant_name,
						"tag": record
					})

		background_tasks.add_task(upsert_records, tags_in.tenant_name, tags_in.records, type='tag', long_job_id='', last_update_device=device_type, last_update_device_id=device_id)
		background_tasks.add_task(broadcast_updates)

		return {"message": "Tags upserted successfully"}
	except Exception as e:
		print('Error upserting tags')
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_tag_vector")
async def route_update_tag_vector(vector_update: VectorUpdateIn, request: Request):
	try:
		new_vector = [vector_update.new_vector[key] for key in vector_update.new_vector]
		device_type = request.state.device_type
		device_id = request.state.device_id
		update_record_vector(vector_update.tenant_name, vector_update.unique_id, new_vector, {"lastUpdateDevice": device_type, "lastUpdateDeviceId": device_id})
		
		# Forward tag vector update to sync server
		await second_broadcast_event("tag", {
			"event": "tag_vector_updated",
			"tenant": vector_update.tenant_name,
			"uniqueid": vector_update.unique_id
		})

		return {"message": "Tag vector updated successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_tag_metadata")
async def route_update_tag_metadata(metadata_update: MetadataUpdateIn, request: Request):
	try:
		device_type = request.state.device_type
		device_id = request.state.device_id
		metadata_update.metadata_updates["lastUpdateDevice"] = device_type
		metadata_update.metadata_updates["lastUpdateDeviceId"] = device_id
		update_record_metadata(metadata_update.tenant_name, metadata_update.unique_id, metadata_update.metadata_updates)
		
		# Forward tag metadata update to sync server
		await second_broadcast_event("tag", {
			"event": "tag_updated",
			"tenant": metadata_update.tenant_name,
			"uniqueid": metadata_update.unique_id,
			"metadata_updates": metadata_update.metadata_updates
		})
		
		return {"message": "Tag metadata updated successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_tag")
async def route_delete_tag(delete_tag_in: DeleteTagIn):
	try:
		# First, delete the tag record itself
		delete_record(delete_tag_in.tenant_name, delete_tag_in.unique_id, "tag")

		# Build a filter to find all notes that reference this tag
		if do_milvus_querying:
			filter_expr = milvus_general.convert_to_milvus_filter({"tagIds": [delete_tag_in.unique_id]})
			notes_with_tag = milvus_general.query_by_filter(
				delete_tag_in.tenant_name,
				filter_expr,
				10000,
				get_connected_results=False
			).get('results', [])
		else:
			notes_with_tag = query_by_filter(
				delete_tag_in.tenant_name,
				Filter.by_property("tagIds").contains_any([delete_tag_in.unique_id]),
				10000
			).get('results', [])

		# Remove the deleted tag from each affected note
		for note in notes_with_tag:
			filtered_tags = [tag for tag in note.get("tags", []) if str(tag.get("uniqueid", "")) != delete_tag_in.unique_id]
			filtered_tag_ids = [tag.get("uniqueid") for tag in filtered_tags]
			update_record_metadata(delete_tag_in.tenant_name, note.get("uniqueid"), {
				"tags": filtered_tags,
				"tagIds": filtered_tag_ids
			})

		# Broadcast the deletion event
		await second_broadcast_event("tag", {
			"event": "tag_deleted",
			"tenant": delete_tag_in.tenant_name,
			"uniqueid": delete_tag_in.unique_id
		})

		return {"message": "Tag deleted successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_all_tags/{tenant_name}")
async def route_delete_all_tags(tenant_name: str):
	try:
		delete_all_records(tenant_name)
		return {"message": "All tags deleted successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/query_tags_by_vector")
async def route_query_tags_by_vector(query_in: QueryIn):
	try:
		query_vector = query_in.query_vector
		if not query_vector and query_in.query_text:
			query_vector = create_embedding(query_in.query_text)
		results = query_by_vector(query_in.tenant_name, query_vector, query_in.top_k)
		return {"results": results}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/query_tags_by_vector_with_filter")
async def route_query_tags_by_vector_with_filter(filter_query_in: FilterQueryIn):
	try:
		if do_milvus_querying:
			flt_expr = milvus_general.convert_to_milvus_filter(filter_query_in.filter)

			results = milvus_general.query_by_vector_with_filter(
				filter_query_in.tenant_name,
				filter_query_in.query_vector,
				flt_expr,
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

@router.post("/query_tags_by_keyword")
async def route_query_tags_by_keyword(keyword_query_in: KeywordQueryIn):
	try:
		results = query_by_keyword(keyword_query_in.tenant_name, keyword_query_in.keyword, keyword_query_in.top_k)
		return {"results": results}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/query_tags_by_keyword_with_filter")
async def route_query_tags_by_keyword_with_filter(keyword_filter_query_in: KeywordFilterQueryIn):
	try:
		if do_milvus_querying:
			flt_expr = milvus_general.convert_to_milvus_filter(keyword_filter_query_in.filter)

			results = milvus_general.query_by_keyword_with_filter(
				keyword_filter_query_in.tenant_name,
				keyword_filter_query_in.keyword,
				flt_expr,
				keyword_filter_query_in.top_k
			)
			return {"results": results}
		else:
			results = query_by_keyword_with_filter(
				keyword_filter_query_in.tenant_name,
				keyword_filter_query_in.keyword,
				keyword_filter_query_in.filter,
				keyword_filter_query_in.top_k
			)
			return {"results": results}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/get_all_tags_for_user")
async def route_get_all_tags_for_user(get_all_tags_in: GetAllTagsIn):
	try:
		results = get_all_tags(get_all_tags_in.tenant_name)
		return {"results": results}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/get_auto_tag")
async def route_get_auto_tag(get_auto_tag_in: GetAutoTagIn):
	try:
		result = get_auto_tag(get_auto_tag_in.note, get_auto_tag_in.tag_names)
		print(result)
		return {"result": result}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

# Add WebSocket route for tags real-time updates

@router.websocket("/ws/tags")
async def tags_websocket(websocket: WebSocket, tenant_name: str = Query(...)):
    """WebSocket endpoint for real-time tag updates (scoped to tenant)."""
    await ws_manager.connect(tenant_name, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(tenant_name, websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        ws_manager.disconnect(tenant_name, websocket)

@router.post("/broadcast-event")
async def route_tags_broadcast_event(message: Dict[str, Any]):
    """Receive tag broadcast from sync server and send to local clients."""
    await ws_manager.broadcast(message)
    return {"success": True}