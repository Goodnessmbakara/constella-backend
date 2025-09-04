from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import traceback
import os
import uuid

# AI imports
from ai.ai_api import (create_chat_completion, create_chat_message)

# Database models
from db.models.constella.constella_signup import ConstellaSignup
from db.models.constella.constella_feature_request import ConstellaFeatureRequest
from db.models.constella.constella_auth import ConstellaAuth
from db.models.constella.constella_integration import ConstellaIntegration
from db.models.constella.long_job import LongJob
from db.models.constella.constella_subscription import ConstellaSubscription

# Utility imports
from utils.loops import create_loops_contact, update_contact_property, send_event
from utils.constella.files.s3.s3 import sign_url
from utils.constella.syncing.integrations.readwise import fetch_from_export_api
from utils.constella.syncing.integrations.integration_helper import sync_integrations_for_user

# External APIs
from arcadepy import Arcade

# Constants
SUPPORTED_INTEGRATIONS = {
    "readwise": "readwise"
}

JOB_TYPES = {
    "INITIAL_SYNC": "initial_sync",
    "SYNC_INTEGRATIONS": "sync_integrations"
}

JOB_STATUSES = {
    "STARTED": "started",
    "COMPLETED": "completed", 
    "FAILED": "failed"
}

ARCADE_AUTH_STATUSES = {
    "COMPLETED": "completed",
    "PENDING": "pending"
}

# Response messages
MESSAGES = {
    "INTEGRATION_UPDATED": "Integration updated successfully",
    "INTEGRATION_REMOVED": "Integration removed",
    "AUTH_INITIATED": "Authorization initiated",
    "AUTH_COMPLETED": "Authorization completed", 
    "SYNC_STARTED": "Sync started",
    "API_KEY_CREATION_FAILED": "Failed to create API key"
}

router = APIRouter(
    prefix="/integrations",
    tags=["integrations"],
    # dependencies=[Depends(validate_access_token)],
    # responses={404: {"description": "Not found"}},
)

arcade_client = Arcade()  # Uses ARCADE_API_KEY from env

# Request Models
class UpdateIntegrationRequest(BaseModel):
    """Request model for updating integration properties"""
    user_email: str
    integration_name: str
    property_name: str
    property_value: str

class GetIntegrationRequest(BaseModel):
    """Request model for getting user integrations"""
    user_email: str

class InitialSyncRequest(BaseModel):
    """Request model for initial integration sync"""
    tenant_name: str
    user_email: str
    integration_name: str
    api_key: str

class SyncIntegrationsRequest(BaseModel):
    """Request model for syncing all user integrations"""
    tenant_name: str
    user_email: str

class CreateApiKeyRequest(BaseModel):
    """Request model for creating API keys"""
    auth_user_id: str

class CreateArcadeIntegrationRequest(BaseModel):
    """Request model for creating Arcade integrations"""
    integration_name: str  # Arcade tool name, e.g., "Gmail.ListEmails"
    user_id: str           # Your app's unique user id (email/uuid)

class WaitForArcadeAuthorizationRequest(BaseModel):
    """Request model for waiting for Arcade authorization completion"""
    integration_name: str
    user_id: str

class RemoveArcadeIntegrationRequest(BaseModel):
    """Request model for removing Arcade integrations"""
    integration_name: str
    user_id: str

# Response Models
class IntegrationResponse(BaseModel):
    """Standard integration response model"""
    message: str
    status: Optional[str] = None
    authorization_url: Optional[str] = None

class SyncResponse(BaseModel):
    """Response model for sync operations"""
    message: str
    long_job_id: str

class ApiKeyResponse(BaseModel):
    """Response model for API key creation"""
    api_key: str

# Helper Functions
def get_current_timestamp_ms() -> int:
    """Get current timestamp in milliseconds"""
    return int(datetime.utcnow().timestamp() * 1000)

def safe_getattr(obj: Any, *attrs: str, default: Any = None) -> Any:
    """Safely get nested attributes from an object"""
    for attr in attrs:
        if obj is None:
            return default
        obj = getattr(obj, attr, None)
        if obj is None:
            return default
    return obj

def extract_arcade_tool_metadata(tool: Any) -> Dict[str, Any]:
    """Extract metadata from Arcade tool object"""
    requirements = safe_getattr(tool, "requirements")
    authorization = safe_getattr(requirements, "authorization")
    
    return {
        "requirements_met": safe_getattr(requirements, "met"),
        "auth_status": safe_getattr(authorization, "status"),
        "token_status": safe_getattr(authorization, "token_status"),
        "provider": safe_getattr(authorization, "provider_type"),
        "description": safe_getattr(tool, "description"),
    }

def create_arcade_auth_data(auth_response: Any) -> Dict[str, Any]:
    """Create initial Arcade auth data from response"""
    return {
        "status": safe_getattr(auth_response, "status"),
        "url": safe_getattr(auth_response, "url"),
    }

