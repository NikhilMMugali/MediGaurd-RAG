# MediGaurd RAG Progress

## Current Phase
Phase 2 — Database (complete for its scope) → starting Phase 3 — RAG

## Overall Status
IN PROGRESS

## Phase 1 — Backend
- [x] Project scaffold
- [x] FastAPI
- [x] Configuration
- [x] Authentication
- [x] Password hashing
- [x] Role validation (server-side role must match client-selected role)
- [x] User APIs (`/api/auth/login`, `/api/auth/me`)
- [x] PDF upload API
- [x] PDF extraction (PyMuPDF)
- [x] Backend tests (9 passing)

## Phase 2 — Database
- [x] PostgreSQL-compatible schema (SQLAlchemy, dialect-agnostic; see Known Issues for current local DB)
- [x] Schema: all 18 Synthea tables + `users`/`departments`/`wards`/`patient_assignments`/`user_departments`/`document_acls`/`source_documents`/`knowledge_records`/`document_chunks`/`ingestion_jobs`/`audit_logs` (29 tables total)
- [x] Alembic migrations (initial migration generated and verified against a blank DB)
- [x] Synthea import (`scripts/import_synthea.py`) — idempotent, all 18 files
- [x] Authorization tables seeded (`scripts/seed_authorization_data.py`: departments, wards, deterministic patient assignments against real imported patient ids)
- [x] PDF normalization foundation (`app/ingestion/pdf_mapper.py`: intermediate schema + rule-based section extraction + DB mapping, wired into `/api/documents/upload`)
- [x] Provenance (`source_type`/`source_document_id`/`created_at`/`updated_at` on every Synthea-derived table; new-patient dedup via `external_patient_id`)
- [x] Knowledge record generation (`scripts/generate_knowledge_records.py`: conditions/medications/observations/encounters/claims/claim_transactions → `knowledge_records`)
- [x] New Phase 2 API endpoints: `GET /api/health/database`, `GET /api/patients/{id}/summary`, `GET /api/admin/database/stats`, `GET /api/admin/ingestion/{job_id}`
- [x] Backend tests updated/added for Phase 2 upload behavior (11 passing total)

## Phase 2 Verification
- PostgreSQL-dialect connection via SQLAlchemy: PASS (code is Postgres-ready; see Known Issues for what actually ran locally)
- Synthea import: PASS — row counts match the documented inventory exactly (108 patients, 5571 encounters, 3517 conditions, 3850 medications, 68648 observations, 105 allergies, 15884 procedures, 349 careplans, 1549 immunizations, 478 imaging studies, 524 devices, 2225 supplies, 9421 claims, 85047 claims_transactions, 3815 payer_transitions, 10 payers, 278 providers, 278 organizations)
- Re-running the importer is idempotent (verified: second run skips every table)
- Sample patient query: PASS (`GET /api/patients/{id}/summary` returns real condition/medication/encounter counts)
- Sample claim query: PASS (verified directly against the DB: claim row resolves for a real patient)
- Authorization metadata: PASS (7 departments, 4 wards, 10 deterministic patient_assignments across doctor01/nurse01 against real patient ids)
- PDF → DB mapping: PASS (new test `test_upload_maps_new_patient_into_database`: uploading a labeled PDF creates a `Patient` + `Condition` + `Medication` + `Allergy`, each carrying `source_document_id` provenance back to the upload)
- Duplicate-upload rejection: PASS (`test_upload_rejects_duplicate_file`: same file hash twice → 409)
- Role-gating on new endpoints: PASS (verified live: `finance01` gets 403 from `/api/admin/database/stats`; `admin01` gets 200)

## Latest Completed Work
Implemented the full Phase 2 database foundation: 18 Synthea-matching SQLAlchemy models plus the application/authorization/knowledge tables (29 total), an idempotent CSV importer verified against the exact documented row counts, Alembic migrations (initial revision verified against a blank DB), a knowledge-record generator producing 176,054 RAG-ready text records from the structured data, and authorization seeding (departments/wards/patient_assignments using real patient ids). Extended the Phase 1 upload endpoint (without rewriting its extraction logic) to map uploaded PDFs through a new rule-based intermediate schema into real, provenance-tagged database rows, with new-patient dedup and duplicate-file rejection. Added `/api/health/database`, `/api/patients/{id}/summary`, and two admin endpoints. 11 backend tests pass; the full flow was also verified live over HTTP (login → admin stats → patient summary → role-denied check).

## Latest Commit
(pending — see Next Task)

## Known Issues
- **PostgreSQL is not actually running locally yet.** Docker is unavailable on this machine, and `brew install postgresql@16` fell back to compiling dependencies (including `cmake`) from source, which was still running after 30+ minutes. Per the speed rule, Phase 2 was built and verified against SQLite (`sqlite:///.../medigaurd_dev.db`) instead of blocking on this. The schema, importer, generator, and migration are 100% dialect-agnostic SQLAlchemy — switching `DATABASE_URL` to a real PostgreSQL instance once available requires no code changes, only re-running `alembic upgrade head` and the seed/import scripts against it. **This must be done and re-verified before the final demo**, since the spec requires PostgreSQL specifically.
- The PDF → DB mapper is a rule-based "Label: Value" line parser (see `progress/DECISIONS.md`), not an LLM-based extractor. It correctly handles the sample document format used throughout the spec; a real scanned clinical PDF with free-form prose would need a smarter extractor plugged into the same seam (`extract_patient_document_data`).
- `knowledge_records` currently covers conditions/medications/observations/encounters/claims/claim_transactions. Allergies/procedures/careplans/immunizations/imaging/devices/payers are not yet generated into knowledge records — straightforward to add with the same generator pattern when Phase 3 needs them.

## Next Task
Phase 3: Qdrant vector store, embedding pipeline, chunking (page/section/schema-aware/narrative), the `AuthorizationContext` + Qdrant filter builder, the `/api/rag/query` endpoint with cited generation, and audit logging. Before that, re-point `DATABASE_URL` at a real PostgreSQL instance and re-verify Phase 2 against it.

## Last Updated
2026-10-08
