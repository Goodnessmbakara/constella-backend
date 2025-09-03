from db.mongodb import db
from datetime import datetime
from utils.json import parse_json
from typing import List, Dict, Any, Optional
from bson.objectid import ObjectId

# MongoDB collection for storing Horizon integrations
collection = db['horizon_integrations']

class HorizonIntegration:
    """
    Represents a user's integration with a third-party service via Arcade.
    
    This model stores the integration state locally for fast queries,
    reducing dependency on Arcade API calls.
    """
    
    def __init__(self, user_id: str, integration_name: str, provider: str, 
                 status: str = "not_connected", auth_status: str = "inactive", 
                 token_status: str = "not_started", arcade_connection_id: str = None,
                 display_name: str = None, logo_url: str = None, 
                 scopes: List[str] = None, metadata: Dict[str, Any] = None):
        self.user_id = user_id
        self.integration_name = integration_name
        self.provider = provider
        self.status = status  # connected, pending, not_connected, failed
        self.auth_status = auth_status  # active, inactive
        self.token_status = token_status  # completed, pending, not_started, failed
        self.arcade_connection_id = arcade_connection_id
        self.display_name = display_name or integration_name.title()
        self.logo_url = logo_url
        self.scopes = scopes or []
        self.metadata = metadata or {}
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def save(self) -> dict:
        """Save the integration to MongoDB and return the persisted record."""
        # Check if integration already exists
        existing = collection.find_one({
            "user_id": self.user_id,
            "integration_name": self.integration_name
        })
        
        if existing:
            # Update existing
            self.updated_at = datetime.utcnow()
            collection.update_one(
                {"user_id": self.user_id, "integration_name": self.integration_name},
                {"$set": self.__dict__}
            )
            return parse_json(collection.find_one({
                "user_id": self.user_id,
                "integration_name": self.integration_name
            }))
        else:
            # Insert new
            result = collection.insert_one(self.__dict__)
            return parse_json(collection.find_one({"_id": result.inserted_id}))
    
    @staticmethod
    def get_by_user_id(user_id: str) -> List[dict]:
        """Get all integrations for a user."""
        integrations = list(collection.find({"user_id": user_id}))
        return [parse_json(integration) for integration in integrations]
    
    @staticmethod
    def get_by_user_and_integration(user_id: str, integration_name: str) -> Optional[dict]:
        """Get a specific integration for a user."""
        integration = collection.find_one({
            "user_id": user_id,
            "integration_name": integration_name
        })
        return parse_json(integration) if integration else None
    
    @staticmethod
    def update_status(user_id: str, integration_name: str, status: str = None, 
                     auth_status: str = None, token_status: str = None,
                     arcade_connection_id: str = None, **kwargs) -> bool:
        """Update integration status fields."""
        update_fields = {"updated_at": datetime.utcnow()}
        
        if status is not None:
            update_fields["status"] = status
        if auth_status is not None:
            update_fields["auth_status"] = auth_status
        if token_status is not None:
            update_fields["token_status"] = token_status
        if arcade_connection_id is not None:
            update_fields["arcade_connection_id"] = arcade_connection_id
        
        # Add any additional fields
        update_fields.update(kwargs)
        
        result = collection.update_one(
            {"user_id": user_id, "integration_name": integration_name},
            {"$set": update_fields}
        )
        
        return result.modified_count > 0
    
    @staticmethod
    def remove_integration(user_id: str, integration_name: str) -> bool:
        """Mark integration as removed (set status to not_connected)."""
        result = collection.update_one(
            {"user_id": user_id, "integration_name": integration_name},
            {"$set": {
                "status": "not_connected",
                "auth_status": "inactive", 
                "token_status": "not_started",
                "arcade_connection_id": None,
                "updated_at": datetime.utcnow()
            }}
        )
        return result.modified_count > 0
    
    @staticmethod
    def delete_integration(user_id: str, integration_name: str) -> bool:
        """Permanently delete an integration record."""
        result = collection.delete_one({
            "user_id": user_id,
            "integration_name": integration_name
        })
        return result.deleted_count > 0
    
    @staticmethod
    def get_all() -> List[dict]:
        """Get all integrations (for admin purposes)."""
        integrations = list(collection.find({}))
        return [parse_json(integration) for integration in integrations]
    
    @staticmethod
    def get_connected_integrations(user_id: str) -> List[dict]:
        """Get only connected integrations for a user."""
        integrations = list(collection.find({
            "user_id": user_id,
            "status": "connected",
            "auth_status": "active",
            "token_status": "completed"
        }))
        return [parse_json(integration) for integration in integrations]
    
    @staticmethod
    def bulk_create_from_arcade_tools(user_id: str, tools_data: List[dict]) -> int:
        """
        Bulk create/update integrations from Arcade tools data.
        This is used for migration and sync purposes.
        """
        created_count = 0
        
        for tool_data in tools_data:
            try:
                # Extract integration info from tool data
                integration_name = tool_data.get("name", "unknown")
                provider = tool_data.get("provider", "unknown")
                
                # Map Arcade status to our status
                auth_status = tool_data.get("auth_status", "inactive")
                token_status = tool_data.get("token_status", "not_started")
                
                if auth_status == "active" and token_status == "completed":
                    status = "connected"
                elif token_status == "pending":
                    status = "pending"
                elif token_status == "failed":
                    status = "failed"
                else:
                    status = "not_connected"
                
                # Create/update integration
                integration = HorizonIntegration(
                    user_id=user_id,
                    integration_name=integration_name,
                    provider=provider,
                    status=status,
                    auth_status=auth_status,
                    token_status=token_status,
                    display_name=tool_data.get("display_name"),
                    logo_url=tool_data.get("logo_url"),
                    metadata=tool_data
                )
                
                integration.save()
                created_count += 1
                
            except Exception as e:
                print(f"Error creating integration from tool data {tool_data}: {e}")
                continue
        
        return created_count
