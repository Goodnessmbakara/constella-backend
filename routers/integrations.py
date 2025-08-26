from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from ai.ai_api import (create_chat_completion, create_chat_message)
import os
import uuid
from typing import List, Optional, Dict, Any
from db.models.constella.constella_signup import ConstellaSignup
from utils.loops import create_loops_contact, update_contact_property, send_event
from db.models.constella.constella_feature_request import ConstellaFeatureRequest
from db.models.constella.constella_auth import ConstellaAuth
from utils.constella.files.s3.s3 import sign_url
from db.models.constella.constella_integration import ConstellaIntegration
from utils.constella.syncing.integrations.readwise import fetch_from_export_api
from db.models.constella.long_job import LongJob
import traceback
from utils.constella.syncing.integrations.integration_helper import sync_integrations_for_user
from db.models.constella.constella_subscription import ConstellaSubscription
from arcadepy import Arcade

router = APIRouter(
	prefix="/integrations",
	tags=["integrations"],
	# dependencies=[Depends(validate_access_token)],
	# responses={404: {"description": "Not found"}},
)

arcade_client = Arcade()  # Uses ARCADE_API_KEY from env

class UpdateIntegrationRequest(BaseModel):
	user_email: str
	integration_name: str
	property_name: str
	property_value: str

class GetIntegrationRequest(BaseModel):
	user_email: str

class InitialSyncRequest(BaseModel):
	tenant_name: str
	user_email: str
	integration_name: str
	api_key: str

class SyncIntegrationsRequest(BaseModel):
	tenant_name: str
	user_email: str

class CreateApiKeyRequest(BaseModel):
	auth_user_id: str

class CreateArcadeIntegrationRequest(BaseModel):
    integration_name: str  # Arcade tool name, e.g., "Gmail.ListEmails"
    user_id: str           # Your app's unique user id (email/uuid)

class WaitForArcadeAuthorizationRequest(BaseModel):
    integration_name: str
    user_id: str

class RemoveArcadeIntegrationRequest(BaseModel):
    integration_name: str
    user_id: str

def sync_readwise_background(tenant_name: str, user_email: str, api_key: str, long_job_id: str):
	try:
		fetch_from_export_api(tenant_name, api_key)
		print("Updating long job status to completed")
		LongJob.update_status(long_job_id, 'completed')
		last_updated_utc = int(datetime.utcnow().timestamp() * 1000)
		ConstellaIntegration.update_integration_property(user_email, 'readwise', 'lastUpdated', last_updated_utc)
	except Exception as e:
		traceback.print_exc()
		print("Error syncing Readwise: " + str(e))
		print('updating long job status to failed')
		LongJob.update_status(long_job_id, 'failed', {'error': str(e)})

@router.post("/get")
async def get_user_integration(
	request: GetIntegrationRequest
):
	try:
		integration = ConstellaIntegration.get_by_email(request.user_email)
		if integration:
			# Convert Integration objects to dict for JSON serialization
			return {
				"integrations": {
					name: {
						"apiKey": getattr(integ, "apiKey", None),
						"lastUpdated": getattr(integ, "lastUpdated", None),
						"arcade": getattr(integ, "arcade", None),
					} for name, integ in integration.integrations.items()
				}
			}
		# Otherwise, create an integration object for user
		integration = ConstellaIntegration(user_email=request.user_email, integrations={})
		integration.save()
		return {"integrations": {}}
	except Exception as e:
		print(e)
		raise HTTPException(status_code=400, detail=str(e))

@router.post("/update")
async def update_user_integration(
	update_data: UpdateIntegrationRequest
):
	try:
		ConstellaIntegration.update_integration_property(
			user_email=update_data.user_email,
			integration_name=update_data.integration_name,
			property_name=update_data.property_name,
			property_value=update_data.property_value
		)
		return {"message": "Integration updated successfully"}
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))

