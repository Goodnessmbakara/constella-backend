from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import traceback
import sentry_sdk
import requests
import os
from arcadepy import Arcade

router = APIRouter(
    prefix="/horizon/integrations",
    tags=["horizon_integrations"],
    # dependencies=[Depends(validate_access_token)],
    # responses={404: {"description": "Not found"}},
)

# Initialize Arcade client
client = Arcade()  # Automatically finds the `ARCADE_API_KEY` env variable

# Integration metadata for v1 endpoint response formatting
INTEGRATION_METADATA = {
    "google": {
        "name": "Google",
        "logo_url": "https://developers.google.com/identity/images/g-logo.png"
    },
    "microsoft": {
        "name": "Microsoft",
        "logo_url": "https://logoeps.com/wp-content/uploads/2013/03/microsoft-vector-logo.png"
    },
    "slack": {
        "name": "Slack", 
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/11/Slack-Logo.png"
    },
    "notion": {
        "name": "Notion",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/4/45/Notion_app_logo.png"
    },
    "pinterest": {
        "name": "Pinterest",
        "logo_url": "https://logoeps.com/wp-content/uploads/2013/03/pinterest-vector-logo.png"
    },
    "asana": {
        "name": "Asana",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/02/Asana-Logo.png"
    },
    "attachfiletotask": {
        "name": "Asana",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/02/Asana-Logo.png"
    },
    "createtag": {
        "name": "Asana",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/02/Asana-Logo.png"
    },
    "createtask": {
        "name": "Asana",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/02/Asana-Logo.png"
    },
    "confluence": {
        "name": "Confluence",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/08/Confluence-Logo.png"
    },
    "createpage": {
        "name": "Confluence",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/08/Confluence-Logo.png"
    },
    "dropbox": {
        "name": "Dropbox",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/03/Dropbox-Logo.png"
    },
    "downloadfile": {
        "name": "Dropbox",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/03/Dropbox-Logo.png"
    },
    "github": {
        "name": "GitHub",
        "logo_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"
    },
    "countstargazers": {
        "name": "GitHub",
        "logo_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"
    },
    "createissue": {
        "name": "GitHub",
        "logo_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"
    },
    "gmail": {
        "name": "Gmail",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/11/Gmail-Logo.png"
    },
    "getthread": {
        "name": "Gmail",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/11/Gmail-Logo.png"
    },
    "listemails": {
        "name": "Gmail",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/11/Gmail-Logo.png"
    },
    "sendemail": {
        "name": "Gmail",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/11/Gmail-Logo.png"
    },
    "jira": {
        "name": "Jira",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/08/Jira-Logo.png"
    },
    "addcommenttoissue": {
        "name": "Jira",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/08/Jira-Logo.png"
    },
    "linkedin": {
        "name": "LinkedIn",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/05/LinkedIn-Logo.png"
    },
    "getcompanydatabykeywords": {
        "name": "LinkedIn",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/05/LinkedIn-Logo.png"
    },
    "trello": {
        "name": "Trello",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/03/Trello-Logo.png"
    },
    "zoom": {
        "name": "Zoom",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/12/Zoom-Logo.png"
    },
    "twitter": {
        "name": "Twitter",
        "logo_url": "https://logos-world.net/wp-content/uploads/2023/08/X-Logo.png"
    },
    "facebook": {
        "name": "Facebook",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/04/Facebook-Logo.png"
    },
    "instagram": {
        "name": "Instagram",
        "logo_url": "https://logos-world.net/wp-content/uploads/2017/02/Instagram-Logo.png"
    },
    "shopify": {
        "name": "Shopify",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/11/Shopify-Logo.png"
    },
    "salesforce": {
        "name": "Salesforce",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/11/Salesforce-Logo.png"
    },
    "hubspot": {
        "name": "HubSpot",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/11/HubSpot-Logo.png"
    },
    "mailchimp": {
        "name": "Mailchimp",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/02/Mailchimp-Logo.png"
    },
    "discord": {
        "name": "Discord",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/12/Discord-Logo.png"
    },
    "spotify": {
        "name": "Spotify",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/06/Spotify-Logo.png"
    },
    "youtube": {
        "name": "YouTube",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/04/YouTube-Logo.png"
    },
    "whatsapp": {
        "name": "WhatsApp",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/05/WhatsApp-Logo.png"
    },
    "telegram": {
        "name": "Telegram",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/06/Telegram-Logo.png"
    },
    "airtable": {
        "name": "Airtable",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/03/Airtable-Logo.png"
    },
    "calendly": {
        "name": "Calendly",
        "logo_url": "https://logos-world.net/wp-content/uploads/2021/02/Calendly-Logo.png"
    },
    "figma": {
        "name": "Figma",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/12/Figma-Logo.png"
    },
    "canva": {
        "name": "Canva",
        "logo_url": "https://logos-world.net/wp-content/uploads/2020/11/Canva-Logo.png"
    }
}


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
    This will revoke the authorization for the specified integration.
    """
    try:
        # Get all tools for the user to find the specific integration
        tools = client.tools.list(user_id=request.user_id)
        
        # Find the specific integration tool
        target_tool = None
        for tool in tools:
            if tool.name.lower() == request.integration_name.lower():
                target_tool = tool
                break
        
        if not target_tool:
            return IntegrationResponse(
                success=False,
                message=f"Integration {request.integration_name} not found for user {request.user_id}",
                status="not_found"
            )
        
        # Check if the integration is actually authorized
        # According to Arcade docs: integration is connected when BOTH conditions are met:
        # 1. auth.status == "active" (auth mechanism is available)
        # 2. auth.token_status == "completed" (user completed OAuth flow)
        if (not target_tool.requirements or 
            not target_tool.requirements.authorization or 
            target_tool.requirements.authorization.token_status != "completed" or
            target_tool.requirements.authorization.status != "active"):
            
            auth_status = "inactive"
            token_status = "not_started"
            if target_tool.requirements and target_tool.requirements.authorization:
                auth_status = target_tool.requirements.authorization.status
                token_status = target_tool.requirements.authorization.token_status
            
            return IntegrationResponse(
                success=False,
                message=f"Integration {request.integration_name} is not fully authorized for user {request.user_id}. Auth status: {auth_status}, Token status: {token_status}",
                status=token_status
            )

        # Get Arcade API key and engine URL
        arcade_api_key = os.getenv("ARCADE_API_KEY")
        engine_url = "https://api.arcade.dev"
        
        if not arcade_api_key:
            return IntegrationResponse(
                success=False,
                message="Arcade API key not configured",
                status="error"
            )

        # Step 1: List user connections to find the connection ID
        list_url = f"{engine_url}/v1/admin/user_connections"
        list_params = {
            "user.id": request.user_id
        }
        list_headers = {
            "Authorization": f"Bearer {arcade_api_key}",
            "Content-Type": "application/json"
        }

        list_response = requests.get(list_url, params=list_params, headers=list_headers)
        
        if list_response.status_code != 200:
            return IntegrationResponse(
                success=False,
                message=f"Failed to list user connections: {list_response.text}",
                status="error"
            )

        connections = list_response.json().get("data", [])
        
        # Step 2: Find the connection for this integration
        connection_to_remove = None
        for connection in connections:
            # Match by provider type or connection metadata
            provider_id = connection.get("provider", {}).get("id", "")
            # Check if this connection is related to the integration we want to remove
            if (request.integration_name.lower() in provider_id.lower() or 
                provider_id.lower() in request.integration_name.lower() or
                request.integration_name == "gmail" and "google" in provider_id.lower()):
                connection_to_remove = connection
                break
        
        if not connection_to_remove:
            return IntegrationResponse(
                success=False,
                message=f"No connection found for integration {request.integration_name}",
                status="not_found"
            )

        # Step 3: Delete the connection
        connection_id = connection_to_remove.get("id")
        delete_url = f"{engine_url}/v1/admin/user_connections/{connection_id}"
        delete_headers = {
            "Authorization": f"Bearer {arcade_api_key}"
        }

        delete_response = requests.delete(delete_url, headers=delete_headers)
        
        if delete_response.status_code == 204:
            return IntegrationResponse(
                success=True,
                message=f"Integration {request.integration_name} successfully removed for user {request.user_id}",
                status="revoked"
            )
        else:
            return IntegrationResponse(
                success=False,
                message=f"Failed to remove connection: {delete_response.text}",
                status="error"
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


# V1 Integration Response Models
class V1IntegrationItem(BaseModel):
    name: str
    display_name: str
    logo: str
    status: str
    provider: str


class V1CheckIntegrationsResponse(BaseModel):
    success: bool
    integrations: List[V1IntegrationItem]


@router.post("/v1/check_integrations", response_model=V1CheckIntegrationsResponse)
async def v1_check_integrations(request: CheckIntegrationsRequest):
    """
    V1 endpoint to check all integrations with standardized response format.
    Returns integrations with name, display_name, logo, status, and provider.
    """
    try:
        # Get all tools for the user
        tools = client.tools.list(user_id=request.user_id)

        integrations = []
        provider_status = {}  # Track the best status for each provider

        # Process each tool and map to our integration metadata
        for tool in tools:
            if tool.requirements and tool.requirements.authorization:
                auth = tool.requirements.authorization

                # Determine integration status
                if auth.token_status == "completed" and auth.status == "active":
                    status = "connected"
                elif auth.token_status == "pending":
                    status = "pending"
                elif auth.token_status == "failed":
                    status = "failed"
                else:
                    status = "not_connected"

                # Get provider from tool authorization info (primary source)
                provider_id = None
                if auth.provider_type:
                    provider_id = auth.provider_type.lower()
                
                # Map common provider types to user-friendly names
                provider_mapping = {
                    "oauth2": "oauth2",  # Keep as is, will map to specific services below
                    "google": "google",
                    "microsoft": "microsoft", 
                    "slack": "slack",
                    "notion": "notion",
                    "pinterest": "pinterest"
                }
                
                # If we have oauth2, try to determine specific provider from tool name
                if provider_id == "oauth2":
                    tool_name_lower = tool.name.lower()
                    # Smart provider mapping based on tool functionality
                    if any(keyword in tool_name_lower for keyword in ["gmail", "email", "thread", "draft"]):
                        provider_id = "gmail"
                    elif any(keyword in tool_name_lower for keyword in ["google", "spreadsheet", "document", "presentation"]):
                        provider_id = "google"
                    elif any(keyword in tool_name_lower for keyword in ["outlook", "microsoft", "onedrive"]):
                        provider_id = "microsoft"
                    elif any(keyword in tool_name_lower for keyword in ["slack"]):
                        provider_id = "slack"
                    elif any(keyword in tool_name_lower for keyword in ["notion"]):
                        provider_id = "notion"
                    elif any(keyword in tool_name_lower for keyword in ["pinterest"]):
                        provider_id = "pinterest"
                    elif any(keyword in tool_name_lower for keyword in ["asana", "task", "project", "tag"]):
                        provider_id = "asana"
                    elif any(keyword in tool_name_lower for keyword in ["confluence", "page", "space"]):
                        provider_id = "confluence"
                    elif any(keyword in tool_name_lower for keyword in ["dropbox", "file"]):
                        provider_id = "dropbox"
                    elif any(keyword in tool_name_lower for keyword in ["github", "repository", "issue", "pull"]):
                        provider_id = "github"
                    elif any(keyword in tool_name_lower for keyword in ["jira", "ticket"]):
                        provider_id = "jira"
                    elif any(keyword in tool_name_lower for keyword in ["linkedin", "company", "contact"]):
                        provider_id = "linkedin"
                    else:
                        # For unrecognized oauth2 tools, group by first word of tool name
                        provider_id = tool_name_lower.split('.')[0] if '.' in tool.name else tool_name_lower.split()[0] if ' ' in tool_name_lower else "other"
                
                # Fallback if no provider found
                if not provider_id:
                    provider_id = tool.name.lower().split('.')[0] if '.' in tool.name else "unknown"

                # Track the best status for each provider (connected > pending > failed > not_connected)
                status_priority = {"connected": 4, "pending": 3, "failed": 2, "not_connected": 1}
                current_priority = status_priority.get(status, 0)
                
                if provider_id not in provider_status or current_priority > provider_status[provider_id]["priority"]:
                    provider_status[provider_id] = {
                        "status": status,
                        "priority": current_priority
                    }

        # Create consolidated integration items from provider status
        for provider_id, status_info in provider_status.items():
            # Get metadata from our integration metadata
            metadata = INTEGRATION_METADATA.get(provider_id, {})

            # Create integration item with standardized format
            integration_item = V1IntegrationItem(
                name=provider_id,
                display_name=metadata.get("name", provider_id.title()),
                logo=metadata.get(
                    "logo_url", "https://via.placeholder.com/64x64?text=?"),
                status=status_info["status"],
                provider=provider_id
            )

            integrations.append(integration_item)

        return V1CheckIntegrationsResponse(
            success=True,
            integrations=integrations
        )

    except Exception as e:
        print(f'Error in v1 check integrations: {e}')
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check integrations: {str(e)}"
        )
