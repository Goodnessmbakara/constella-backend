from db.weaviate.records.general_record import GeneralWeaviateRecord
from typing import List, Dict, Optional
import time
from enum import Enum


class BodyType(Enum):
    NOTE = "note"
    JOURNAL = "journal"


class WeaviateNoteBody(GeneralWeaviateRecord):
    """
    A NoteBody class that extends GeneralWeaviateRecord
    """
    def __init__(self,
                 uniqueid: str,
                 vector: List[float],
                 text: str,
                 referenceId: str, # The referring note it is related to
                 type: BodyType,
                 created: int,
                 lastModified: int,
                 lastUpdateDevice: str,
                 position: Optional[int] = None,
                 journalDate: Optional[int] = None,
                 referenceTitle: Optional[str] = None
                ):
        super().__init__(uniqueid, vector, created, lastModified, "noteBody", lastUpdateDevice)
        self.properties.update({
            "text": text,
            "referenceId": referenceId,
            "referenceTitle": referenceTitle,
            "type": type.value,
            "position": position,
            "journalDate": journalDate,
        })

    def to_milvus_dict(self, tenant_name: str) -> Dict:
        """
        Convert note body record to flat dictionary suitable for Milvus operations
        """
        milvus_dict = super().to_milvus_dict(tenant_name)
        # Ensure all note body-specific fields are included
        milvus_dict.update({
            "text": self.properties.get("text", ""),
            "referenceId": self.properties.get("referenceId", ""),
            "referenceTitle": self.properties.get("referenceTitle", ""),
            "type": self.properties.get("type", ""),
            "position": self.properties.get("position", None),
            "journalDate": self.properties.get("journalDate", None),
        })
        return milvus_dict

    @classmethod
    def from_dict(cls, data: Dict) -> 'WeaviateNoteBody':
        type_value = data.get("properties", {}).get("type", "")
        body_type = BodyType.NOTE
        try:
            body_type = BodyType(type_value)
        except ValueError:
            # Default to NOTE if invalid type
            pass
            
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=data.get("vector", [0.0] * 384),
            text=data.get("properties", {}).get("text", ""),
            referenceId=data.get("properties", {}).get("referenceId", ""),
            type=body_type,
            created=data.get("properties", {}).get("created", 0),
            lastModified=data.get("properties", {}).get("lastModified", 0),
            lastUpdateDevice=data.get("properties", {}).get("lastUpdateDevice", ""),
            position=data.get("properties", {}).get("position", None),
            journalDate=data.get("properties", {}).get("journalDate", None),
            referenceTitle=data.get("properties", {}).get("referenceTitle", None),
        )

    @classmethod
    def from_rxdb(cls, data: dict) -> 'WeaviateNoteBody':
        type_value = data.get("type", "")
        body_type = BodyType.NOTE
        try:
            body_type = BodyType(type_value)
        except ValueError:
            # Default to NOTE if invalid type
            pass
            
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=list(data.get("vector", {}).values()) if isinstance(data.get("vector"), dict) else data.get("vector", [0.0] * 384),
            text=data.get("text", ""),
            referenceId=data.get("referenceId", ""),
            type=body_type,
            created=data.get("created", int(time.time() * 1000)),
            lastModified=data.get("lastModified", int(time.time() * 1000)),
            lastUpdateDevice=data.get("lastUpdateDevice", ""),
            position=data.get("position", None),
            journalDate=data.get("journalDate", None),
            referenceTitle=data.get("referenceTitle", None),
        )