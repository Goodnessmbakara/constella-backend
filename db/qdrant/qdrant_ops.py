from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Document,
    FieldCondition,
    Filter,
    MatchText,
    MatchValue,
    PointIdsList,
    PointStruct,
)


from .q_client import DEFAULT_MODEL
TENANT_PAYLOAD_KEY = "group_id"


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
    must: List[FieldCondition] = [
        FieldCondition(key=TENANT_PAYLOAD_KEY, match=MatchValue(value=group_id))
    ]
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
        vector=Document(text=record.content, model=model),
    )

# 1. create (upsert)
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


# 2. update
def update_record(
    client: QdrantClient,
    *,
    collection_name: str,
    record: QdrantRecord,
    group_id: str,
    model: str = DEFAULT_MODEL,
) -> None:
    # Upsert will replace payload and vector for the point id
    point = _record_to_point(record, model=model, group_id=group_id)
    client.upsert(collection_name=collection_name, points=[point])


def update_payload(
    client: QdrantClient,
    *,
    collection_name: str,
    point_id: str,
    payload_updates: dict,
    group_id: Optional[str] = None,
) -> None:
    payload = dict(payload_updates)
    if group_id is not None:
        payload[TENANT_PAYLOAD_KEY] = group_id
    client.set_payload(collection_name=collection_name, payload=payload, points=[point_id])


# 3. delete
def delete_points_by_ids(
    client: QdrantClient,
    *,
    collection_name: str,
    point_ids: Sequence[str],
) -> None:
    client.delete(collection_name=collection_name, points_selector=PointIdsList(points=list(point_ids)))


def delete_points_by_group(
    client: QdrantClient,
    *,
    collection_name: str,
    group_id: str,
) -> None:
    client.delete(collection_name=collection_name, points_selector=_tenant_filter(group_id))


# 4. search by vector (cloud inference Document)
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
        query=Document(text=query_text, model=model),
        query_filter=_tenant_filter(group_id),
        limit=limit,
        with_payload=True,
    )


# 5. search by hybrid (vector + keyword/text) using should text matches
def search_by_hybrid(
    client: QdrantClient,
    *,
    collection_name: str,
    query_text: str,
    group_id: str,
    model: str = DEFAULT_MODEL,
    limit: int = 10,
):
    text_conditions = [
        FieldCondition(key="title", match=MatchText(text=query_text)),
        FieldCondition(key="content", match=MatchText(text=query_text)),
    ]
    return client.query_points(
        collection_name=collection_name,
        query=Document(text=query_text, model=model),
        query_filter=Filter(
            must=[FieldCondition(key=TENANT_PAYLOAD_KEY, match=MatchValue(value=group_id))],
            should=text_conditions,
        ),
        limit=limit,
        with_payload=True,
    )


__all__ = [
    "QdrantRecord",
    "get_qdrant_client",
    "ensure_collection",
    "upsert_records",
    "update_record",
    "update_payload",
    "delete_points_by_ids",
    "delete_points_by_group",
    "search_by_vector",
    "search_by_hybrid",
]


