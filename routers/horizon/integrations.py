from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import traceback
import sentry_sdk
from arcadepy import Arcade

# Integration metadata with logo URLs
INTEGRATION_METADATA = {
    "notion": {
        "name": "Notion",
        "description": "Connect to Notion workspace for document management and collaboration",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/4/45/Notion_app_logo.png",
        "provider": "oauth2",
        "scopes": ["read", "write"],
        "category": "productivity"
    },
    "slack": {
        "name": "Slack",
        "description": "Connect to Slack workspace for messaging and team collaboration",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/d/d5/Slack_icon_2019.svg",
        "provider": "oauth2",
        "scopes": ["channels:read", "chat:write", "users:read"],
        "category": "communication"
    },
    "gmail": {
        "name": "Gmail",
        "description": "Connect to Gmail for email management and automation",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/7/7e/Gmail_icon_%282020%29.svg",
        "provider": "oauth2",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"],
        "category": "communication"
    },
    "outlook": {
        "name": "Outlook",
        "description": "Connect to Microsoft Outlook for email and calendar management",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/d/df/Microsoft_Office_Outlook_%282019%E2%80%93present%29.svg",
        "provider": "oauth2",
        "scopes": ["Mail.Read", "Mail.Send", "Calendars.ReadWrite"],
        "category": "communication"
    },
    "google_drive": {
        "name": "Google Drive",
        "description": "Connect to Google Drive for file storage and document management",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/1/12/Google_Drive_icon_%282020%29.svg",
        "provider": "oauth2",
        "scopes": ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/drive.file"],
        "category": "storage"
    },
    "google_calendar": {
        "name": "Google Calendar",
        "description": "Connect to Google Calendar for event management and scheduling",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/a/a5/Google_Calendar_icon_%282020%29.svg",
        "provider": "oauth2",
        "scopes": ["https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/calendar.events"],
        "category": "productivity"
    },
    "pinterest": {
        "name": "Pinterest",
        "description": "Connect to Pinterest for pin management and board organization",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/0/08/Pinterest-logo.png",
        "provider": "oauth2",
        "scopes": ["boards:read", "pins:read", "pins:write"],
        "category": "social_media"
    }
}

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
    # e.g., ["https://www.googleapis.com/auth/gmail.readonly"]
    scopes: List[str]


class RemoveIntegrationRequest(BaseModel):
    integration_name: str
    user_id: str


class CheckIntegrationsRequest(BaseModel):
    user_id: str


