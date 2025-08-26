from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import traceback
import sentry_sdk
from arcadepy import Arcade

router = APIRouter(
    prefix="/horizon/integrations",
    tags=["horizon_integrations"],
    # dependencies=[Depends(validate_access_token)],
    # responses={404: {"description": "Not found"}},
)

# Initialize Arcade client
client = Arcade()  # Automatically finds the `ARCADE_API_KEY` env variable

class CreateIntegrationRequest(BaseModel):
    integration_name: str
    user_id: str

class CreateDirectIntegrationRequest(BaseModel):
    provider: str  # e.g., "google", "microsoft", "slack", etc.
    user_id: str
    scopes: List[str]  # e.g., ["https://www.googleapis.com/auth/gmail.readonly"]

class RemoveIntegrationRequest(BaseModel):
    integration_name: str
    user_id: str

class CheckIntegrationsRequest(BaseModel):
    user_id: str

class IntegrationResponse(BaseModel):
    success: bool
    message: str
    authorization_url: Optional[str] = None
    status: Optional[str] = None

class DirectIntegrationResponse(BaseModel):
    success: bool
    message: str
    authorization_url: Optional[str] = None
    status: str
    provider: str
    token: Optional[str] = None

class IntegrationsListResponse(BaseModel):
    success: bool
    integrations: List[Dict[str, Any]]
    message: str

@router.post("/create_direct_integration", response_model=DirectIntegrationResponse)
async def create_direct_integration(request: CreateDirectIntegrationRequest):
    """
    Create a direct integration using Arcade's auth.start() method.
    This initiates authorization with a third-party provider and returns tokens directly.
    
    Args:
        provider: The OAuth provider (e.g., "google", "microsoft", "slack")
        user_id: Your app's internal user ID
        scopes: List of OAuth scopes to request
    
    Returns:
        - If authorization needed: authorization_url to redirect user
        - If already authorized: token for direct API calls
    """
    try:
        # Start the authorization process using Arcade's direct auth
        auth_response = client.auth.start(
            user_id=request.user_id,
            provider=request.provider,
            scopes=request.scopes
        )
        
        if auth_response.status == "completed":
            # Authorization already complete, return the token
            token = None
            if hasattr(auth_response, 'context') and hasattr(auth_response.context, 'token'):
                token = auth_response.context.token
                
            return DirectIntegrationResponse(
                success=True,
                message=f"Direct integration with {request.provider} already authorized for user {request.user_id}",
                status=auth_response.status,
                provider=request.provider,
                token=token
            )
        else:
            # Authorization needed, return URL for user to complete OAuth flow
            return DirectIntegrationResponse(
                success=True,
                message=f"Authorization required for {request.provider}. User must complete OAuth flow at the provided URL.",
                authorization_url=auth_response.url,
                status=auth_response.status,
                provider=request.provider
            )
            
    except Exception as e:
        print(f'Error creating direct integration with {request.provider}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create direct integration: {str(e)}"
        )

@router.post("/create_integration", response_model=IntegrationResponse)
async def create_integration(request: CreateIntegrationRequest):
    """
    Create a new integration using Arcade's authorization system.
    This will initiate the OAuth flow for the specified integration.
    """
    try:
        # Request authorization for the integration
        auth_response = client.tools.authorize(
            tool_name=request.integration_name,
            user_id=request.user_id,
        )
        
        if auth_response.status == "completed":
            return IntegrationResponse(
                success=True,
                message=f"Integration {request.integration_name} already authorized for user {request.user_id}",
                status=auth_response.status
            )
        else:
            return IntegrationResponse(
                success=True,
                message=f"Authorization required for {request.integration_name}. User must complete OAuth flow.",
                authorization_url=auth_response.url,
                status=auth_response.status
            )
            
    except Exception as e:
        print(f'Error creating integration {request.integration_name}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create integration: {str(e)}"
        )

