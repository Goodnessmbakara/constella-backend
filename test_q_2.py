# minimal_repro_qdrant_inference.py

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    Document,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    KeywordIndexParams,
    MatchText,
    MatchValue,
    PointIdsList,
    PointStruct,
    TextIndexParams,
    VectorParams,
)

# Mirrors current defaults in our code
DEFAULT_MODEL = "sentence-transformers/all-minilm-l6-v2"
TENANT_PAYLOAD_KEY = "group_id"


def get_qdrant_client(*, url: Optional[str] = None, api_key: Optional[str] = None, cloud_inference: bool = True) -> QdrantClient:
    # Our code uses a fixed URL and reads QDRANT_API_KEY from env
    qdrant_url = url or "https://69c976f5-f0bc-44d6-9e40-078b0ad4847b.us-east-1-0.aws.cloud.qdrant.io"
    qdrant_api_key = api_key or os.getenv("QDRANT_API_KEY")
    if not qdrant_url:
        raise ValueError("QDRANT_URL is not set.")
    if not qdrant_api_key:
        raise ValueError("QDRANT_API_KEY is not set.")
    return QdrantClient(url=qdrant_url, api_key=qdrant_api_key, cloud_inference=cloud_inference)


def ensure_collection(
    client: QdrantClient,
    *,
    collection_name: str,
    vector_size: int = 384,
    distance: Distance = Distance.COSINE,
    create_text_indexes: bool = True,
) -> None:
    # Same logic as our helper: create if missing, configure HNSW and payload/text indexes
    try:
        client.get_collection(collection_name=collection_name)
    except Exception:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
            hnsw_config=HnswConfigDiff(payload_m=16, m=0),
        )

    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=TENANT_PAYLOAD_KEY,
            field_schema=KeywordIndexParams(type="keyword", is_tenant=True),
        )
    except Exception:
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


@dataclass
class QdrantRecord:
    uniqueid: str
    title: str
    content: str
    dateCreated: str
    dateModified: str
    source: str
    link: str
    relatedItems: List[str]
    parentId: Optional[str]
    fileUrl: str

    @staticmethod
    def new(
        *,
        title: str,
        content: str,
        source: str = "",
        link: str = "",
        parentId: Optional[str] = None,
        relatedItems: Optional[List[str]] = None,
        fileUrl: str = "",
    ) -> "QdrantRecord":
        now = datetime.utcnow().isoformat()
        return QdrantRecord(
            uniqueid=str(uuid.uuid4()),
            title=title,
            content=content,
            dateCreated=now,
            dateModified=now,
            source=source,
            link=link,
            relatedItems=relatedItems or [],
            parentId=parentId,
            fileUrl=fileUrl,
        )


def _tenant_filter(group_id: str, extra_must: Optional[List[FieldCondition]] = None) -> Filter:
    must: List[FieldCondition] = [FieldCondition(key=TENANT_PAYLOAD_KEY, match=MatchValue(value=group_id))]
    if extra_must:
        must.extend(extra_must)
    return Filter(must=must)


def _record_to_point(record: QdrantRecord, *, model: str, group_id: str) -> PointStruct:
    payload = {
        TENANT_PAYLOAD_KEY: group_id,
        "uniqueid": record.uniqueid,
        "title": record.title,
        "content": record.content,
        "dateCreated": record.dateCreated,
        "dateModified": record.dateModified,
        "source": record.source,
        "link": record.link,
        "relatedItems": record.relatedItems,
        "parentId": record.parentId,
        "fileUrl": record.fileUrl,
    }
    return PointStruct(
        id=record.uniqueid,
        payload=payload,
        vector=Document(text=record.content, model=model),  # cloud inference embedding
    )


def upsert_records(
    client: QdrantClient,
    *,
    collection_name: str,
    records: Sequence[QdrantRecord],
    group_id: str,
    model: str = DEFAULT_MODEL,
) -> None:
    points = [_record_to_point(r, model=model, group_id=group_id) for r in records]
    client.upsert(collection_name=collection_name, points=points)


def search_by_vector(
    client: QdrantClient,
    *,
    collection_name: str,
    query_text: str,
    group_id: str,
    model: str = DEFAULT_MODEL,
    limit: int = 10,
):
    return client.query_points(
        collection_name=collection_name,
        query=Document(text=query_text, model=model),  # cloud inference embedding
        query_filter=_tenant_filter(group_id),
        limit=limit,
        with_payload=True,
    )


if __name__ == "__main__":
    # Setup client
    client = get_qdrant_client()

    # Collection and tenant
    collection = "tutils_test_records"
    group_id = "demo-tenant-1"

    # Ensure collection exists with our current config
    ensure_collection(
        client,
        collection_name=collection,
        vector_size=384,
        distance=Distance.COSINE,
        create_text_indexes=True,
    )

    # Upsert (this is the call that triggers the error we’re debugging)
    records = [
        QdrantRecord.new(
            title="Chocolate chip cookies",
            content="Recipe for baking chocolate chip cookies requires flour, sugar, eggs, and chocolate chips.",
            source="unit-test",
        )
    ]
    upsert_records(
        client,
        collection_name=collection,
        records=records,
        group_id=group_id,
        model=DEFAULT_MODEL,
    )

    # Query (current flow we use)
    import time
    
    times = []
    for i in range(20):
        start_time = time.time()
        result = search_by_vector(
            client,
            collection_name=collection,
            query_text="Recipe for baking chocolate chip cookies requires flour",
            group_id=group_id,
            model=DEFAULT_MODEL,
            limit=5,
        )
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        times.append(duration_ms)
        print(f"Query {i+1}: {duration_ms:.2f} ms")
    
    average_time = sum(times) / len(times)
    print(f"\nAverage time over 20 queries: {average_time:.2f} ms")
    print(result)