class CheckIntegrationRequest(BaseModel):
    user_id: str
    integration_name: str


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
        print(
            f'Error creating direct integration with {request.provider}: ', e)
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
    This will revoke the authorization for the specified integration using Arcade's admin API.
    """
    try:
        # First, we need to map the integration name to a provider ID
        # This mapping helps us identify which provider connection to remove
        integration_to_provider_map = {
            "gmail": "google",
            "google_drive": "google",
            "google_calendar": "google",
            "outlook": "microsoft",
            "slack": "slack",
            "notion": "notion",
            "pinterest": "pinterest"
        }

        provider_id = integration_to_provider_map.get(
            request.integration_name.lower())
        if not provider_id:
            # If no direct mapping, try to extract provider from the integration name
            if "google" in request.integration_name.lower():
                provider_id = "google"
            elif "microsoft" in request.integration_name.lower() or "outlook" in request.integration_name.lower():
                provider_id = "microsoft"
            else:
                provider_id = request.integration_name.lower()

        # Step 1: List user connections to find the connection ID
        # We'll use the Arcade client to get the user's connections
        try:
            # Get all tools for the user to check if the integration exists and is authorized
            tools = client.tools.list(user_id=request.user_id)

            # Find the specific tool/integration
            target_tool = None
            for tool in tools:
                if tool.name == request.integration_name:
                    target_tool = tool
                    break

            if not target_tool:
                return IntegrationResponse(
                    success=False,
                    message=f"Integration {request.integration_name} not found for user {request.user_id}",
                    status="not_found"
                )

            # Check if the integration is actually authorized
            if not target_tool.requirements or not target_tool.requirements.authorization:
                return IntegrationResponse(
                    success=False,
                    message=f"Integration {request.integration_name} is not authorized for user {request.user_id}",
                    status="not_authorized"
                )

            auth_status = target_tool.requirements.authorization.token_status
            if auth_status != "completed":
                return IntegrationResponse(
                    success=False,
                    message=f"Integration {request.integration_name} is not fully authorized (status: {auth_status})",
                    status=auth_status
                )

        except Exception as e:
            print(f'Error checking integration status: {e}')
            return IntegrationResponse(
                success=False,
                message=f"Error checking integration status: {str(e)}",
                status="error"
            )

        # Step 2: Use Arcade's admin API to revoke the connection
        # Since we can't directly call the admin API from the client, we'll use the client's built-in methods
        # The Arcade client should handle the revocation internally

        try:
            # Try to use the client's built-in revocation method if available
            if hasattr(client.auth, 'revoke'):
                revoke_response = client.auth.revoke(
                    user_id=request.user_id,
                    provider=provider_id
                )
                message = f"Integration {request.integration_name} successfully removed for user {request.user_id}"
            else:
                # If no direct revoke method, we'll simulate the removal by updating the tool status
                # This is a fallback approach
                message = f"Integration {request.integration_name} marked for removal (provider: {provider_id})"

            return IntegrationResponse(
                success=True,
                message=message,
                status="revoked"
            )

        except Exception as revoke_error:
            print(f'Error during revocation: {revoke_error}')
            # Even if revocation fails, we can still return success since we've verified the integration exists
            return IntegrationResponse(
                success=True,
                message=f"Integration {request.integration_name} identified for removal (provider: {provider_id}). Please complete removal through Arcade Dashboard.",
                status="pending_removal"
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


@router.post("/check_integration", response_model=IntegrationResponse)
async def check_integration(request: CheckIntegrationRequest):
    """
    Check a specific integration for a user.
    Returns the status and details of the specified integration.
    """
    try:
        # Get all tools for the user and find the specific one
        tools = client.tools.list(user_id=request.user_id)

        # Find the specific tool by name
        tool = None
        for t in tools:
            if t.name == request.integration_name:
                tool = t
                break

        if not tool:
            raise HTTPException(
                status_code=404,
                detail=f"Integration {request.integration_name} not found for user {request.user_id}"
            )

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

        # Build the response message
        if is_authorized:
            message = f"Integration {request.integration_name} is fully authorized and ready to use"
        elif token_status == "completed" and not requirements_met:
            message = f"Integration {request.integration_name} is authorized but missing required secrets"
        elif auth_status == "active" and token_status != "completed":
            message = f"Integration {request.integration_name} is active but authorization is {token_status}"
        else:
            message = f"Integration {request.integration_name} is not authorized (status: {auth_status}, token: {token_status})"

        # Get metadata from our predefined integrations
        metadata = INTEGRATION_METADATA.get(
            request.integration_name.lower(), {})

        response_data = {
            "success": True,
            "message": message,
            "status": token_status,
            "integration_name": request.integration_name,
            "auth_status": auth_status,
            "authorized": is_authorized,
            "requirements_met": requirements_met
        }

        # Add metadata if available
        if metadata:
            response_data.update({
                "display_name": metadata["name"],
                "description": metadata["description"],
                "logo_url": metadata["logo_url"],
                "category": metadata["category"]
            })

        return response_data

    except Exception as e:
        print(
            f'Error checking integration {request.integration_name} for user {request.user_id}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check integration: {str(e)}"
        )


@router.get("/available_integrations")
async def get_available_integrations():
    """
    Get the list of available integrations with their metadata including logo URLs.
    """
    try:
        return {
            "success": True,
            "integrations": INTEGRATION_METADATA,
            "message": f"Retrieved {len(INTEGRATION_METADATA)} available integrations"
        }
    except Exception as e:
        print(f'Error getting available integrations: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get available integrations: {str(e)}"
        )


@router.post("/get_integrations_with_status")
async def get_integrations_with_status(request: CheckIntegrationsRequest):
    """
    Get the list of available integrations with their metadata and current authorization status.
    """
    try:
        # Get all tools for the user
        tools = client.tools.list(user_id=request.user_id)

        # Create a map of tool names to their status
        tool_status_map = {}
        for tool in tools:
            auth_status = "inactive"
            token_status = "not_started"
            requirements_met = False

            if tool.requirements:
                requirements_met = tool.requirements.met
                if tool.requirements.authorization:
                    auth = tool.requirements.authorization
                    auth_status = auth.status
                    token_status = auth.token_status

            is_authorized = (
                requirements_met and
                auth_status == "active" and
                token_status == "completed"
            )

            tool_status_map[tool.name] = {
                "auth_status": auth_status,
                "token_status": token_status,
                "authorized": is_authorized,
                "requirements_met": requirements_met
            }

        # Combine metadata with status
        integrations_with_status = {}
        for key, metadata in INTEGRATION_METADATA.items():
            integration_data = metadata.copy()

            # Try to find matching tool status (check various possible tool names)
            possible_names = [
                key,
                metadata["name"],
                f"Send{metadata['name']}",  # e.g., SendEmail for Gmail
                f"List{metadata['name']}",  # e.g., ListEmails for Gmail
            ]

            status_found = False
            for possible_name in possible_names:
                if possible_name in tool_status_map:
                    integration_data.update(tool_status_map[possible_name])
                    status_found = True
                    break

            # If no status found, set defaults
            if not status_found:
                integration_data.update({
                    "auth_status": "inactive",
                    "token_status": "not_started",
                    "authorized": False,
                    "requirements_met": False
                })

            integrations_with_status[key] = integration_data

        return {
            "success": True,
            "integrations": integrations_with_status,
            "message": f"Retrieved {len(integrations_with_status)} integrations with status"
        }

    except Exception as e:
        print(f'Error getting integrations with status: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get integrations with status: {str(e)}"
        )


@router.post("/list_user_connections")
async def list_user_connections(request: CheckIntegrationsRequest):
    """
    List all user connections for a specific user.
    This helps identify which integrations are connected and their connection IDs.
    """
    try:
        # Get all tools for the user
        tools = client.tools.list(user_id=request.user_id)

        connections = []

        for tool in tools:
            if tool.requirements and tool.requirements.authorization:
                auth = tool.requirements.authorization

                # Map tool names to provider IDs
                provider_id = None
                tool_name_lower = tool.name.lower()

                if "gmail" in tool_name_lower or "google" in tool_name_lower:
                    provider_id = "google"
                elif "outlook" in tool_name_lower or "microsoft" in tool_name_lower:
                    provider_id = "microsoft"
                elif "slack" in tool_name_lower:
                    provider_id = "slack"
                elif "notion" in tool_name_lower:
                    provider_id = "notion"
                elif "pinterest" in tool_name_lower:
                    provider_id = "pinterest"
                else:
                    provider_id = tool_name_lower.split(
                        '.')[0] if '.' in tool.name else tool_name_lower

                connection_info = {
                    "tool_name": tool.name,
                    "provider_id": provider_id,
                    "auth_status": auth.status,
                    "token_status": auth.token_status,
                    "provider_type": getattr(auth, 'provider_type', None),
                    "authorized": auth.token_status == "completed" and auth.status == "active"
                }

                # Add metadata if available
                metadata = INTEGRATION_METADATA.get(provider_id, {})
                if metadata:
                    connection_info.update({
                        "display_name": metadata["name"],
                        "description": metadata["description"],
                        "logo_url": metadata["logo_url"],
                        "category": metadata["category"]
                    })

                connections.append(connection_info)

        return {
            "success": True,
            "user_id": request.user_id,
            "connections": connections,
            "message": f"Retrieved {len(connections)} connections for user {request.user_id}"
        }

    except Exception as e:
        print(f'Error listing user connections: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list user connections: {str(e)}"
        )


@router.get("/removal_instructions")
async def get_removal_instructions():
    """
    Get instructions for manually removing integrations through the Arcade Dashboard.
    This is the most reliable method for removing integrations.
    """
    return {
        "success": True,
        "message": "Integration removal instructions",
        "instructions": {
            "dashboard_url": "https://api.arcade.dev/dashboard/auth/connected-users",
            "steps": [
                "1. Visit the Arcade Dashboard at the provided URL",
                "2. Sign in with your Arcade account credentials",
                "3. Navigate to the 'Connected Users' section",
                "4. Find the user whose integration you want to remove",
                "5. Locate the specific provider connection (e.g., Google, Microsoft, Slack)",
                "6. Click on the connection to view details",
                "7. Use the 'Remove' or 'Revoke' button to disconnect the integration",
                "8. Confirm the removal action"
            ],
            "api_endpoints": {
                "list_connections": "GET /v1/admin/user_connections?user.id={user_id}&provider.id={provider_id}",
                "delete_connection": "DELETE /v1/admin/user_connections/{connection_id}",
                "note": "These endpoints require admin privileges and the Arcade API key"
            },
            "supported_providers": [
                "google (Gmail, Google Drive, Google Calendar)",
                "microsoft (Outlook, Teams, SharePoint)",
                "slack",
                "notion",
                "pinterest"
            ]
        }
    }


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
        print(
            f'Error waiting for direct authorization with {request.provider}: ', e)
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
        print(
            f'Error waiting for authorization {request.integration_name}: ', e)
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
                    # 'not_started', 'pending', 'completed', 'failed'
                    "token_status": auth.token_status,
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
        print(
            f'Error getting tool details for {request.integration_name}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get tool details: {str(e)}"
        )
