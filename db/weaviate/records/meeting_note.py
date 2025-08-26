from db.weaviate.records.general_record import GeneralWeaviateRecord
from typing import List, Dict
import time


class MeetingNote(GeneralWeaviateRecord):
    """
    A Meeting Note class that extends GeneralWeaviateRecord
    """
    def __init__(self,
                 uniqueid: str,
                 vector: List[float],
                 notes: List[dict],
                 transcript: List[dict],
                 created: int,
                 ai_chat_messages: List[dict],
                 tenant_name: str,
                 title: str = "Untitled Meeting",
                 description: str = "",
                 lastModified: int = None,
                 lastUpdateDevice: str = "",
                 lastUpdateDeviceId: str = "",
                 referenceId: str = None
                ):
        if lastModified is None:
            lastModified = int(time.time() * 1000)
            
        super().__init__(uniqueid, vector, created, lastModified, "meeting_note", lastUpdateDevice)
        self.properties.update({
            "notes": notes,
            "transcript": transcript,
            "ai_chat_messages": ai_chat_messages,
            "tenant_name": tenant_name,
            "title": title,
            "description": description,
            "lastUpdateDeviceId": lastUpdateDeviceId,
            "referenceId": referenceId or uniqueid,
        })

    def to_milvus_dict(self, tenant_name: str) -> Dict:
        """
        Convert meeting note record to flat dictionary suitable for Milvus operations
        """
        milvus_dict = super().to_milvus_dict(tenant_name)
        # Ensure all meeting note-specific fields are included
        milvus_dict.update({
            "notes": self.properties.get("notes", []),
            "transcript": self.properties.get("transcript", []),
            "ai_chat_messages": self.properties.get("ai_chat_messages", []),
            "tenant_name": self.properties.get("tenant_name", tenant_name),
            "title": self.properties.get("title", "Untitled Meeting"),
            "description": self.properties.get("description", ""),
            "lastUpdateDeviceId": self.properties.get("lastUpdateDeviceId", ""),
            "referenceId": self.properties.get("referenceId"),
        })
        return milvus_dict

    @classmethod
    def from_dict(cls, data: Dict) -> 'MeetingNote':
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=data.get("vector", [0.0] * 1024),  # Using our_embedding_dimension
            notes=data.get("properties", {}).get("notes", []),
            transcript=data.get("properties", {}).get("transcript", []),
            created=data.get("properties", {}).get("created", int(time.time() * 1000)),
            ai_chat_messages=data.get("properties", {}).get("ai_chat_messages", []),
            tenant_name=data.get("properties", {}).get("tenant_name", ""),
            title=data.get("properties", {}).get("title", "Untitled Meeting"),
            description=data.get("properties", {}).get("description", ""),
            lastModified=data.get("properties", {}).get("lastModified", int(time.time() * 1000)),
            lastUpdateDevice=data.get("properties", {}).get("lastUpdateDevice", ""),
            lastUpdateDeviceId=data.get("properties", {}).get("lastUpdateDeviceId", ""),
            referenceId=data.get("properties", {}).get("referenceId"),
        )

    @classmethod
    def from_request_data(cls, data: dict, tenant_name: str) -> 'MeetingNote':
        """
        Create MeetingNote from API request data
        """
        current_time = int(time.time() * 1000)
        
        # Determine title
        title = data.get("title", "")
        if not title:
            # Look for title in first note
            notes = data.get("notes", [])
            if notes and isinstance(notes[0], dict) and notes[0].get("title"):
                title = notes[0]["title"]
            else:
                title = "Untitled Meeting"
        
        # Determine description from first bulletpoint found
        description = data.get("description", "")
        if not description:
            notes = data.get("notes", [])
            for note in notes:
                if isinstance(note, dict) and note.get("bulletpoints"):
                    bulletpoints = note["bulletpoints"]
                    if bulletpoints and len(bulletpoints) > 0:
                        # Get first bulletpoint
                        first_bullet = bulletpoints[0]
                        if isinstance(first_bullet, dict):
                            description = first_bullet.get("text", "") or first_bullet.get("content", "")
                        elif isinstance(first_bullet, str):
                            description = first_bullet
                        break
        
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=data.get("vector", [0.0] * 1024),  # Will be generated later
            notes=data.get("notes", []),
            transcript=data.get("transcript", []),
            created=data.get("created", current_time),
            ai_chat_messages=data.get("ai_chat_messages", []),
            tenant_name=tenant_name,
            title=title,
            description=description,
            lastModified=current_time,
            lastUpdateDevice=data.get("lastUpdateDevice", ""),
            lastUpdateDeviceId=data.get("lastUpdateDeviceId", ""),
            referenceId=data.get("referenceId"),
        ) 