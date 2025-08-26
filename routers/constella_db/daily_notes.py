from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import traceback
from typing import List, Dict, Any
from db.weaviate.operations.general import (
	insert_record, upsert_records, update_record_vector, update_record_metadata,
)
from ai.embeddings import create_embedding
from db.weaviate.records.daily_note import WeaviateDailyNote
from constants import default_query_limit

router = APIRouter(
	prefix="/constella_db/daily_note",
	tags=["constella_db_daily_note"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

class DailyNoteIn(BaseModel):
	tenant_name: str
	record: dict

class DailyNotesIn(BaseModel):
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

class DeleteDailyNoteIn(BaseModel):
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

@router.post("/insert_daily_note")
async def route_insert_daily_note(daily_note_in: DailyNoteIn):
	try:
		insert_record(daily_note_in.tenant_name, WeaviateDailyNote.from_rxdb(daily_note_in.record))
		return {"message": "Daily note inserted successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.post("/upsert_daily_notes")
async def route_upsert_daily_notes(daily_notes_in: DailyNotesIn):
	try:
		upsert_records(daily_notes_in.tenant_name, daily_notes_in.records)
		return {"message": "Daily notes upserted successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_daily_note_vector")
async def route_update_daily_note_vector(vector_update: VectorUpdateIn):
	try:
		new_vector = [vector_update.new_vector[key] for key in vector_update.new_vector]
		update_record_vector(vector_update.tenant_name, vector_update.unique_id, new_vector)
		return {"message": "Daily note vector updated successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_daily_note_metadata")
async def route_update_daily_note_metadata(metadata_update: MetadataUpdateIn):
	try:
		status = update_record_metadata(metadata_update.tenant_name, metadata_update.unique_id, metadata_update.metadata_updates)
		if status == 404:
			insert_record(metadata_update.tenant_name, WeaviateDailyNote.from_rxdb( metadata_update.metadata_updates))
		return {"message": "Daily note metadata updated successfully"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))