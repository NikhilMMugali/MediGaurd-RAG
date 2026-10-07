"""Qdrant wrapper (docs/RAG_DESIGN.md "vector DB internals"). Defaults to
qdrant-client's embedded on-disk mode (QDRANT_MODE=local) so the prototype
needs no separate Qdrant server process; set QDRANT_MODE=server + QDRANT_URL
to point at a real Qdrant instance instead — nothing else in this file
changes.

One unified collection holds every knowledge chunk (Synthea-derived and
PDF-derived alike) with a metadata payload. Authorization is enforced by
passing a qdrant_client.models.Filter into search() itself — the filter is
built by app.authorization.context before this module is ever called, so a
restricted point is excluded by Qdrant and never reaches the caller.
"""
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from app.config import get_settings

PAYLOAD_INDEX_FIELDS = [
    "patient_id",
    "record_type",
    "department_id",
    "ward_id",
    "sensitivity",
    "source_type",
    "allowed_roles",
    "source_document_id",
]


class VectorStore:
    def __init__(self, client: QdrantClient, collection: str):
        self.client = client
        self.collection = collection

    def ensure_collection(self, dimension: int) -> None:
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection in existing:
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )
        for field in PAYLOAD_INDEX_FIELDS:
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field,
                field_schema="keyword",
            )

    def upsert(self, points: list[PointStruct]) -> None:
        self.client.upsert(collection_name=self.collection, points=points)

    def count(self) -> int:
        return self.client.count(collection_name=self.collection).count

    def search(self, vector: list[float], query_filter: Filter | None, limit: int, score_threshold: float) -> list[ScoredPoint]:
        return self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold or None,
        )


def match_value_or_any(field: str, values: list[str]) -> FieldCondition:
    if len(values) == 1:
        return FieldCondition(key=field, match=MatchValue(value=values[0]))
    return FieldCondition(key=field, match=MatchAny(any=values))


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.qdrant_mode == "local":
        client = QdrantClient(path=settings.qdrant_path)
    else:
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    return VectorStore(client, settings.qdrant_collection)
