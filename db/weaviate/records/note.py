from db.weaviate.records.general_record import GeneralWeaviateRecord
from typing import List, Dict
import time


class WeaviateNote(GeneralWeaviateRecord):
    """
    A Note class that extends GeneralWeaviateRecord
    """
    def __init__(self,
                 uniqueid: str,
                 vector: List[float],
                 title: str,
                 content: str,
                 filePath: str,
                 tags: List[dict],
                 created: int,
                 lastModified: int,
                 lastUpdateDevice: str,
                 lastUpdateDeviceId: str,
                 incomingConnections: List[str],
                 outgoingConnections: List[str],
                 tagIds: List[str], # just unique-ids in list for Weaviate filtering of all notes with a tag
                 fileData: str = "",
                 fileType: str = "",
                 fileText: str = "",
                 noteType: str = ""
			):
        super().__init__(uniqueid, vector, created, lastModified, "note", lastUpdateDevice)
        self.properties.update({
            "title": title,
            "content": content,
            "filePath": filePath,
            "tags": tags,
            "incomingConnections": incomingConnections,
            "outgoingConnections": outgoingConnections,
            "tagIds": tagIds,
            "lastUpdateDeviceId": lastUpdateDeviceId,
            "fileData": fileData,
            "fileType": fileType,
            "fileText": fileText,
            "noteType": noteType,
        })

    def to_milvus_dict(self, tenant_name: str) -> Dict:
        """
        Convert note record to flat dictionary suitable for Milvus operations
        """
        milvus_dict = super().to_milvus_dict(tenant_name)
        # Ensure all note-specific fields are included
        milvus_dict.update({
            "title": self.properties.get("title", ""),
            "content": self.properties.get("content", ""),
            "filePath": self.properties.get("filePath", ""),
            "tags": self.properties.get("tags", []),
            "incomingConnections": self.properties.get("incomingConnections", []),
            "outgoingConnections": self.properties.get("outgoingConnections", []),
            "lastUpdateDeviceId": self.properties.get("lastUpdateDeviceId", ""),
            "fileData": self.properties.get("fileData", ""),
            "fileType": self.properties.get("fileType", ""),
            "fileText": self.properties.get("fileText", ""),
            "noteType": self.properties.get("noteType", ""),
        })
        return milvus_dict

    @classmethod
    def from_dict(cls, data: Dict) -> 'WeaviateNote':
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=data.get("vector", [0.0] * 384),
            title=data.get("properties", {}).get("title", ""),
            content=data.get("properties", {}).get("content", ""),
            filePath=data.get("properties", {}).get("filePath", ""),
            tags=data.get("properties", {}).get("tags", []),
            created=data.get("properties", {}).get("created", 0),
            lastModified=data.get("properties", {}).get("lastModified", 0),
            lastUpdateDevice=data.get("properties", {}).get("lastUpdateDevice", ""),
            lastUpdateDeviceId=data.get("properties", {}).get("lastUpdateDeviceId", ""),
            incomingConnections=data.get("properties", {}).get("incomingConnections", []),
            outgoingConnections=data.get("properties", {}).get("outgoingConnections", []),
			# if tagIds does not exist already, construct it from the tags
            tagIds=data.get("properties", {}).get("tagIds") or [tag.get("uniqueid") for tag in data.get("tags", [])],
            fileData=data.get("properties", {}).get("fileData", ""),
            fileType=data.get("properties", {}).get("fileType", ""),
            fileText=data.get("properties", {}).get("fileText", ""),
            noteType=data.get("properties", {}).get("noteType", "")
        )

    @classmethod
    def from_rxdb(cls, data: dict) -> 'WeaviateNote':
        return cls(
            uniqueid=data.get("uniqueid", None),
            vector=list(data.get("vector", {}).values()) if isinstance(data.get("vector"), dict) else data.get("vector", [0.0] * 384),
            title=data.get("title", ""),
            content=data.get("content", ""),
            filePath=data.get("filePath", ""),
            tags=data.get("tags", []),
            created=data.get("created", int(time.time() * 1000)),
            lastModified=data.get("lastModified", int(time.time() * 1000)),
            lastUpdateDevice=data.get("lastUpdateDevice", ""),
            lastUpdateDeviceId=data.get("lastUpdateDeviceId", ""),
            incomingConnections=data.get("incomingConnections", []),
            outgoingConnections=data.get("outgoingConnections", []),
			# if tagIds does not exist already, construct it from the tags
            tagIds=data.get("properties", {}).get("tagIds") or [tag.get("uniqueid") for tag in data.get("tags", [])],
            fileData=data.get("fileData", ""),
            fileType=data.get("fileType", ""),
            fileText=data.get("fileText", ""),
            noteType=data.get("noteType", "")
        )