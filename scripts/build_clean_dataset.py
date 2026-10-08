"""Build the deterministic, demo-safe MediGaurd dataset from the raw
Synthea export (docs/CLEAN_DATASET.md).

    data/raw/synthea_original/*.csv  -->  data/clean/*.csv

Steps (all deterministic — no RNG, no wall-clock dependency, so running
this twice produces byte-identical output):

  1. Select exactly 100 patients (the first 100 by Synthea Id, sorted).
  2. Assign each a clean demo-facing id ("P001".."P100") and a fully
     fictional name — the real Synthea id is kept as the row's own `Id`
     (every other table's patient FK is untouched), so referential
     integrity never needs remapping; only a cosmetic display_id column is
     added to patients.csv.
  3. Filter every patient-linked table down to just those 100 patients'
     rows, deduplicating on each table's natural key.
  4. Blank SSN/DRIVERS/PASSPORT (never needed by the app or the RAG layer,
     dropped for demo safety per docs/CLEAN_DATASET.md).
  5. organizations.csv/providers.csv/payers.csv are copied through
     unfiltered — tiny reference tables shared across all patients, so
     filtering them would risk a dangling FK for no real size benefit.

This narrows the *active* dataset; it never touches or deletes
data/raw/synthea_original.

Usage:
    python scripts/build_clean_dataset.py
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "synthea_original"
CLEAN_DIR = ROOT / "data" / "clean"

PATIENT_COUNT = 100

# Deterministic, fully fictional name pairs — no real/public person. Sized
# to exactly PATIENT_COUNT so each of the 100 selected patients gets a
# unique (first, last) pairing by plain index, no randomness involved.
FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Rohan", "Kabir", "Dhruv", "Arnav", "Yash", "Aryan", "Shaurya", "Advik", "Rudra", "Veer",
    "Aanya", "Ananya", "Diya", "Isha", "Kiara", "Myra", "Navya", "Pari", "Riya", "Saanvi",
    "Sara", "Siya", "Tara", "Zara", "Anika", "Avni", "Ira", "Kavya", "Meera", "Neha",
    "Liam", "Noah", "Oliver", "Elijah", "James", "William", "Benjamin", "Lucas", "Henry", "Owen",
    "Emma", "Olivia", "Ava", "Sophia", "Isabella", "Mia", "Charlotte", "Amelia", "Harper", "Evelyn",
    "Mateo", "Santiago", "Sebastian", "Leonardo", "Diego", "Mariana", "Valentina", "Camila", "Lucia", "Elena",
    "Yusuf", "Omar", "Hamza", "Zainab", "Amara", "Layla", "Fatima", "Noor", "Sana", "Imran",
    "Wei", "Ming", "Jun", "Hiroshi", "Kenji", "Yuki", "Haruto", "Sakura", "Aiko", "Mei",
    "Daniel", "Matthew", "Andrew", "Joseph", "David", "Grace", "Chloe", "Victoria", "Natalie", "Lily",
]
LAST_NAMES = [
    "Shah", "Patel", "Mehta", "Sharma", "Verma", "Gupta", "Kapoor", "Nair", "Rao", "Iyer",
    "Reddy", "Singh", "Kumar", "Bose", "Chatterjee", "Desai", "Joshi", "Kulkarni", "Malhotra", "Pillai",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Garcia", "Wilson", "Anderson",
    "Taylor", "Thomas", "Moore", "Martin", "Jackson", "White", "Harris", "Clark", "Lewis", "Walker",
    "Hall", "Allen", "Young", "King", "Wright", "Scott", "Green", "Baker", "Adams", "Nelson",
    "Hill", "Campbell", "Mitchell", "Carter", "Roberts", "Gomez", "Flores", "Morales", "Ortiz", "Reyes",
    "Cruz", "Romero", "Chavez", "Ramirez", "Torres", "Rivera", "Diaz", "Fernandez", "Silva", "Costa",
    "Khan", "Ahmed", "Hussain", "Ali", "Malik", "Farooq", "Siddiqui", "Rashid", "Haider", "Qureshi",
    "Tanaka", "Suzuki", "Sato", "Watanabe", "Ito", "Yamamoto", "Nakamura", "Kobayashi", "Kato", "Yoshida",
    "Murphy", "Cooper", "Richardson", "Cox", "Ward", "Bennett", "Gray", "James", "Foster", "Simmons",
]
assert len(FIRST_NAMES) == PATIENT_COUNT and len(LAST_NAMES) == PATIENT_COUNT

# (file name, patient-id column). Everything else is copied unfiltered.
PATIENT_FILTERED_FILES = [
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
# Shared reference data every patient's records point into — small, and
# filtering them risks a dangling FK for no real size benefit.
COPY_UNFILTERED_FILES = ["organizations.csv", "providers.csv", "payers.csv"]

# Natural key per file for deduplication (section 12: never dedupe on
# description alone — two real blood-pressure readings can share a
# description on different dates).
NATURAL_KEYS: dict[str, list[str]] = {
    "encounters.csv": ["Id"],
    "conditions.csv": ["PATIENT", "CODE", "START"],
    "medications.csv": ["PATIENT", "CODE", "START"],
    "observations.csv": ["PATIENT", "CODE", "DATE", "VALUE"],
    "allergies.csv": ["PATIENT", "CODE", "START"],
    "procedures.csv": ["PATIENT", "CODE", "START"],
    "careplans.csv": ["Id"],
    "immunizations.csv": ["PATIENT", "CODE", "DATE"],
    "imaging_studies.csv": ["Id", "SERIES_UID", "INSTANCE_UID"],
    "devices.csv": ["PATIENT", "CODE", "START"],
    "claims.csv": ["Id"],
    "claims_transactions.csv": ["ID"],
    "payer_transitions.csv": ["PATIENT", "PAYER", "START_DATE"],
}


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return reader.fieldnames or [], rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def dedupe(rows: list[dict], key_cols: list[str]) -> list[dict]:
    seen: set[tuple] = set()
    out = []
    for row in rows:
        key = tuple(row.get(c, "") for c in key_cols)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def build_patients() -> dict[str, str]:
    """Returns {synthea_id: display_id} for the selected 100 patients."""
    fieldnames, rows = read_csv(RAW_DIR / "patients.csv")
    rows.sort(key=lambda r: r["Id"])
    selected = rows[:PATIENT_COUNT]

    id_to_display: dict[str, str] = {}
    out_fieldnames = fieldnames + ["DISPLAY_ID"]
    out_rows = []
    for i, row in enumerate(selected):
        display_id = f"P{i + 1:03d}"
        id_to_display[row["Id"]] = display_id

        clean_row = dict(row)
        clean_row["FIRST"] = FIRST_NAMES[i]
        clean_row["LAST"] = LAST_NAMES[i]
        clean_row["MIDDLE"] = ""
        clean_row["MAIDEN"] = ""
        # Never needed by the app or the RAG layer — dropped for demo
        # safety (docs/CLEAN_DATASET.md "identifiers excluded").
        clean_row["SSN"] = ""
        clean_row["DRIVERS"] = ""
        clean_row["PASSPORT"] = ""
        clean_row["DISPLAY_ID"] = display_id
        out_rows.append(clean_row)

    write_csv(CLEAN_DIR / "patients.csv", out_fieldnames, out_rows)
    print(f"OK    patients.csv: {len(out_rows)} patients (P001..P{len(out_rows):03d})")
    return id_to_display


def build_patient_filtered(file_name: str, patient_col: str, valid_ids: set[str]) -> None:
    src = RAW_DIR / file_name
    if not src.exists():
        print(f"SKIP  {file_name}: not found in raw dataset")
        return
    fieldnames, rows = read_csv(src)
    filtered = [r for r in rows if r.get(patient_col) in valid_ids]
    key_cols = NATURAL_KEYS.get(file_name, fieldnames)
    deduped = dedupe(filtered, key_cols)
    write_csv(CLEAN_DIR / file_name, fieldnames, deduped)
    dropped_dupes = len(filtered) - len(deduped)
    print(f"OK    {file_name}: {len(deduped)} rows ({len(rows)} raw, {dropped_dupes} duplicates removed)")


def copy_unfiltered(file_name: str) -> None:
    src = RAW_DIR / file_name
    if not src.exists():
        print(f"SKIP  {file_name}: not found in raw dataset")
        return
    fieldnames, rows = read_csv(src)
    write_csv(CLEAN_DIR / file_name, fieldnames, rows)
    print(f"OK    {file_name}: {len(rows)} rows (copied unfiltered — shared reference data)")


def main() -> None:
    if not RAW_DIR.exists():
        print(f"Raw Synthea data not found at {RAW_DIR}", file=sys.stderr)
        sys.exit(1)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    id_to_display = build_patients()
    valid_ids = set(id_to_display.keys())

    for file_name, patient_col in PATIENT_FILTERED_FILES:
        build_patient_filtered(file_name, patient_col, valid_ids)

    for file_name in COPY_UNFILTERED_FILES:
        copy_unfiltered(file_name)

    print(f"\nClean dataset built at {CLEAN_DIR} — {len(valid_ids)} patients.")


if __name__ == "__main__":
    main()