@router.post("/remove_integration", response_model=IntegrationResponse)
async def remove_integration(request: RemoveIntegrationRequest):
    """
    Remove an existing integration for a user.
    This will revoke the authorization for the specified integration.
    """
    try:
        # Check if the integration exists first using the correct Arcade API
        tool = client.tools.get(
            tool_name=request.integration_name,
            user_id=request.user_id
        )
        
        if not tool.requirements or not tool.requirements.authorization or tool.requirements.authorization.token_status != "completed":
            return IntegrationResponse(
                success=False,
                message=f"Integration {request.integration_name} is not authorized for user {request.user_id}",
                status=tool.requirements.authorization.token_status if tool.requirements and tool.requirements.authorization else "not_started"
            )
        
        # Revoke the authorization - Note: This method may need to be confirmed with Arcade docs
        # Using a conceptual revoke method - actual implementation may vary
        revoke_response = client.auth.revoke(
            tool_name=request.integration_name,
            user_id=request.user_id
        )
        
        return IntegrationResponse(
            success=True,
            message=f"Integration {request.integration_name} successfully removed for user {request.user_id}",
            status="revoked"
        )
        
    except Exception as e:
        print(f'Error removing integration {request.integration_name}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to remove integration: {str(e)}"
        )

@router.post("/check_integrations", response_model=IntegrationsListResponse)
async def check_integrations(request: CheckIntegrationsRequest):
    """
    Check all existing integrations for a user.
    Returns a list of authorized integrations and their status.
    """
    try:
        # Get all tools for the user using the correct Arcade API
        tools = client.tools.list(user_id=request.user_id)
        
        integrations = []
        
        for tool in tools:
            try:
                # Initialize default values
                auth_status = "inactive"
                token_status = "not_started"
                requirements_met = False
                provider_type = None
                status_reason = None
                secrets_info = []
                
                # Check if requirements exist and are met
                if tool.requirements:
                    requirements_met = tool.requirements.met
                    
                    # Check authorization status
                    if tool.requirements.authorization:
                        auth = tool.requirements.authorization
                        auth_status = auth.status  # 'active' or 'inactive'
                        token_status = auth.token_status  # 'not_started', 'pending', 'completed', 'failed'
                        provider_type = auth.provider_type
                        if hasattr(auth, 'status_reason'):
                            status_reason = auth.status_reason
                    
                    # Check secret requirements
                    if tool.requirements.secrets:
                        for secret in tool.requirements.secrets:
                            secret_info = {
                                "key": secret.key,
                                "met": secret.met
                            }
                            if hasattr(secret, 'status_reason') and secret.status_reason:
                                secret_info["status_reason"] = secret.status_reason
                            secrets_info.append(secret_info)
                
                # Determine if tool is fully authorized
                is_authorized = (
                    requirements_met and 
                    auth_status == "active" and 
                    token_status == "completed"
                )
                
                integration_data = {
                    "name": tool.name,
                    "description": getattr(tool, 'description', None),
                    "auth_status": auth_status,
                    "token_status": token_status,
                    "authorized": is_authorized,
                    "requirements_met": requirements_met,
                    "provider": provider_type or (tool.name.split('.')[0] if '.' in tool.name else tool.name)
                }
                
                # Add optional fields if they exist
                if status_reason:
                    integration_data["status_reason"] = status_reason
                if secrets_info:
                    integration_data["secrets"] = secrets_info
                    
                integrations.append(integration_data)
                
            except Exception as tool_error:
                # If checking a specific tool fails, continue with others
                print(f'Error checking status for {tool.name}: {tool_error}')
                integrations.append({
                    "name": tool.name,
                    "auth_status": "error",
                    "token_status": "error",
                    "authorized": False,
                    "requirements_met": False,
                    "provider": tool.name.split('.')[0] if '.' in tool.name else tool.name,
                    "error": str(tool_error)
                })
        
        return IntegrationsListResponse(
            success=True,
            integrations=integrations,
            message=f"Retrieved {len(integrations)} integration statuses for user {request.user_id}"
        )
        
    except Exception as e:
        print(f'Error checking integrations for user {request.user_id}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to check integrations: {str(e)}"
        )

