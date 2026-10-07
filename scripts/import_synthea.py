"""Import the verified Synthea CSV export into PostgreSQL.

Idempotent: a table already holding rows is skipped on re-run rather than
duplicated. Column names are matched case-insensitively against each CSV's
header, so this script assumes (and the model definitions confirm) that
every Synthea CSV header lowercases directly onto a model attribute name.

Usage:
    python scripts/import_synthea.py
"""
import csv
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import Date, DateTime, Float, Integer, insert  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402,F401  (registers all tables on Base.metadata)
from app.config import get_settings  # noqa: E402
from app.db.session import Base, engine  # noqa: E402
from app.models.hospital import (  # noqa: E402
    Allergy,
    Careplan,
    Claim,
    ClaimTransaction,
    Condition,
    Device,
    Encounter,
    ImagingStudy,
    Immunization,
    Medication,
    Observation,
    Organization,
    Patient,
    Payer,
    PayerTransition,
    Procedure,
    Provider,
    Supply,
)

settings = get_settings()

# (csv file name, model) in dependency-safe order: organizations/providers/
# payers/patients first, everything that references a patient/encounter after.
IMPORT_ORDER = [
    ("organizations.csv", Organization),
    ("providers.csv", Provider),
    ("payers.csv", Payer),
    ("patients.csv", Patient),
    ("encounters.csv", Encounter),
    ("conditions.csv", Condition),
    ("medications.csv", Medication),
    ("observations.csv", Observation),
    ("allergies.csv", Allergy),
    ("procedures.csv", Procedure),
    ("careplans.csv", Careplan),
    ("immunizations.csv", Immunization),
    ("imaging_studies.csv", ImagingStudy),
    ("devices.csv", Device),
    ("supplies.csv", Supply),
    ("claims.csv", Claim),
    ("claims_transactions.csv", ClaimTransaction),
    ("payer_transitions.csv", PayerTransition),
]

BATCH_SIZE = 2000

# Per-model overrides where a CSV column's lowercased name does not map
# directly onto the model's own primary key (imaging_studies.csv repeats its
# "Id" across series/instance rows, so it is not usable as our primary key).
COLUMN_OVERRIDES: dict[type, dict[str, str]] = {
    ImagingStudy: {"id": "study_id"},
}


def _coerce(column_type, raw: str):
    if raw == "" or raw is None:
        return None
    if isinstance(column_type, DateTime):
        # Synthea uses both bare dates and ISO-8601 with a trailing Z.
        text = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return datetime.fromisoformat(raw)
    if isinstance(column_type, Date):
        return date.fromisoformat(raw)
    if isinstance(column_type, Float):
        return float(raw)
    if isinstance(column_type, Integer):
        return int(float(raw))  # Synthea sometimes writes integers as "1.0"
    return raw


def import_file(session: Session, file_name: str, model) -> int:
    csv_path = Path(settings.synthea_csv_dir) / file_name
    if not csv_path.exists():
        print(f"SKIP  {file_name}: not found at {csv_path}")
        return 0

    existing = session.query(model).first()
    if existing is not None:
        print(f"SKIP  {model.__tablename__}: already has data")
        return 0

    columns = {c.name: c.type for c in model.__table__.columns}
    overrides = COLUMN_OVERRIDES.get(model, {})
    rows: list[dict] = []
    inserted = 0

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            row: dict = {}
            for key, value in raw_row.items():
                attr = overrides.get(key.lower(), key.lower())
                if attr not in columns:
                    continue
                row[attr] = _coerce(columns[attr], value)
            rows.append(row)

            if len(rows) >= BATCH_SIZE:
                session.execute(insert(model), rows)
                inserted += len(rows)
                rows = []

    if rows:
        session.execute(insert(model), rows)
        inserted += len(rows)

    session.commit()
    print(f"OK    {model.__tablename__}: {inserted} rows")
    return inserted


def main() -> None:
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        total = 0
        for file_name, model in IMPORT_ORDER:
            total += import_file(session, file_name, model)
        print(f"\nImport complete. {total} rows inserted across {len(IMPORT_ORDER)} tables.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
