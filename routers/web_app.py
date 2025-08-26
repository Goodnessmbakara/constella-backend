import json
from fastapi import APIRouter, WebSocketDisconnect, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from fastapi import WebSocket
from ai.ai_api import stream_anthropic_response, stream_google_response
import requests
from typing import List, Dict, Optional
from utils.constella.stella_chat import parse_frontend_messages
from ai.stella.prompts import (get_system_prompt, stella_calling_realtime_instructions,
	stella_calling_realtime_max_tokens)
import jwt
import os
from db.models.constella.constella_shared_view import ConstellaSharedView
from fastapi.responses import JSONResponse
import traceback
from utils.loops import send_transactional_email
from db.models.constella.long_job import LongJob
import df

router = APIRouter(
	prefix="/web-app",
	tags=["web-app"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

class DeepFindReq(BaseModel):
	query: str
	url: HttpUrl
	max_links: Optional[int] = 200
	check_interval: Optional[int] = 50
	tenant_name: Optional[str] = None

@router.post("/deep-find")
async def deep_find(req: DeepFindReq, background_tasks: BackgroundTasks):
	"""
	Performs a deep search on a website to find information related to a query.
	Uses background tasks and long job tracking for asynchronous processing.
	"""
	try:
		# Create a long job to track the progress
		long_job_id = LongJob.insert('started', [], type='deep-find')

		# if url does not start with https://www., add it
		if not str(req.url).startswith("https://"):
			req.url = "https://" + str(req.url)
		
		# Add the crawl task to background tasks
		background_tasks.add_task(
			process_deep_find,
			req.url,
			req.query,
			req.max_links,
			req.check_interval,
			req.tenant_name,
			long_job_id
		)
		
		return {"message": "Deep find search started", "long_job_id": long_job_id}
	except Exception as e:
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=f"Error starting deep find: {str(e)}")

async def process_deep_find(
	url: HttpUrl, 
	query: str, 
	max_links: int, 
	check_interval: int, 
	tenant_name: str,
	long_job_id: str
):
	"""
	Background task to process the deep find request and update the long job status.
	"""
	try:
		# Update job status to processing
		LongJob.update_status(long_job_id, "processing")
		
		# Call the crawl function from df.py
		result = await df.crawl_website_for_information(
			url, 
			query, 
			max_links=max_links, 
			check_interval=check_interval, 
			tenant_name=tenant_name
		)
		
		# Update the long job with the results
		LongJob.update_status(long_job_id, "completed", result)
		
	except Exception as e:
		print(f"Error in deep find process: {str(e)}")
		traceback.print_exc()
		# Update job status to error
		LongJob.update_status(long_job_id, "error", {"error": str(e)})


@router.get("/job-status/{job_id}")
async def get_job_status(job_id: str):
    """
    Get the status of a long-running job and its results if completed.
    
    Args:
        job_id: The ID of the long job to check
        
    Returns:
        JSON response with job status and results if available
    """
    try:
        # Get the job data with full object
        job_data = LongJob.get_status(job_id, return_object=True)
        
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
            
        # Return the job status and results
        return {
            "status": job_data.get("status"),
            "type": job_data.get("type", ""),
            "created_at": job_data.get("created_at"),
            # Only include results if the job is completed
            "results": job_data.get("results") if job_data.get("status") == "completed" else None,
            "error": job_data.get("results", {}).get("error") if job_data.get("status") == "error" else None
        }
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error retrieving job status: {str(e)}")
