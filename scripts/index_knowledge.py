"""Embed every knowledge_records row into Qdrant (docs/DATA_FLOW.md step
12-13). Batched (EMBEDDING_BATCH_SIZE) rather than one giant embedding call,
and idempotent via Qdrant upsert on the knowledge_record's own id — re-running
this after new PDF knowledge records exist re-embeds everything currently in
the table, overwriting points with identical ids harmlessly rather than
duplicating them.

Run once after scripts/generate_knowledge_records.py. A PDF upload indexes
its own new records immediately via app/rag/indexing.py (see
app/api/upload.py) — this script is for the initial Synthea-derived backlog,
or to catch up anything that failed to index at upload time.

Usage:
    python scripts/index_knowledge.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.documents import KnowledgeRecord  # noqa: E402
from app.rag.indexing import index_records  # noqa: E402
from app.services.embedding_provider import get_embedding_provider  # noqa: E402
from app.services.vector_store import get_vector_store  # noqa: E402

settings = get_settings()


def main() -> None:
    db = SessionLocal()
    embedder = get_embedding_provider()
    store = get_vector_store()
    store.ensure_collection(embedder.dimension)

    try:
        total = db.query(KnowledgeRecord).count()
        print(f"Indexing {total} knowledge records (batch size {settings.embedding_batch_size})...")

        indexed = 0
        batch: list[KnowledgeRecord] = []
        for record in db.query(KnowledgeRecord).yield_per(settings.embedding_batch_size):
            batch.append(record)
            if len(batch) >= settings.embedding_batch_size:
                indexed += index_records(batch, embedder, store)
                print(f"  {indexed}/{total}")
                batch = []
        if batch:
            indexed += index_records(batch, embedder, store)

        print(f"Done. {indexed} points upserted. Collection count: {store.count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
