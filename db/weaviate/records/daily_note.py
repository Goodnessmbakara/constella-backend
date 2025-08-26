from typing import List, Dict
from .general_record import GeneralWeaviateRecord

class WeaviateDailyNote(GeneralWeaviateRecord):
    """
    A DailyNote class that extends GeneralWeaviateRecord
    """
    def __init__(self,
                 uniqueid: str,
                 vector: List[float],
                 date: str,
                 content: str,
                 created: int,
                 lastModified: int):
        super().__init__(uniqueid, vector, created, lastModified, "daily_note")
        self.properties.update({
            "date": date,
            "content": content,
            "uniqueid": uniqueid
        })

    def to_dict(self) -> Dict:
        return super().to_dict()

    def to_milvus_dict(self, tenant_name: str) -> Dict:
        """
        Convert daily note record to flat dictionary suitable for Milvus operations
        """
        milvus_dict = super().to_milvus_dict(tenant_name)
        # Ensure all daily note-specific fields are included
        milvus_dict.update({
            "date": self.properties.get("date", ""),
            "content": self.properties.get("content", ""),
        })
        return milvus_dict

    @classmethod
    def from_dict(cls, data: Dict) -> 'WeaviateDailyNote':
        properties = data.get("properties", {})
        return cls(
            uniqueid=data.get("uniqueid", ""),
            vector=data.get("vector", [0.0] * 384),
            date=properties.get("date", ""),
            content=properties.get("content", ""),
            created=properties.get("created", 0),
            lastModified=properties.get("lastModified", 0)
        )

    @classmethod
    def from_rxdb(cls, data: dict) -> 'WeaviateDailyNote':
        return cls(
            uniqueid=data.get("uniqueid", ""),
            vector=list(data.get("vector", {}).values()) if isinstance(data.get("vector"), dict) else data.get("vector", [0.0] * 384),
            date=data.get("date", ""),
            content=data.get("content", ""),
            created=data.get("created", 0),
            lastModified=data.get("lastModified", 0)
        )