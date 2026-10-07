# MediGaurd RAG — TODO

## Immediate (before Phase 3 starts)
- [ ] Get a real PostgreSQL running locally (retry `brew install postgresql@16` later, or install Docker) and re-point `DATABASE_URL`; re-run `alembic upgrade head`, `scripts/import_synthea.py`, `scripts/seed_authorization_data.py` against it and re-verify row counts
- [ ] First git commit of the Phase 2 scaffold (models, importer, migration, PDF mapper, new endpoints, docs)
- [ ] Push to https://github.com/NikhilMMugali/MediGaurd-RAG-.git once the user confirms the remote

## Phase 3 — RAG
- [ ] `EmbeddingProvider` abstraction + sentence-transformers implementation
- [ ] `VectorStore` abstraction + Qdrant implementation (collection create, payload index, filtered search)
- [ ] Schema-aware + narrative chunking on top of existing `knowledge_records`/`document_chunks` (see docs/DATA_FLOW.md chunking levels)
- [ ] Extend `knowledge_generator.py` to cover allergies/procedures/careplans/immunizations/imaging/devices/payers (currently: conditions/medications/observations/encounters/claims/claim_transactions)
- [ ] `AuthorizationContext` builder from PostgreSQL state (role, department, ward_ids, assigned_patient_ids, allowed_record_types/sensitivity) — `patient_assignments`/`wards`/`user_departments` tables already exist and are seeded
- [ ] Qdrant filter builder from `AuthorizationContext`
- [ ] `LLMProvider` abstraction (Groq default; Gemini/OpenAI alternates)
- [ ] `/api/rag/query` endpoint
- [ ] Citation validator
- [ ] `audit_logs` writes on every query (table already exists)
- [ ] Admin debug endpoint/view showing the authorization filter + retrieved-vs-excluded sources
- [ ] Frontend: login page, dashboard/chat, upload UI, admin view
- [ ] Ten acceptance tests from docs/PROJECT_REQUIREMENTS.md passing end-to-end

## Known gaps to revisit (not blocking, tracked in progress/DECISIONS.md and PROGRESS.md)
- [ ] Smarter PDF extraction (current mapper is a rule-based "Label: Value" line parser; fine for the spec's sample document format, not for free-form scanned prose)
- [ ] `document_acls` is modeled but not yet populated or enforced anywhere — Phase 3 retrieval-filter work
- [ ] Ambiguous new-patient matches are created as new rows rather than flagged for review (no review UI yet)

## Housekeeping
- [x] Synthea CSV import verified against documented row counts
- [x] Idempotency verified for importer and knowledge-record generator
