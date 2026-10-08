"""Validate data/clean/ after scripts/build_clean_dataset.py
(docs/CLEAN_DATASET.md). Run once per dataset rebuild — not after every
unrelated code change.

Usage:
    python scripts/validate_clean_dataset.py
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "data" / "clean"
EXPECTED_PATIENT_COUNT = 100

PATIENT_LINKED_FILES = [
    ("encounters.csv", "PATIENT"),
    ("conditions.csv", "PATIENT"),
    ("medications.csv", "PATIENT"),
    ("observations.csv", "PATIENT"),
    ("allergies.csv", "PATIENT"),
    ("procedures.csv", "PATIENT"),
    ("careplans.csv", "PATIENT"),
    ("immunizations.csv", "PATIENT"),
    ("imaging_studies.csv", "PATIENT"),
    ("devices.csv", "PATIENT"),
    ("claims.csv", "PATIENTID"),
    ("claims_transactions.csv", "PATIENTID"),
    ("payer_transitions.csv", "PATIENT"),
]
DATE_COLUMNS: dict[str, list[str]] = {
    "patients.csv": ["BIRTHDATE", "DEATHDATE"],
    "encounters.csv": ["START", "STOP"],
    "conditions.csv": ["START", "STOP"],
    "medications.csv": ["START", "STOP"],
    "observations.csv": ["DATE"],
    "claims.csv": ["SERVICEDATE"],
}
SENSITIVE_PATIENT_COLUMNS = ["SSN", "DRIVERS", "PASSPORT"]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_parseable_date(value: str) -> bool:
    if not value:
        return True  # blank is valid (nullable)
    text = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(text)
        return True
    except ValueError:
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False


def main() -> None:
    errors: list[str] = []

    patients = read_csv(CLEAN_DIR / "patients.csv")
    if len(patients) != EXPECTED_PATIENT_COUNT:
        errors.append(f"Expected exactly {EXPECTED_PATIENT_COUNT} patients, found {len(patients)}")

    patient_ids = [p["Id"] for p in patients]
    if len(patient_ids) != len(set(patient_ids)):
        errors.append("Duplicate patient Id values in patients.csv")

    display_ids = [p["DISPLAY_ID"] for p in patients]
    if len(display_ids) != len(set(display_ids)):
        errors.append("Duplicate DISPLAY_ID values in patients.csv")
    expected_display_ids = {f"P{i + 1:03d}" for i in range(EXPECTED_PATIENT_COUNT)}
    if set(display_ids) != expected_display_ids:
        errors.append("DISPLAY_ID values do not match the expected P001..P100 sequence")

    for col in SENSITIVE_PATIENT_COLUMNS:
        if any(p.get(col) for p in patients):
            errors.append(f"patients.csv still contains values in sensitive column {col}")

    valid_patient_ids = set(patient_ids)
    for file_name, patient_col in PATIENT_LINKED_FILES:
        path = CLEAN_DIR / file_name
        if not path.exists():
            errors.append(f"{file_name} missing from data/clean/")
            continue
        rows = read_csv(path)
        dangling = [r for r in rows if r.get(patient_col) not in valid_patient_ids]
        if dangling:
            errors.append(f"{file_name}: {len(dangling)} rows reference a patient id outside the clean 100-patient set")

        # imaging_studies.csv's own Id legitimately repeats across
        # series/instance rows within one study (see DECISIONS.md "Surrogate
        # UUID primary keys" — the app keys it on its own generated id
        # instead), so it is excluded from this check.
        key_cols = [c for c in rows[0].keys() if c.lower() in ("id",)] if rows and file_name != "imaging_studies.csv" else []
        if key_cols:
            seen_ids = [r[key_cols[0]] for r in rows if r.get(key_cols[0])]
            if len(seen_ids) != len(set(seen_ids)):
                errors.append(f"{file_name}: duplicate {key_cols[0]} values")

    for file_name, columns in DATE_COLUMNS.items():
        path = CLEAN_DIR / file_name
        if not path.exists():
            continue
        rows = read_csv(path)
        for col in columns:
            bad = [r for r in rows if col in r and not is_parseable_date(r[col])]
            if bad:
                errors.append(f"{file_name}: {len(bad)} rows have an unparseable {col} value")

    if errors:
        print(f"VALIDATION FAILED ({len(errors)} issue(s)):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print(f"VALIDATION PASSED — {EXPECTED_PATIENT_COUNT} patients, all linked tables referentially sound, no sensitive identifiers, all dates parseable.")


if __name__ == "__main__":
    main()
