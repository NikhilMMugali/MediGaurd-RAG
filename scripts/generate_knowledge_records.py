"""Generate knowledge_records from the already-imported structured tables
(docs/DATA_FLOW.md step 11). Covers the record types demonstrated in the
acceptance tests: conditions, medications, observations, encounters, claims,
claim transactions. Idempotent: skips a record type that already has rows.

Usage:
    python scripts/generate_knowledge_records.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app.models  # noqa: E402,F401
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models.documents import KnowledgeRecord  # noqa: E402
from app.models.hospital import Allergy, Claim, ClaimTransaction, Condition, Encounter, Medication, Observation, Procedure  # noqa: E402
from app.models.provenance import new_uuid  # noqa: E402
from app.services import knowledge_generator as kg  # noqa: E402

# Observation categories worth indexing for semantic retrieval (vitals,
# labs, and clinical exam/imaging/procedure findings). survey/social-history
# rows and uncategorized administrative ones (e.g. Synthea's QALY scoring)
# are excluded from the RAG knowledge layer — they are still fully present
# in the structured `observations` table for direct DB queries, just not
# indexed as semantic knowledge (docs/CLEAN_DATASET.md, progress/DECISIONS.md
# "RAG quality fix").
CLINICAL_OBSERVATION_CATEGORIES = ["vital-signs", "laboratory", "exam", "imaging", "procedure", "therapy"]

GENERATORS = [
    ("condition", Condition, kg.from_condition, None),
    ("medication", Medication, kg.from_medication, None),
    ("observation", Observation, kg.from_observation, Observation.category.in_(CLINICAL_OBSERVATION_CATEGORIES)),
    ("allergy", Allergy, kg.from_allergy, None),
    ("procedure", Procedure, kg.from_procedure, None),
    ("encounter", Encounter, kg.from_encounter, None),
    ("claim", Claim, kg.from_claim, None),
    ("claim_transaction", ClaimTransaction, kg.from_claim_transaction, None),
]

BATCH_SIZE = 2000


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        total = 0
        for record_type, model, generator, extra_filter in GENERATORS:
            existing = db.query(KnowledgeRecord).filter(KnowledgeRecord.record_type == record_type).first()
            if existing is not None:
                print(f"SKIP  {record_type}: already has knowledge records")
                continue

            query = db.query(model)
            if extra_filter is not None:
                query = query.filter(extra_filter)

            count = 0
            batch: list[dict] = []
            for row in query.yield_per(BATCH_SIZE):
                record = generator(row)
                record["id"] = new_uuid()
                batch.append(record)
                if len(batch) >= BATCH_SIZE:
                    db.bulk_insert_mappings(KnowledgeRecord, batch)
                    count += len(batch)
                    batch = []
            if batch:
                db.bulk_insert_mappings(KnowledgeRecord, batch)
                count += len(batch)

            db.commit()
            total += count
            print(f"OK    {record_type}: {count} knowledge records")

        print(f"\nKnowledge record generation complete. {total} records created.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
