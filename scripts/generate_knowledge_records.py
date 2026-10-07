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
from app.models.hospital import Claim, ClaimTransaction, Condition, Encounter, Medication, Observation  # noqa: E402
from app.models.provenance import new_uuid  # noqa: E402
from app.services import knowledge_generator as kg  # noqa: E402

GENERATORS = [
    ("condition", Condition, kg.from_condition),
    ("medication", Medication, kg.from_medication),
    ("observation", Observation, kg.from_observation),
    ("encounter", Encounter, kg.from_encounter),
    ("claim", Claim, kg.from_claim),
    ("claim_transaction", ClaimTransaction, kg.from_claim_transaction),
]

BATCH_SIZE = 2000


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        total = 0
        for record_type, model, generator in GENERATORS:
            existing = db.query(KnowledgeRecord).filter(KnowledgeRecord.record_type == record_type).first()
            if existing is not None:
                print(f"SKIP  {record_type}: already has knowledge records")
                continue

            count = 0
            batch: list[dict] = []
            for row in db.query(model).yield_per(BATCH_SIZE):
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
