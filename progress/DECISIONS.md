# MediGaurd RAG — Decisions Log

Record of non-obvious implementation choices, in case a later session needs the "why."

## 2026-10-08 — Python 3.12 instead of 3.14 for the backend virtualenv
The machine's default `python3` is 3.14, but `psycopg2-binary` and several ML packages had no prebuilt wheel for it yet, causing source builds to fail (missing `pg_config`, etc.). Switched to the already-installed Python 3.12 interpreter, which installed every dependency cleanly from wheels. If 3.14 wheel coverage improves later, this can be revisited, but there's no functional reason to chase the newest interpreter here.

## 2026-10-08 — psycopg3 instead of psycopg2
Following from the above: rather than fight `psycopg2-binary`'s build requirements, switched the SQLAlchemy URL scheme to `postgresql+psycopg` and the dependency to `psycopg[binary]==3.2.3`, which ships wheels for 3.12. No behavioral difference for this project's usage.

## 2026-10-08 — bcrypt pinned to 4.0.1
`passlib==1.7.4` reads `bcrypt.__about__.__version__`, which was removed in `bcrypt>=4.1`. Without the pin, every password hash/verify call raised `ValueError: password cannot be longer than 72 bytes` (a misleading downstream symptom of the version-detection failure, not an actual length issue). Pinning `bcrypt==4.0.1` restores compatibility. Revisit if upgrading passlib later.

## 2026-10-08 — SQLite `StaticPool` for Phase 1 tests
`sqlite:///:memory:` without `StaticPool` gives each connection checkout a fresh, empty in-memory database under SQLAlchemy's default pooling, so tables created in one connection are invisible to the next ("no such table" errors). `StaticPool` forces a single shared connection for the test engine, which fixes this without requiring a real PostgreSQL instance just to run Phase 1 tests.

## 2026-10-08 — Role verified against the database on every authenticated request, not just at login
A JWT's `role` claim is treated as a convenience cache, not a trust boundary: `get_current_user` re-reads the user's role from PostgreSQL on every request and rejects if it no longer matches the token. This means a role downgrade takes effect immediately without waiting for token expiry, and a forged/stale token claiming a role the account no longer has is rejected. Chosen because the spec's central rule is that authorization must never be decided from client-supplied or client-cached state.

## 2026-10-08 — Upload endpoint restricted to DOCTOR/NURSE/ADMIN
The original spec says "an authorized user" can upload without naming exact roles for this action. Interpreted conservatively: FINANCE and RECEPTION (who have no clinical access) should not be able to introduce new clinical documents. Revisit if the hackathon demo needs a different uploader role (e.g. a dedicated records-clerk role) — currently ADMIN covers that gap.

## 2026-10-08 — SQLite used for local Phase 2 development instead of PostgreSQL
Neither Docker nor a prebuilt PostgreSQL were available on this machine; `brew install postgresql@16` fell back to compiling from source (no bottle for this host), pulling in a from-source `cmake` build that was still running after 30+ minutes. Per the Phase 2 "speed rule" (development speed matters, fix blockers and continue), local development/demo uses `sqlite:///.../medigaurd_dev.db` for now. This is a configuration choice only: every model, the importer, the knowledge-record generator, and the Alembic migration are plain SQLAlchemy with no Postgres-specific types or SQL, so pointing `DATABASE_URL` at a real PostgreSQL instance (`docker compose up -d postgres`, or once the brew build finishes) requires zero code changes — just re-run `alembic upgrade head` + `scripts/import_synthea.py` against the new URL. Revisit once Postgres is actually available locally and re-verify the acceptance tests against it before the final demo.

## 2026-10-08 — Surrogate UUID primary keys for Synthea tables with no native id
`conditions`, `medications`, `observations`, `allergies`, `procedures`, `immunizations`, `devices`, `supplies`, and `payer_transitions` have no `Id` column in their CSVs. `imaging_studies.csv` *has* an `Id` column, but it repeats across multiple series/instance rows belonging to one study (confirmed by a real `UNIQUE constraint failed` during import) — so it was remapped to a `study_id` column and given its own surrogate `id`. Every other Synthea table keeps its original `Id` as the primary key unchanged, so relationships never need remapping.

## 2026-10-08 — CSV → model column mapping is a blanket lowercase, not a per-table dictionary
Every verified Synthea CSV header lowercases directly onto a model attribute name (e.g. `STATE_HEADQUARTERED` → `state_headquartered`), confirmed by inspecting every header against the models before writing the importer. This kept `scripts/import_synthea.py` to one generic coercion loop keyed off each model's own SQLAlchemy column types (Date/DateTime/Float/Integer) instead of 18 hand-written per-table mappers. `COLUMN_OVERRIDES` exists for the one exception (`imaging_studies`'s `Id` → `study_id`, see above) — add to that dict rather than special-casing the loop if another exception turns up.

## 2026-10-08 — PDF → DB mapping uses a rule-based "Label: Value" line parser, not an LLM call
Phase 2's scope is "extract → normalize → validate → store → provenance," not full RAG. A regex-based scan for lines like `Diagnosis: Hypertension` is fast, free, deterministic, and fully testable, and matches the sample document format used throughout the spec. `app/ingestion/pdf_mapper.py::extract_patient_document_data` is the single seam to replace with an LLM-based or ML-based extractor later without touching `map_to_database` or the upload API.
