from __future__ import annotations

import os
import random
import string
from datetime import datetime
from typing import List
import uuid

from qdrant_client.http.models import PointStruct, Document


# When executed as a script: python db/qdrant/test_qdrant.py
from db.qdrant import (
	DEFAULT_MODEL,
	QdrantRecord,
	ensure_collection,
	get_qdrant_client,
	search_by_vector,
	upsert_records,
)


def _random_string(length: int = 12) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_mock_records(n: int) -> List[QdrantRecord]:
    records: List[QdrantRecord] = []
    now = datetime.utcnow().isoformat()
    for _ in range(n):
        records.append(
            QdrantRecord(
                uniqueid=str(uuid.uuid4()),
                title=_random_string(24),
                content=_random_string(160),
                dateCreated=now,
                dateModified=now,
                source="mock",
                link=f"https://example.com/{_random_string(8)}",
                relatedItems=[],
                parentId=None,
                fileUrl=f"https://files.example.com/{_random_string(8)}.txt",
            )
        )
    return records


def main():
    collection_name = os.getenv("QDRANT_COLLECTION", "tutils_test_records")
    group_id = os.getenv("QDRANT_TENANT", "user_1")

    client = get_qdrant_client()
    ensure_collection(client, collection_name=collection_name)

    records = generate_mock_records(500)
    upsert_records(client, collection_name=collection_name, records=records, group_id=group_id)

    # Run a vector search using cloud inference Document on the same model
    query_text = records[0].title[:20]
    results = search_by_vector(
        client,
        collection_name=collection_name,
        query_text=query_text,
        group_id=group_id,
        model=DEFAULT_MODEL,
        limit=5,
    )
    print(f"Query: {query_text}")
    print("Top results:")
    for i, r in enumerate(results, 1):
        print(f"  {i}. ID: {r.id}, Score: {r.score:.4f}")
        if hasattr(r, 'payload') and r.payload:
            title = r.payload.get('title', 'N/A')
            print(f"     Title: {title}")


if __name__ == "__main__":
    main()



