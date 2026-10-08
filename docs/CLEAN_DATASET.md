# The MediGaurd clean dataset

MediGaurd's demo data is a deterministic, 100-patient subset of the
standard Synthea sample population, built by
[`scripts/build_clean_dataset.py`](../scripts/build_clean_dataset.py) and
checked by
[`scripts/validate_clean_dataset.py`](../scripts/validate_clean_dataset.py).

## Where the data came from

The source is `synthea_sample_data_csv_latest`, a public, openly-licensed
**synthetic** patient population generator's output — no real patient,
provider, or claim was ever involved. It is preserved unmodified at
`data/raw/synthea_original/` (gitignored — large and regeneratable, not
committed). `data/clean/` is the narrowed, demo-safe dataset the
application actually imports (`SYNTHEA_CSV_DIR` in `.env`), and *is*
committed — it's small, fully synthetic, and worth judges being able to
read directly.

## What changed, and why

| Step | What | Why |
|---|---|---|
| Patient selection | Exactly 100 patients, the first 100 by Synthea `Id` sorted ascending | A fixed, reproducible demo size — running the build script twice selects the identical 100 patients |
| Clean display ids | Each selected patient gets `P001..P100` (`Patient.display_id`) | The UI shows this, never the raw Synthea UUID. The UUID (`Patient.id`) is kept as the real internal id every other table's foreign key already points to — nothing else in the schema needed to change |
| Synthetic names | `FIRST`/`LAST` overwritten with a fixed, fictional name pair per patient (no RNG — direct index into two 100-entry name lists) | Synthea's own generated names carry odd numeric suffixes (`Shawn331 Turcotte157`) that look like a bug in a demo. The replacement names are entirely fictional — not drawn from, or resembling, any real/public person |
| Sensitive identifiers dropped | `SSN`, `DRIVERS`, `PASSPORT` blanked in `data/clean/patients.csv` | Never read by the application or the RAG layer; blanked anyway so the "demo-safe" dataset never carries them at all |
| Referential filtering | Every patient-linked table (`encounters`, `conditions`, `medications`, `observations`, `allergies`, `procedures`, `careplans`, `immunizations`, `imaging_studies`, `devices`, `claims`, `claims_transactions`, `payer_transitions`) filtered to just the 100 selected patients | A clean, self-consistent 100-patient population — no dangling references to a patient outside the set |
| Shared reference data | `organizations.csv`, `providers.csv`, `payers.csv` copied through unfiltered | Small (278/278/10 rows) and referenced by many patients' encounters/claims — filtering them would risk a dangling FK for no real size benefit |
| Deduplication | Natural-key dedup per table (e.g. observations: patient+code+date+value) — never on description alone, since two real blood-pressure readings can share one on different dates | Synthea's export had a handful of exact-duplicate rows (20 total across medications/observations) |
| `supplies.csv` dropped | Not carried into `data/clean/` at all | Not modeled into the app's knowledge/authorization layer and not part of the required domain list — kept out rather than imported unused |

## Observation filtering (the biggest quality lever)

`observations.csv` mixes genuinely clinical readings with Synthea's own
`CATEGORY` field already distinguishing:

- `vital-signs`, `laboratory`, `exam`, `imaging`, `procedure`, `therapy` — clinically useful
- `survey`, `social-history` — socioeconomic questionnaire answers (e.g. "are you afraid of your partner", "household size")
- *(uncategorized)* — administrative scoring (Synthea's own QALY/DALY rows)

**All of these stay in `data/clean/observations.csv` and the structured
database** — a Finance or Reception question never needs them, but a
direct SQL lookup for "household size" (if ever asked) still has the row.
**Only the RAG knowledge/vector layer excludes the non-clinical categories**
(`scripts/generate_knowledge_records.py`'s observation filter) — a bare
"recent observations" question from a clinical role now surfaces vitals
and labs, not an unrelated survey answer that happened to score high on
cosine similarity. This cut the observation knowledge-record count from
64,888 raw rows to 40,234 indexed ones for the 100-patient set.

## Identifier mapping

```
patient_id (display, UI-facing)   =  P001
source_patient_id (internal, DB)  =  the original Synthea UUID (Patient.id)
```

The mapping lives in one column (`patients.display_id`) rather than a
separate table — every other table's `patient`/`patient_id` FK already
points at the Synthea UUID and was never touched, so referential integrity
needed zero remapping. `app.rag.pipeline.resolve_patient_reference()` is
the one place that turns a UI-facing `Pxxx` (or a pasted raw UUID, for
back-compat) back into the internal id before any authorization check or
retrieval runs.

A patient introduced later via an uploaded PDF (not part of the 100) gets
`external_patient_id` set instead (pre-existing mechanism) and no
`display_id` — the API falls back to showing its internal id until/unless
it's assigned one.

## Validation

```
python scripts/validate_clean_dataset.py
```

Checks: exactly 100 patients, no duplicate patient/display ids, no
dangling patient references in any linked table, no `SSN`/`DRIVERS`/
`PASSPORT` values present, and every date column parses.

## Rebuilding

```
cd backend  # .env is resolved relative to cwd — must run from here
python ../scripts/build_clean_dataset.py      # data/raw -> data/clean
python ../scripts/validate_clean_dataset.py
python ../scripts/import_synthea.py           # data/clean -> fresh DB (point DATABASE_URL at an empty file first)
python ../scripts/seed_users.py
python ../scripts/seed_authorization_data.py
python ../scripts/generate_knowledge_records.py
python ../scripts/index_knowledge.py          # clear data/qdrant first for a true from-scratch reindex
```

Every step is idempotent (skips a table/collection that already has data),
so re-running after a partial failure is always safe — it only ever
re-does the step that didn't finish.
