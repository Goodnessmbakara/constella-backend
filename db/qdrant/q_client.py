import os
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
	Distance,
	HnswConfigDiff,
	KeywordIndexParams,
	TextIndexParams,
	VectorParams,
)


DEFAULT_MODEL = "sentence-transformers/all-minilm-l6-v2"
our_qdrant_client = None

def get_qdrant_client(
	*,
	url: Optional[str] = None,
	api_key: Optional[str] = None,
	cloud_inference: bool = True,
) -> QdrantClient:
	"""Create and return a configured Qdrant client.

	Reads `QDRANT_URL` and `QDRANT_API_KEY` from environment by default.
	"""
	global our_qdrant_client
	if our_qdrant_client:
		return our_qdrant_client
	
	qdrant_url = "https://69c976f5-f0bc-44d6-9e40-078b0ad4847b.us-east-1-0.aws.cloud.qdrant.io"
	qdrant_api_key = api_key or os.getenv("QDRANT_API_KEY")

	if not qdrant_url:
		raise ValueError(
			"QDRANT_URL is not set. Provide url param or set environment variable QDRANT_URL."
		)
	if not qdrant_api_key:
		raise ValueError(
			"QDRANT_API_KEY is not set. Provide api_key param or set environment variable QDRANT_API_KEY."
		)

	our_qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, cloud_inference=True)
	return our_qdrant_client


def ensure_collection(
	client: QdrantClient,
	*,
	collection_name: str,
	vector_size: int = 384,
	distance: Distance = Distance.COSINE,
	create_text_indexes: bool = True,
) -> None:
	"""Ensure collection exists with multitenancy and performance-optimized config.

	- Multitenancy: creates a keyword index for `group_id` with `is_tenant=True`.
	- Performance: disables global HNSW index (m=0) and enables per-tenant payload index (payload_m=16).
	- Optionally creates TEXT indexes for `title` and `content`.
	"""
	# Create collection
	try:
		client.get_collection(collection_name=collection_name)
		# Collection exists – still ensure indexes exist (idempotent)
	except Exception:
		client.create_collection(
			collection_name=collection_name,
			vectors_config=VectorParams(size=vector_size, distance=distance),
			hnsw_config=HnswConfigDiff(payload_m=16, m=0),
		)

	# Ensure tenant keyword index on group_id
	try:
		client.create_payload_index(
			collection_name=collection_name,
			field_name="group_id",
			field_schema=KeywordIndexParams(type="keyword", is_tenant=True),
		)
	except Exception:
		# Likely already exists
		pass

	if create_text_indexes:
		for field in ("title", "content"):
			try:
				client.create_payload_index(
					collection_name=collection_name,
					field_name=field,
					field_schema=TextIndexParams(type="text"),
				)
			except Exception:
				pass


