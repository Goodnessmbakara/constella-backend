from fastapi import APIRouter, HTTPException, Request
from fastapi import BackgroundTasks
from pydantic import BaseModel
import traceback
from typing import List, Dict, Any, Optional
from db.weaviate.operations.general import (delete_record, insert_record, update_record_metadata,
	upsert_records)
from db.weaviate.records.misc import WeaviateMisc
from db.models.constella.long_job import LongJob

router = APIRouter(
	prefix="/constella_db/misc",
	tags=["constella_db_misc"],
)

class RecordIn(BaseModel):
	tenant_name: str
	record: dict

class MetadataUpdateIn(BaseModel):
	tenant_name: str
	unique_id: str
	metadata_updates: Dict[str, Any]
	full_data: Optional[Dict[str, Any]] = None

class DeleteRecordIn(BaseModel):
	tenant_name: str
	unique_id: str
	type: str

@router.post("/insert_record")
async def route_insert_record(record_in: RecordIn, request: Request):
	try:
		# Add device info
		device_type = request.state.device_type
		device_id = request.state.device_id
		record_in.record["lastUpdateDevice"] = device_type
		record_in.record["lastUpdateDeviceId"] = device_id

		try:
			# Try insert first
			uniqueid = insert_record(record_in.tenant_name, WeaviateMisc.from_rxdb(record_in.record))
		except Exception as insert_error:
			# If insert fails, try update
			uniqueid = record_in.record.get("uniqueid")
			if not uniqueid:
				raise insert_error
			update_record_metadata(record_in.tenant_name, uniqueid, record_in.record)
			
		return {"success": True, "uniqueid": uniqueid}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

class RecordsIn(BaseModel):
	tenant_name: str
	records: List[Dict[str, Any]]

@router.post("/upsert_records")
async def route_upsert_records(records_in: RecordsIn, request: Request, background_tasks: BackgroundTasks):
	try:
		device_type = request.state.device_type
		device_id = request.state.device_id
		
		long_job_id = LongJob.insert('started', [])

		background_tasks.add_task(upsert_records, records_in.tenant_name, records_in.records, type='misc', long_job_id=long_job_id, last_update_device=device_type, last_update_device_id=device_id)

		return {"message": "Records upserted successfully", "long_job_id": long_job_id}
	except Exception as e:
		print('Error upserting notes')
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.put("/update_record_metadata")
async def route_update_record_metadata(metadata_update: MetadataUpdateIn, request: Request):
	try:
		device_type = request.state.device_type
		device_id = request.state.device_id
		metadata_update.metadata_updates["lastUpdateDevice"] = device_type
		metadata_update.metadata_updates["lastUpdateDeviceId"] = device_id

		res = update_record_metadata(metadata_update.tenant_name, metadata_update.unique_id, metadata_update.metadata_updates)
		# Try inserting if update failed (i.e. update called before insert)
		if res != 200 and metadata_update.full_data is not None and len(metadata_update.full_data) > 0:
			insert_record(metadata_update.tenant_name, WeaviateMisc.from_rxdb(metadata_update.full_data))
		return {"message": "Record metadata updated successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_record")
async def route_delete_record(delete_record_in: DeleteRecordIn):
	try:
		delete_record(delete_record_in.tenant_name, delete_record_in.unique_id, delete_record_in.type)
		return {"message": "Record deleted successfully"}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))