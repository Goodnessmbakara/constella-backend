from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import traceback
import sentry_sdk
import requests
import os
import asyncio
import time
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from arcadepy import Arcade
from datetime import datetime, timedelta
from db.models.horizon.horizon_integration import HorizonIntegration

router = APIRouter(
    prefix="/horizon/integrations",
    tags=["horizon_integrations"],
    # dependencies=[Depends(validate_access_token)],
    # responses={404: {"description": "Not found"}},
)

# Initialize Arcade client
client = Arcade()  # Automatically finds the `ARCADE_API_KEY` env variable

# TTL Cache for tools list


class ToolsCache:
    def __init__(self, ttl_minutes=5):
        self.cache = {}
        self.ttl_seconds = ttl_minutes * 60
        print(f"Initialized ToolsCache with TTL: {ttl_minutes} minutes")

    def get(self, user_id: str):
        """Get cached tools for user if not expired"""
        if user_id not in self.cache:
            return None

        cached_data, timestamp = self.cache[user_id]

        # Check if cache is expired
        if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
            del self.cache[user_id]
            print(f"Cache expired for user {user_id}")
            return None

        print(
            f"Cache hit for user {user_id} (age: {(datetime.now() - timestamp).seconds}s)")
        return cached_data

    def set(self, user_id: str, tools):
        """Cache tools for user with timestamp"""
        self.cache[user_id] = (tools, datetime.now())
        print(f"Cached {len(tools)} tools for user {user_id}")

    def invalidate(self, user_id: str):
        """Manually invalidate cache for user"""
        if user_id in self.cache:
            del self.cache[user_id]
            print(f"Cache invalidated for user {user_id}")

    def clear_all(self):
        """Clear entire cache"""
        self.cache.clear()
        print("Cache cleared")

    def get_stats(self):
        """Get cache statistics"""
        total_users = len(self.cache)
        expired_count = 0

        for user_id, (_, timestamp) in self.cache.items():
            if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
                expired_count += 1

        return {
            "total_cached_users": total_users,
            "expired_entries": expired_count,
            "active_entries": total_users - expired_count
        }


# Initialize global cache instance
tools_cache = ToolsCache(ttl_minutes=5)

# Helper function to migrate user integrations from Arcade to database


async def migrate_user_integrations_from_arcade(user_id: str) -> int:
    """
    Migrate user integrations from Arcade API to database.
    This is called when a user has no integrations in the database.
    """
    try:
        print(
            f"Migrating integrations for user {user_id} from Arcade API to database...")

        # Get tools from Arcade API (use cache if available)
        tools = tools_cache.get(user_id)

        if tools is None:
            print(
                f"Cache miss during migration for user {user_id} - fetching from Arcade API")
            tools_page = client.tools.list(user_id=user_id)
            tools = list(tools_page)
            tools_cache.set(user_id, tools)

        # Process tools and create integration records
        migration_data = []
        for tool in tools:
            try:
                # Process each tool to extract integration data
                integration_data = process_single_tool(tool)
                if integration_data:
                    migration_data.append(integration_data)
            except Exception as e:
                print(
                    f"Error processing tool {getattr(tool, 'name', 'unknown')} during migration: {e}")
                continue

        # Bulk create integrations in database
        created_count = HorizonIntegration.bulk_create_from_arcade_tools(
            user_id, migration_data)

        print(
            f"Successfully migrated {created_count} integrations for user {user_id}")
        return created_count

    except Exception as e:
        print(f"Error migrating integrations for user {user_id}: {e}")
        traceback.print_exc()
        return 0

# Helper function for parallel tool processing


def process_tool_for_integration(tool):
    """Process a single tool and return provider information"""
    try:
        if not tool.requirements or not tool.requirements.authorization:
            return None

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
                provider_id = tool_name_lower.split('.')[0] if '.' in tool.name else tool_name_lower.split()[
                    0] if ' ' in tool_name_lower else "other"

        # Fallback if no provider found
        if not provider_id:
            provider_id = tool.name.lower().split(
                '.')[0] if '.' in tool.name else "unknown"

        return {
            "provider_id": provider_id,
            "status": status,
            "tool_name": tool.name
        }

    except Exception as e:
        print(f"Error processing tool {getattr(tool, 'name', 'unknown')}: {e}")
        return None


