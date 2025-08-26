from datetime import datetime, timezone
from weaviate.exceptions import UnexpectedStatusCodeError
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from fastapi import BackgroundTasks
import traceback
from typing import Optional
from db.weaviate.operations.general import sync_by_last_modified
from ai.embeddings import create_embedding
from db.weaviate.records.note import WeaviateNote
from db.models.constella.long_job import LongJob
from db.models.constella.constella_integration import ConstellaIntegration
from utils.constella.syncing.integrations.integration_helper import sync_integrations_for_user
from utils.constella.syncing.syncing_helper import sync_everything_for_user

router = APIRouter(
	prefix="/constella_db",
	tags=["constella_db"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

class SyncByLastModifiedIn(BaseModel):
	tenant_name: str
	last_sync_datetime_utc: datetime # should be in UTC to ensure consistency
	user_email: Optional[str] = None
	use_background_task: Optional[bool] = False
	use_batching: Optional[bool] = False
	limit: Optional[int] = 1000
	offset: Optional[int] = 0

class LongJobStatusIn(BaseModel):
	long_job_id: str
	return_object: Optional[bool] = False

@router.post("/sync_by_last_modified")
async def route_sync_by_last_modified(sync_in: SyncByLastModifiedIn, request: Request, background_tasks: BackgroundTasks):
	try:
		# set timezone as UTC but passed in as local time (gets converted here)
		sync_in.last_sync_datetime_utc = sync_in.last_sync_datetime_utc.replace(tzinfo=timezone.utc)
				
		curr_device_id = request.state.device_id
		
		if sync_in.use_batching:
			# Use batching with limit and offset
			results = sync_by_last_modified(
				sync_in.tenant_name, 
				sync_in.last_sync_datetime_utc, 
				curr_device_id,
				limit=sync_in.limit,
				offset=sync_in.offset
			)
			return results
		elif not sync_in.use_background_task:
			results = sync_by_last_modified(sync_in.tenant_name, sync_in.last_sync_datetime_utc, curr_device_id)
			integrations_results = sync_integrations_for_user(sync_in.tenant_name, sync_in.user_email)
			results['results'].extend(integrations_results)
			return results
		else:
			long_job_id = LongJob.insert('started', {}, 'sync', sync_in.user_email)
			background_tasks.add_task(sync_everything_for_user, sync_in.tenant_name, sync_in.last_sync_datetime_utc, curr_device_id, sync_in.user_email, long_job_id)
			return {"long_job_id": long_job_id}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))



@router.post("/get_long_job_status")
async def route_get_long_job_status(job_status_in: LongJobStatusIn):
	try:
		status = LongJob.get_status(job_status_in.long_job_id, job_status_in.return_object)
		if status is None:
			raise HTTPException(status_code=404, detail="Job not found")
		if job_status_in.return_object:
			return status
		else:
			return {"status": status}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=str(e))
