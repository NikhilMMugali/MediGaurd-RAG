"""One-off backfill for knowledge_records.record_date / observation_category
on rows created before those columns existed (docs/DECISIONS.md "RAG quality
fix"). Uses a single correlated UPDATE per record_type — not a 176k-row
Python loop — so it runs in seconds, not hours.

Safe to re-run: every UPDATE is unconditional on the already-correct value,
so re-running just re-derives the same result.

Usage:
    python scripts/backfill_knowledge_metadata.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402

# (record_type, source table, source date column, correlation column)
DATE_BACKFILLS = [
    ("condition", "conditions", "start"),
    ("medication", "medications", "start"),
    ("observation", "observations", "date"),
    ("encounter", "encounters", "start"),
    ("claim", "claims", "servicedate"),
    ("claim_transaction", "claims_transactions", "fromdate"),
]


def main() -> None:
    db = SessionLocal()
    try:
        for record_type, table, date_col in DATE_BACKFILLS:
            result = db.execute(
                text(
                    f"""
                    UPDATE knowledge_records
                    SET record_date = (
                        SELECT {date_col} FROM {table} WHERE {table}.id = knowledge_records.record_id
                    )
                    WHERE knowledge_records.record_type = :record_type
                    """
                ),
                {"record_type": record_type},
            )
            print(f"record_date  {record_type}: {result.rowcount} rows")

        result = db.execute(
            text(
                """
                UPDATE knowledge_records
                SET observation_category = (
                    SELECT category FROM observations WHERE observations.id = knowledge_records.record_id
                )
                WHERE knowledge_records.record_type = 'observation'
                """
            )
        )
        print(f"observation_category: {result.rowcount} rows")

        db.commit()
        print("Backfill complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
