from db.weaviate.records.general_record import GeneralWeaviateRecord
from typing import List, Dict

class WeaviateMisc(GeneralWeaviateRecord):
    """
    A Misc class that extends GeneralWeaviateRecord
    """
    def __init__(self,
                 uniqueid: str,
                 vector: List[float],
                 date: str,
                 content: str,
                 foreignId: str,
                 miscData: str,
                 startId: str,
                 startData: str,
                 endId: str,
                 endData: str,
                 created: int,
                 lastModified: int,
                 lastUpdateDevice: str,
                 type: str = ""
                ):
        super().__init__(uniqueid, vector, created, lastModified, "misc", lastUpdateDevice)
        self.properties.update({
            "date": date,
            "content": content,
            "foreignId": foreignId,
            "miscData": miscData,
            "startId": startId,
            "startData": startData,
            "endId": endId,
            "endData": endData,
            "type": type
        })

    def to_milvus_dict(self, tenant_name: str) -> Dict:
        """
        Convert misc record to flat dictionary suitable for Milvus operations
        """
        milvus_dict = super().to_milvus_dict(tenant_name)
        # Ensure all misc-specific fields are included
        milvus_dict.update({
            "date": self.properties.get("date", ""),
            "content": self.properties.get("content", ""),
            "foreignId": self.properties.get("foreignId", ""),
            "miscData": self.properties.get("miscData", ""),
            "startId": self.properties.get("startId", ""),
            "startData": self.properties.get("startData", ""),
            "endId": self.properties.get("endId", ""),
            "endData": self.properties.get("endData", ""),
            "type": self.properties.get("type", "")
        })
        return milvus_dict

    @classmethod
    def from_dict(cls, data: Dict) -> 'WeaviateMisc':
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=data.get("vector", [0.0] * 384),
            date=data.get("properties", {}).get("date", ""),
            content=data.get("properties", {}).get("content", ""),
            foreignId=data.get("properties", {}).get("foreignId", ""),
            miscData=data.get("properties", {}).get("miscData", ""),
            startId=data.get("properties", {}).get("startId", ""),
            startData=data.get("properties", {}).get("startData", ""),
            endId=data.get("properties", {}).get("endId", ""),
            endData=data.get("properties", {}).get("endData", ""),
            created=data.get("properties", {}).get("created", 0),
            lastModified=data.get("properties", {}).get("lastModified", 0),
            lastUpdateDevice=data.get("properties", {}).get("lastUpdateDevice", ""),
            type=data.get("properties", {}).get("type", "")
        )

    @classmethod
    def from_rxdb(cls, data: dict) -> 'WeaviateMisc':
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=list(data.get("vector", {}).values()) if isinstance(data.get("vector"), dict) else data.get("vector", [0.0] * 384),
            date=data.get("date", ""),
            content=data.get("content", ""),
            foreignId=data.get("foreignId", ""),
            miscData=data.get("miscData", ""),
            startId=data.get("startId", ""),
            startData=data.get("startData", ""),
            endId=data.get("endId", ""),
            endData=data.get("endData", ""),
            created=data.get("created", 0),
            lastModified=data.get("lastModified", 0),
            lastUpdateDevice=data.get("lastUpdateDevice", ""),
            type=data.get("type", "")
        )