@router.post("/arcade/create")
async def arcade_create_integration(request: CreateArcadeIntegrationRequest):
    try:
        # Kick off Arcade authorization for the specific tool
        auth_response = arcade_client.tools.authorize(
            tool_name=request.integration_name,
            user_id=request.user_id,
        )

        # Persist initial Arcade auth status under integrations[name].arcade
        arcade_data: Dict[str, Any] = {
            "status": getattr(auth_response, "status", None),
            "url": getattr(auth_response, "url", None),
        }
        ConstellaIntegration.update_integration_property(
            user_email=request.user_id,  # Aligning on email-as-user_id per existing model
            integration_name=request.integration_name,
            property_name="arcade",
            property_value=arcade_data,
        )

        # If already completed, fetch tool details for richer persistence
        if getattr(auth_response, "status", None) == "completed":
            tool = arcade_client.tools.get(
                tool_name=request.integration_name,
                user_id=request.user_id,
            )
            tool_arcade_meta = {
                "requirements_met": getattr(getattr(tool, "requirements", None), "met", None),
                "auth_status": getattr(getattr(getattr(tool, "requirements", None), "authorization", None), "status", None),
                "token_status": getattr(getattr(getattr(tool, "requirements", None), "authorization", None), "token_status", None),
                "provider": getattr(getattr(getattr(tool, "requirements", None), "authorization", None), "provider_type", None),
                "description": getattr(tool, "description", None),
            }
            ConstellaIntegration.update_integration_property(
                user_email=request.user_id,
                integration_name=request.integration_name,
                property_name="arcade",
                property_value=tool_arcade_meta,
            )

        response: Dict[str, Any] = {
            "message": "Authorization initiated" if getattr(auth_response, "status", None) != "completed" else "Authorization completed",
            "status": getattr(auth_response, "status", None),
        }
        if getattr(auth_response, "status", None) != "completed":
            response["authorization_url"] = getattr(auth_response, "url", None)

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/arcade/wait_for_authorization")
async def arcade_wait_for_authorization(request: WaitForArcadeAuthorizationRequest):
    try:
        # Get a fresh authorization response (id/handle) to wait on
        auth_response = arcade_client.tools.authorize(
            tool_name=request.integration_name,
            user_id=request.user_id,
        )
        # Wait for completion (blocking call)
        completed = arcade_client.auth.wait_for_completion(auth_response)

        # Fetch tool details once completed
        tool = arcade_client.tools.get(
            tool_name=request.integration_name,
            user_id=request.user_id,
        )
        tool_arcade_meta = {
            "requirements_met": getattr(getattr(tool, "requirements", None), "met", None),
            "auth_status": getattr(getattr(getattr(tool, "requirements", None), "authorization", None), "status", None),
            "token_status": getattr(getattr(getattr(tool, "requirements", None), "authorization", None), "token_status", None),
            "provider": getattr(getattr(getattr(tool, "requirements", None), "authorization", None), "provider_type", None),
            "description": getattr(tool, "description", None),
        }
        ConstellaIntegration.update_integration_property(
            user_email=request.user_id,
            integration_name=request.integration_name,
            property_name="arcade",
            property_value=tool_arcade_meta,
        )

        return {
            "message": "Authorization completed",
            "status": getattr(completed, "status", "completed"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/arcade/remove")
async def arcade_remove_integration(request: RemoveArcadeIntegrationRequest):
    try:
        # Best-effort revoke in Arcade (some providers may not support revoke; API subject to change)
        try:
            arcade_client.auth.revoke(
                tool_name=request.integration_name,
                user_id=request.user_id,
            )
        except Exception:
            # Proceed even if revoke isn't supported
            pass

        # Remove from our database
        ConstellaIntegration.remove_integration(
            user_email=request.user_id,
            integration_name=request.integration_name,
        )
        return {"message": "Integration removed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync-initial-integration")
async def sync_initial_integration(
	request: InitialSyncRequest, 
	background_tasks: BackgroundTasks
):
	try:
		if request.integration_name == "readwise":
			# Create a long job and run sync in background
			long_job_id = LongJob.insert('started', {}, 'initial_sync', request.user_email)
			background_tasks.add_task(
				sync_readwise_background,
				request.tenant_name,
				request.user_email,
				request.api_key,
				long_job_id
			)
			return {"message": "Sync started", "long_job_id": long_job_id}
		else:
			raise HTTPException(status_code=400, detail=f"Integration {request.integration_name} not supported")
			
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))

@router.post("/sync-integrations")
async def sync_integrations(
	request: SyncIntegrationsRequest,
	background_tasks: BackgroundTasks
):
	try:
		long_job_id = LongJob.insert('started', {}, 'sync_integrations', request.user_email)
		background_tasks.add_task(
			sync_integrations_for_user,
			request.tenant_name,
			request.user_email,
			long_job_id
		)
		return {"message": "Sync started", "long_job_id": long_job_id}	
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))

@router.post("/create-api-key")
async def create_api_key(
	request: CreateApiKeyRequest
):
	try:
		# Create API key
		api_key = ConstellaSubscription.add_api_key(auth_user_id=request.auth_user_id)
		if not api_key:
			raise HTTPException(status_code=400, detail="Failed to create API key")
			
		return {"api_key": api_key}
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))

