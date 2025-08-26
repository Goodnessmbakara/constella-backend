from typing import List, Dict
from .general_record import GeneralWeaviateRecord

class WeaviateTag(GeneralWeaviateRecord):
    """
    A Tag class that extends GeneralWeaviateRecord
    """
    def __init__(self,
                 uniqueid: str,
                 vector: List[float],
                 color: str,
                 name: str,
                 created: int,
                 lastModified: int,
                 lastUpdateDevice: str = "",
                 lastUpdateDeviceId: str = ""):
        super().__init__(uniqueid, vector, created, lastModified, "tag", lastUpdateDevice)
        self.properties.update({
            "color": color,
            "name": name,
            "uniqueid": uniqueid,
            "lastUpdateDeviceId": lastUpdateDeviceId
        })

    def to_dict(self) -> Dict:
        return super().to_dict()

    def to_milvus_dict(self, tenant_name: str) -> Dict:
        """
        Convert tag record to flat dictionary suitable for Milvus operations
        """
        milvus_dict = super().to_milvus_dict(tenant_name)
        # Ensure all tag-specific fields are included
        milvus_dict.update({
            "color": self.properties.get("color", ""),
            "name": self.properties.get("name", ""),
            "lastUpdateDeviceId": self.properties.get("lastUpdateDeviceId", ""),
        })
        return milvus_dict

    @classmethod
    def from_dict(cls, data: Dict) -> 'WeaviateTag':
        tag_properties = data.get("properties", {}).get("tagProperties", {})
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=data.get("vector", [0.0] * 384),
            color=tag_properties.get("color", ""),
            name=tag_properties.get("name", ""),
            created=data.get("properties", {}).get("created", 0),
            lastModified=data.get("properties", {}).get("lastModified", 0),
            lastUpdateDevice=data.get("properties", {}).get("lastUpdateDevice", ""),
            lastUpdateDeviceId=data.get("properties", {}).get("lastUpdateDeviceId", "")
        )

    @classmethod
    def from_rxdb(cls, data: dict) -> 'WeaviateTag':
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=list(data.get("vector", {}).values()) if isinstance(data.get("vector"), dict) else data.get("vector", [0.0] * 384),
            color=data.get("color", ""),
            name=data.get("name", ""),
            created=data.get("created", 0),
            lastModified=data.get("lastModified", 0),
            lastUpdateDevice=data.get("lastUpdateDevice", ""),
            lastUpdateDeviceId=data.get("lastUpdateDeviceId", "")
        )