def update_integration_with_arcade_data(user_id: str, integration_name: str, arcade_data: Dict[str, Any]) -> None:
    """Update integration with Arcade data"""
    ConstellaIntegration.update_integration_property(
        user_email=user_id,
        integration_name=integration_name,
        property_name="arcade",
        property_value=arcade_data,
    )

def handle_completed_arcade_auth(user_id: str, integration_name: str) -> None:
    """Handle completed Arcade authorization by fetching and storing tool details"""
    try:
        tool = arcade_client.tools.get(
            tool_name=integration_name,
            user_id=user_id,
        )
        tool_metadata = extract_arcade_tool_metadata(tool)
        update_integration_with_arcade_data(user_id, integration_name, tool_metadata)
    except Exception as e:
        print(f"Error fetching tool details for {integration_name}: {e}")

def revoke_arcade_integration(user_id: str, integration_name: str) -> bool:
    """Attempt to revoke Arcade integration (best effort)"""
    try:
        arcade_client.auth.revoke(
            tool_name=integration_name,
            user_id=user_id,
        )
        return True
    except Exception as e:
        print(f"Failed to revoke Arcade integration {integration_name}: {e}")
        return False

# Background Task Functions
def sync_readwise_background(tenant_name: str, user_email: str, api_key: str, long_job_id: str) -> None:
    """Background task for syncing Readwise data"""
    try:
        fetch_from_export_api(tenant_name, api_key)
        print(f"Readwise sync completed for user {user_email}")
        
        # Update job status and integration timestamp
        LongJob.update_status(long_job_id, JOB_STATUSES["COMPLETED"])
        last_updated_utc = get_current_timestamp_ms()
        ConstellaIntegration.update_integration_property(
            user_email, 
            SUPPORTED_INTEGRATIONS["readwise"], 
            "lastUpdated", 
            last_updated_utc
        )
    except Exception as e:
        traceback.print_exc()
        print(f"Error syncing Readwise for user {user_email}: {e}")
        LongJob.update_status(long_job_id, JOB_STATUSES["FAILED"], {"error": str(e)})

def _serialize_integration(integ: Any) -> Dict[str, Any]:
    """Serialize integration object for JSON response"""
    return {
        "apiKey": getattr(integ, "apiKey", None),
        "lastUpdated": getattr(integ, "lastUpdated", None),
        "arcade": getattr(integ, "arcade", None),
    }

@router.post("/get")
async def get_user_integration(request: GetIntegrationRequest) -> Dict[str, Any]:
    """
    Get user integrations. Creates empty integration record if none exists.
    """
    try:
        integration = ConstellaIntegration.get_by_email(request.user_email)
        if integration:
            # Convert Integration objects to dict for JSON serialization
            return {
                "integrations": {
                    name: _serialize_integration(integ)
                    for name, integ in integration.integrations.items()
                }
            }
        
        # Create empty integration object for new user
        integration = ConstellaIntegration(user_email=request.user_email, integrations={})
        integration.save()
        return {"integrations": {}}
        
    except Exception as e:
        print(f"Error getting user integration for {request.user_email}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get user integrations: {str(e)}")

@router.post("/update")
async def update_user_integration(update_data: UpdateIntegrationRequest) -> Dict[str, str]:
    """
    Update a specific property of a user's integration.
    """
    try:
        ConstellaIntegration.update_integration_property(
            user_email=update_data.user_email,
            integration_name=update_data.integration_name,
            property_name=update_data.property_name,
            property_value=update_data.property_value
        )
        return {"message": MESSAGES["INTEGRATION_UPDATED"]}
        
    except Exception as e:
        print(f"Error updating integration {update_data.integration_name} for {update_data.user_email}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update integration: {str(e)}")

@router.post("/arcade/create", response_model=IntegrationResponse)
async def arcade_create_integration(request: CreateArcadeIntegrationRequest) -> IntegrationResponse:
    """
    Create an Arcade integration by initiating authorization for a specific tool.
    """
    try:
        # Initiate Arcade authorization
        auth_response = arcade_client.tools.authorize(
            tool_name=request.integration_name,
            user_id=request.user_id,
        )

        # Store initial auth status
        arcade_data = create_arcade_auth_data(auth_response)
        update_integration_with_arcade_data(request.user_id, request.integration_name, arcade_data)

        # Handle completed authorization immediately
        auth_status = safe_getattr(auth_response, "status")
        if auth_status == ARCADE_AUTH_STATUSES["COMPLETED"]:
            handle_completed_arcade_auth(request.user_id, request.integration_name)

        # Build response
        is_completed = auth_status == ARCADE_AUTH_STATUSES["COMPLETED"]
        response = IntegrationResponse(
            message=MESSAGES["AUTH_COMPLETED"] if is_completed else MESSAGES["AUTH_INITIATED"],
            status=auth_status,
        )
        
        if not is_completed:
            response.authorization_url = safe_getattr(auth_response, "url")

        return response
        
    except Exception as e:
        print(f"Error creating Arcade integration {request.integration_name} for {request.user_id}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create Arcade integration: {str(e)}")

