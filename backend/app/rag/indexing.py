"""Shared embed-and-upsert logic for knowledge_records -> Qdrant, used by
both the one-off backlog script (scripts/index_knowledge.py) and the
upload endpoint's index-on-upload path (app/api/upload.py), so a new PDF's
knowledge is searchable without an app restart or a separate script run.
"""
from qdrant_client.models import PointStruct

from app.models.documents import KnowledgeRecord
from app.services.embedding_provider import EmbeddingProvider
from app.services.vector_store import VectorStore


def record_to_payload(record: KnowledgeRecord) -> dict:
    return {
        "knowledge_record_id": record.id,
        "source_type": record.source_type,
        "source_document_id": record.source_document_id,
        "source_page": record.source_page,
        "source_section": record.source_section,
        "patient_id": record.patient_id,
        "record_type": record.record_type,
        "department_id": record.department_id,
        "sensitivity": record.sensitivity,
        "content": record.content,
    }


def index_records(records: list[KnowledgeRecord], embedder: EmbeddingProvider, store: VectorStore) -> int:
    if not records:
        return 0
    store.ensure_collection(embedder.dimension)
    vectors = embedder.embed_documents([r.content for r in records])
    points = [PointStruct(id=r.id, vector=v, payload=record_to_payload(r)) for r, v in zip(records, vectors)]
    store.upsert(points)
    return len(points)