def process_tool_for_integration_fast(tool):
    """Optimized version with faster processing and timeouts"""
    try:
        # Skip tools without authorization requirements immediately
        if not hasattr(tool, 'requirements') or not tool.requirements or not tool.requirements.authorization:
            return None

        auth = tool.requirements.authorization

        # Quick status determination without deep inspection
        if hasattr(auth, 'token_status') and hasattr(auth, 'status'):
            if auth.token_status == "completed" and auth.status == "active":
                status = "connected"
            elif auth.token_status == "pending":
                status = "pending"
            elif auth.token_status == "failed":
                status = "failed"
            else:
                status = "not_connected"
        else:
            status = "not_connected"

        # Fast provider identification with minimal string operations
        provider_id = "other"
        if hasattr(auth, 'provider_type') and auth.provider_type:
            provider_type = auth.provider_type.lower()
            if provider_type != "oauth2":
                provider_id = provider_type
            else:
                # Quick provider mapping based on tool name
                tool_name = tool.name.lower() if hasattr(tool, 'name') else ""
                if "gmail" in tool_name or "email" in tool_name:
                    provider_id = "gmail"
                elif "google" in tool_name:
                    provider_id = "google"
                elif "microsoft" in tool_name or "outlook" in tool_name:
                    provider_id = "microsoft"
                elif "slack" in tool_name:
                    provider_id = "slack"
                elif "asana" in tool_name:
                    provider_id = "asana"
                elif "github" in tool_name:
                    provider_id = "github"
                elif "dropbox" in tool_name:
                    provider_id = "dropbox"
                elif "linkedin" in tool_name:
                    provider_id = "linkedin"
                elif "confluence" in tool_name:
                    provider_id = "confluence"
                # Add other quick matches here

        return {
            "provider_id": provider_id,
            "status": status
        }

    except Exception:
        # Return minimal default on any error
        return {
            "provider_id": "other",
            "status": "not_connected"
        }


def get_default_integrations():
    """Return default integrations when no tools are found"""
    default_providers = [
        "notion", "slack", "gmail", "outlook", "google-drive", "google-calendar", "pinterest"
    ]

    integrations = []
    for provider_id in default_providers:
        metadata = INTEGRATION_METADATA.get(provider_id, {})
        integration_item = V1IntegrationItem(
            name=provider_id,
            display_name=metadata.get("name", provider_id.title()),
            logo=metadata.get(
                "logo_url", "https://via.placeholder.com/64x64?text=?"),
            status="not_connected",
            provider=provider_id
        )
        integrations.append(integration_item)

    return integrations