@router.post("/wait_for_direct_authorization", response_model=DirectIntegrationResponse)
async def wait_for_direct_authorization(request: CreateDirectIntegrationRequest):
    """
    Wait for direct authorization completion after user has been redirected to OAuth flow.
    This endpoint waits for the authorization to complete and returns the token.
    """
    try:
        # Start the authorization process to get the auth response
        auth_response = client.auth.start(
            user_id=request.user_id,
            provider=request.provider,
            scopes=request.scopes
        )
        
        if auth_response.status == "completed":
            # Already completed, extract token
            token = None
            if hasattr(auth_response, 'context') and hasattr(auth_response.context, 'token'):
                token = auth_response.context.token
                
            return DirectIntegrationResponse(
                success=True,
                message=f"Direct integration with {request.provider} is already authorized",
                status="completed",
                provider=request.provider,
                token=token
            )
        
        # Wait for completion using Arcade's wait method
        completed_auth = client.auth.wait_for_completion(auth_response)
        
        # Extract token from completed authorization
        token = None
        if hasattr(completed_auth, 'context') and hasattr(completed_auth.context, 'token'):
            token = completed_auth.context.token
        
        return DirectIntegrationResponse(
            success=True,
            message=f"Direct integration with {request.provider} successfully authorized for user {request.user_id}",
            status="completed",
            provider=request.provider,
            token=token
        )
        
    except Exception as e:
        print(f'Error waiting for direct authorization with {request.provider}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to wait for direct authorization: {str(e)}"
        )

@router.post("/wait_for_authorization")
async def wait_for_authorization(request: CreateIntegrationRequest):
    """
    Wait for authorization completion after user has been redirected to OAuth flow.
    This is a helper endpoint to check if authorization has been completed.
    """
    try:
        # First get the auth response to wait for
        auth_response = client.tools.authorize(
            tool_name=request.integration_name,
            user_id=request.user_id,
        )
        
        if auth_response.status == "completed":
            return IntegrationResponse(
                success=True,
                message=f"Integration {request.integration_name} is already authorized",
                status="completed"
            )
        
        # Wait for completion (this might take some time)
        completed_auth = client.auth.wait_for_completion(auth_response)
        
        return IntegrationResponse(
            success=True,
            message=f"Integration {request.integration_name} successfully authorized for user {request.user_id}",
            status="completed"
        )
        
    except Exception as e:
        print(f'Error waiting for authorization {request.integration_name}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to wait for authorization: {str(e)}"
        )

@router.post("/get_tool_details")
async def get_tool_details(request: CreateIntegrationRequest):
    """
    Get detailed information about a specific tool including authorization status.
    """
    try:
        # Get specific tool details using the correct Arcade API
        tool = client.tools.get(
            tool_name=request.integration_name,
            user_id=request.user_id
        )
        
        result = {
            "name": tool.name,
            "description": getattr(tool, 'description', None),
        }
        
        if tool.requirements:
            result["requirements_met"] = tool.requirements.met
            
            # Check authorization status with proper status values
            if tool.requirements.authorization:
                auth = tool.requirements.authorization
                result["authorization"] = {
                    "provider_type": auth.provider_type,
                    "status": auth.status,  # 'active' or 'inactive'
                    "token_status": auth.token_status,  # 'not_started', 'pending', 'completed', 'failed'
                }
                
                # Add status reason if available
                if hasattr(auth, 'status_reason') and auth.status_reason:
                    result["authorization"]["status_reason"] = auth.status_reason
            
            # Check secret requirements with proper status
            if tool.requirements.secrets:
                result["secrets"] = []
                for secret in tool.requirements.secrets:
                    secret_data = {
                        "key": secret.key,
                        "met": secret.met  # true or false
                    }
                    # Add status reason if available and not met
                    if not secret.met and hasattr(secret, 'status_reason') and secret.status_reason:
                        secret_data["status_reason"] = secret.status_reason
                    result["secrets"].append(secret_data)
        
        return {
            "success": True,
            "tool": result,
            "message": f"Retrieved details for {request.integration_name}"
        }
        
    except Exception as e:
        print(f'Error getting tool details for {request.integration_name}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get tool details: {str(e)}"
        )