@router.post("/arcade/wait_for_authorization", response_model=IntegrationResponse)
async def arcade_wait_for_authorization(request: WaitForArcadeAuthorizationRequest) -> IntegrationResponse:
    """
    Wait for Arcade authorization completion (blocking operation).
    """
    try:
        # Get fresh authorization response to wait on
        auth_response = arcade_client.tools.authorize(
            tool_name=request.integration_name,
            user_id=request.user_id,
        )
        
        # Wait for completion (blocking call)
        completed = arcade_client.auth.wait_for_completion(auth_response)

        # Handle completed authorization
        handle_completed_arcade_auth(request.user_id, request.integration_name)

        return IntegrationResponse(
            message=MESSAGES["AUTH_COMPLETED"],
            status=safe_getattr(completed, "status", ARCADE_AUTH_STATUSES["COMPLETED"]),
        )
        
    except Exception as e:
        print(f"Error waiting for Arcade authorization {request.integration_name} for {request.user_id}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to wait for authorization: {str(e)}")

@router.post("/arcade/remove", response_model=IntegrationResponse)
async def arcade_remove_integration(request: RemoveArcadeIntegrationRequest) -> IntegrationResponse:
    """
    Remove an Arcade integration. Attempts to revoke authorization and removes from database.
    """
    try:
        # Attempt to revoke in Arcade (best effort)
        revoke_success = revoke_arcade_integration(request.user_id, request.integration_name)
        if not revoke_success:
            print(f"Warning: Could not revoke Arcade integration {request.integration_name} for {request.user_id}")

        # Remove from database
        ConstellaIntegration.remove_integration(
            user_email=request.user_id,
            integration_name=request.integration_name,
        )
        
        return IntegrationResponse(message=MESSAGES["INTEGRATION_REMOVED"])
        
    except Exception as e:
        print(f"Error removing Arcade integration {request.integration_name} for {request.user_id}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to remove integration: {str(e)}")

@router.post("/sync-initial-integration", response_model=SyncResponse)
async def sync_initial_integration(
    request: InitialSyncRequest, 
    background_tasks: BackgroundTasks
) -> SyncResponse:
    """
    Start initial sync for a supported integration.
    """
    try:
        # Validate supported integration
        if request.integration_name not in SUPPORTED_INTEGRATIONS:
            supported = ", ".join(SUPPORTED_INTEGRATIONS.keys())
            raise HTTPException(
                status_code=400, 
                detail=f"Integration '{request.integration_name}' not supported. Supported: {supported}"
            )

        # Create long job and start background sync
        long_job_id = LongJob.insert(
            JOB_STATUSES["STARTED"], 
            {}, 
            JOB_TYPES["INITIAL_SYNC"], 
            request.user_email
        )
        
        if request.integration_name == SUPPORTED_INTEGRATIONS["readwise"]:
            background_tasks.add_task(
                sync_readwise_background,
                request.tenant_name,
                request.user_email,
                request.api_key,
                long_job_id
            )

        return SyncResponse(
            message=MESSAGES["SYNC_STARTED"],
            long_job_id=long_job_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error starting initial sync for {request.integration_name}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to start sync: {str(e)}")

@router.post("/sync-integrations", response_model=SyncResponse)
async def sync_integrations(
    request: SyncIntegrationsRequest,
    background_tasks: BackgroundTasks
) -> SyncResponse:
    """
    Start sync for all user integrations.
    """
    try:
        # Create long job and start background sync
        long_job_id = LongJob.insert(
            JOB_STATUSES["STARTED"], 
            {}, 
            JOB_TYPES["SYNC_INTEGRATIONS"], 
            request.user_email
        )
        
        background_tasks.add_task(
            sync_integrations_for_user,
            request.tenant_name,
            request.user_email,
            long_job_id
        )
        
        return SyncResponse(
            message=MESSAGES["SYNC_STARTED"],
            long_job_id=long_job_id
        )
        
    except Exception as e:
        print(f"Error starting integrations sync for user {request.user_email}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to start integrations sync: {str(e)}")

@router.post("/create-api-key", response_model=ApiKeyResponse)
async def create_api_key(request: CreateApiKeyRequest) -> ApiKeyResponse:
    """
    Create a new API key for the authenticated user.
    """
    try:
        # Create API key
        api_key = ConstellaSubscription.add_api_key(auth_user_id=request.auth_user_id)
        if not api_key:
            raise HTTPException(
                status_code=500, 
                detail=MESSAGES["API_KEY_CREATION_FAILED"]
            )
            
        return ApiKeyResponse(api_key=api_key)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating API key for user {request.auth_user_id}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create API key: {str(e)}")