# Integration metadata for v1 endpoint response formatting
INTEGRATION_METADATA = {
    "notion": {
        "name": "Notion",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/4/45/Notion_app_logo.png"
    },
    "slack": {
        "name": "Slack",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/d/d5/Slack_icon_2019.svg"
    },
    "gmail": {
        "name": "Gmail",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/7/7e/Gmail_icon_%282020%29.svg"
    },
    "outlook": {
        "name": "Microsoft Outlook",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/d/df/Microsoft_Office_Outlook_%282019%E2%80%93present%29.svg"
    },
    "google-drive": {
        "name": "Google Drive",
        "logo_url": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/google/google-original.svg"
    },
    "google-calendar": {
        "name": "Google Calendar",
        "logo_url": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/google/google-original.svg"
    },
    "pinterest": {
        "name": "Pinterest",
        "logo_url": "https://upload.wikimedia.org/wikipedia/commons/0/08/Pinterest-logo.png"
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


class CacheStatsResponse(BaseModel):
    success: bool
    stats: Dict[str, Any]
    message: str


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
    This will revoke the authorization and update the database.
    Database-centric approach for ultra-fast response times.
    """
    try:
        # Step 1: Check if integration exists in database
        db_integration = HorizonIntegration.get_by_user_and_integration(
            request.user_id, request.integration_name
        )

        if not db_integration:
            return IntegrationResponse(
                success=False,
                message=f"Integration {request.integration_name} not found for user {request.user_id}",
                status="not_found"
            )

        # Step 2: Check if integration is currently connected
        current_status = db_integration.get("status", "not_connected")
        if current_status != "connected":
            return IntegrationResponse(
                success=False,
                message=f"Integration {request.integration_name} is not connected (current status: {current_status})",
                status=current_status
            )

        # Step 3: Attempt to revoke from Arcade API (if connection ID available)
        arcade_connection_id = db_integration.get("arcade_connection_id")
        arcade_revoked = False

        if arcade_connection_id:
            # Try to revoke from Arcade API
            arcade_api_key = os.getenv("ARCADE_API_KEY")
            if arcade_api_key:
                try:
                    engine_url = "https://api.arcade.dev"
                    delete_url = f"{engine_url}/v1/admin/user_connections/{arcade_connection_id}"
                    delete_headers = {
                        "Authorization": f"Bearer {arcade_api_key}"}

                    delete_response = requests.delete(
                        delete_url, headers=delete_headers)
                    arcade_revoked = delete_response.status_code == 204

                    if not arcade_revoked:
                        print(
                            f"Warning: Failed to revoke from Arcade API: {delete_response.text}")
                except Exception as e:
                    print(f"Warning: Error revoking from Arcade API: {e}")

        # Step 4: Update database - mark as removed (this is the source of truth now)
        success = HorizonIntegration.remove_integration(
            request.user_id, request.integration_name)

        if success:
            # Invalidate cache since integration status changed
            tools_cache.invalidate(request.user_id)

            status_message = "revoked"
            if arcade_revoked:
                message = f"Integration {request.integration_name} successfully removed from both database and Arcade API"
            else:
                message = f"Integration {request.integration_name} successfully removed from database (Arcade API revocation may have failed)"

            return IntegrationResponse(
                success=True,
                message=message,
                status=status_message
            )
        else:
            return IntegrationResponse(
                success=False,
                message=f"Failed to remove integration {request.integration_name} from database",
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


def process_single_tool(tool):
    """Process a single tool and extract integration data"""
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

        # Map the tool to our specific integration providers
        provider_id = provider_type or (tool.name.split(
            '.')[0] if '.' in tool.name else tool.name)

        # Smart provider mapping based on tool functionality
        if provider_id == "oauth2":
            tool_name_lower = tool.name.lower()
            # Map to our specific integrations
            if any(keyword in tool_name_lower for keyword in ["gmail", "email", "thread", "draft"]):
                provider_id = "gmail"
            elif any(keyword in tool_name_lower for keyword in ["google", "spreadsheet", "document", "presentation", "calendar"]):
                if "calendar" in tool_name_lower:
                    provider_id = "google-calendar"
                elif any(keyword in tool_name_lower for keyword in ["spreadsheet", "document", "presentation", "drive"]):
                    provider_id = "google-drive"
                else:
                    provider_id = "google-drive"
            elif any(keyword in tool_name_lower for keyword in ["outlook", "microsoft", "onedrive"]):
                provider_id = "outlook"
            elif any(keyword in tool_name_lower for keyword in ["slack"]):
                provider_id = "slack"
            elif any(keyword in tool_name_lower for keyword in ["notion"]):
                provider_id = "notion"
            elif any(keyword in tool_name_lower for keyword in ["pinterest"]):
                provider_id = "pinterest"
            else:
                # For unrecognized oauth2 tools, don't include them
                provider_id = None

        # Only include tools that map to our specific integrations
        if provider_id and provider_id in INTEGRATION_METADATA:
            integration_data = {
                "name": tool.name,
                "description": getattr(tool, 'description', None),
                "auth_status": auth_status,
                "token_status": token_status,
                "authorized": is_authorized,
                "requirements_met": requirements_met,
                "provider": provider_id
            }
        else:
            # Skip tools that don't map to our integrations
            return None

        # Add optional fields if they exist
        if status_reason:
            integration_data["status_reason"] = status_reason
        if secrets_info:
            integration_data["secrets"] = secrets_info

        return integration_data

    except Exception as tool_error:
        # If checking a specific tool fails, return error data
        print(f'Error checking status for {tool.name}: {tool_error}')
        return {
            "name": tool.name,
            "auth_status": "error",
            "token_status": "error",
            "authorized": False,
            "requirements_met": False,
            "provider": tool.name.split('.')[0] if '.' in tool.name else tool.name,
            "error": str(tool_error)
        }


@router.post("/check_integrations", response_model=IntegrationsListResponse)
async def check_integrations(request: CheckIntegrationsRequest):
    """
    Check all existing integrations for a user using batch processing.
    Returns a list of authorized integrations and their status.
    """
    try:
        start_time = time.time()

        # Try to get tools from cache first
        tools = tools_cache.get(request.user_id)

        if tools is None:
            # Cache miss - fetch from Arcade API
            print(
                f"Cache miss for user {request.user_id} - fetching from Arcade API")
            tools_page = client.tools.list(user_id=request.user_id)

            # Convert paginated result to list
            tools = list(tools_page)

            # Cache the results
            tools_cache.set(request.user_id, tools)

            fetch_time = time.time()
            print(
                f"Fetched {len(tools)} tools from API in {fetch_time - start_time:.2f}s")
        else:
            # Cache hit
            fetch_time = time.time()
            print(
                f"Retrieved {len(tools)} tools from cache in {fetch_time - start_time:.4f}s")

        # Process tools in parallel using ThreadPoolExecutor
        integrations = []

        # Use ThreadPoolExecutor for I/O bound operations
        max_workers = min(50, len(tools))  # Limit concurrent threads

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tool processing tasks
            future_to_tool = {
                executor.submit(process_single_tool, tool): tool
                for tool in tools
            }

            # Collect results as they complete
            for future in as_completed(future_to_tool):
                tool = future_to_tool[future]
                try:
                    integration_data = future.result(
                        timeout=5.0)  # 5 second timeout per tool
                    integrations.append(integration_data)
                except Exception as exc:
                    print(f'Tool {tool.name} generated an exception: {exc}')
                    # Add error entry for failed tool
                    integrations.append({
                        "name": tool.name,
                        "auth_status": "error",
                        "token_status": "error",
                        "authorized": False,
                        "requirements_met": False,
                        "provider": tool.name.split('.')[0] if '.' in tool.name else tool.name,
                        "error": f"Processing timeout or error: {str(exc)}"
                    })

        processing_time = time.time()
        total_time = processing_time - start_time

        print(
            f"Processed {len(integrations)} integrations in {processing_time - fetch_time:.2f}s (Total: {total_time:.2f}s)")

        return IntegrationsListResponse(
            success=True,
            integrations=integrations,
            message=f"Retrieved {len(integrations)} integration statuses for user {request.user_id} in {total_time:.2f}s"
        )

    except Exception as e:
        print(f'Error checking integrations for user {request.user_id}: ', e)
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check integrations: {str(e)}"
        )


@router.get("/cache_stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """
    Get statistics about the tools cache.
    Useful for monitoring cache performance and debugging.
    """
    try:
        stats = tools_cache.get_stats()
        return CacheStatsResponse(
            success=True,
            stats=stats,
            message=f"Cache stats retrieved successfully"
        )
    except Exception as e:
        print(f'Error getting cache stats: {e}')
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cache stats: {str(e)}"
        )


@router.post("/clear_cache")
async def clear_tools_cache():
    """
    Clear the entire tools cache. Use with caution.
    """
    try:
        tools_cache.clear_all()
        return {"success": True, "message": "Cache cleared successfully"}
    except Exception as e:
        print(f'Error clearing cache: {e}')
        traceback.print_exc()
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
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
    Simplified to always return the 7 specific integrations we want.
    """
    try:
        start_time = time.time()

        # Always return our specific integrations regardless of database state
        integrations = get_default_integrations()

        total_time = time.time() - start_time
        print(
            f"V1 endpoint completed in {total_time:.4f}s with {len(integrations)} integrations")

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
