from typing import List, Dict
import json

class GeneralWeaviateRecord:
	"""
	A GeneralWeaviateRecord instance
	Separates uniqueid and vector from properties
	Other records extend this to add on their own properties
	"""
	def __init__(self,
				 uniqueid: str,
				 vector: List[float],
				 created: int,
				 lastModified: int,
				 recordType: str,
				 lastUpdateDevice: str = ""):
		if recordType == 'note' and len(vector) < 384:
			# add zeros to end
			vector.extend([0.0] * (384 - len(vector)))
		elif recordType == 'note' and len(vector) > 384:
			# remove last 384 elements
			vector = vector[:384]
		
		self.uniqueid = uniqueid
		self.vector = vector
		self.properties = {
			"created": created,
			"lastModified": lastModified,
			"recordType": recordType,
			"lastUpdateDevice": lastUpdateDevice,
		}

	def to_dict(self) -> Dict:
		return {
			"uniqueid": self.uniqueid,
			"vector": self.vector,
			"properties": self.properties
		}

	def to_milvus_dict(self, tenant_name: str) -> Dict:
		"""
		Convert record to flat dictionary suitable for Milvus operations
		"""
		milvus_dict = {
			"uniqueid": self.uniqueid,
			"vector": self.vector,
			"tenantName": tenant_name,
		}
		# Flatten all properties into the main dictionary
		milvus_dict.update(self.properties)

		# --- Normalise special fields for Milvus compatibility ---
		# Ensure ``tagIds`` (if present) is either ``None`` or a list[str].
		if "tagIds" in milvus_dict:
			_tag_ids = milvus_dict["tagIds"]

			# Treat empty / falsy values as NULL so that the column can remain nullable
			if not _tag_ids:
				milvus_dict["tagIds"] = None
			elif isinstance(_tag_ids, list):
				# Convert all elements to strings in-place
				milvus_dict["tagIds"] = [str(t) for t in _tag_ids if t is not None and str(t) != ""]
				# If the resulting list is empty, store NULL instead
				if not milvus_dict["tagIds"]:
					milvus_dict["tagIds"] = None
			else:
				# Single value (e.g. UUID object / raw string) -> wrap in list[str]
				milvus_dict["tagIds"] = [str(_tag_ids)]

		# -----------------------------------------------------------------

		# Convert ``tags`` (list/dict) to JSON string for Milvus VARCHAR column
		if "tags" in milvus_dict and milvus_dict["tags"] is not None and not isinstance(milvus_dict["tags"], str):
			try:
				milvus_dict["tags"] = json.dumps(milvus_dict["tags"])
			except Exception:
				milvus_dict["tags"] = "[]"

		# Guard against cases (e.g. ``WeaviateTag``) where ``uniqueid`` also lives
		# inside ``self.properties`` and could have been an outdated/empty value.
		# Re-apply the authoritative ID held on the object itself so it always wins.
		milvus_dict["uniqueid"] = self.uniqueid

		return milvus_dict

	@classmethod
	def from_dict(cls, data: Dict) -> 'GeneralWeaviateRecord':
		return cls(
			uniqueid=data.get("uniqueid", ""),
			vector=data.get("vector", [0.0] * 384),
			created=data.get("properties", {}).get("created", 0),
			lastModified=data.get("properties", {}).get("lastModified", 0),
			recordType=data.get("properties", {}).get("recordType", ""),
			lastUpdateDevice=data.get("properties", {}).get("lastUpdateDevice", "")
		)
	
	@classmethod
	def from_rxdb(cls, data: dict) -> 'GeneralWeaviateRecord':
		return cls(
			uniqueid=data.get("uniqueid", ""),
			vector=list(data.get("vector", {}).values()) if isinstance(data.get("vector"), dict) else data.get("vector", [0.0] * 384),
			created=data.get("created", 0),
			lastModified=data.get("lastModified", 0),
			recordType=data.get("recordType", ""),
			lastUpdateDevice=data.get("lastUpdateDevice", "")
		)