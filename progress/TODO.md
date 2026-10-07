# MediGaurd RAG — TODO

## Immediate (Phase 2 kickoff)
- [ ] Add `docker-compose.yml` services for PostgreSQL + Qdrant (compose file scaffolded at repo root; verify `docker compose up` works end-to-end)
- [ ] Write SQLAlchemy models for all 18 Synthea tables with provenance columns
- [ ] Write `scripts/import_synthea.py` (CSV → PostgreSQL, idempotent re-run)
- [ ] Add Alembic and generate the first migration
- [ ] Add `wards`, `patient_assignments`, `user_departments`, `document_acls`, `audit_logs`, `ingestion_jobs` tables
- [ ] Seed deterministic ward/patient assignments using real imported patient ids (no fabricated ids)
- [ ] Update `scripts/seed_users.py` to run against real PostgreSQL once it's standard, not just SQLite-in-tests

## Phase 2 — PDF → schema mapping
- [ ] Define the intermediate extraction JSON schema in Pydantic (`patient`, `encounters`, `conditions`, `medications`, ... per docs/DATA_FLOW.md)
- [ ] Section/heading detection on top of the existing PyMuPDF page extraction
- [ ] LLM- or rule-based structured field extraction from section text
- [ ] Validation layer rejecting ungrounded/hallucinated fields (missing → null, never guessed)
- [ ] New-patient dedup logic (identifier + name + DOB comparison, flag ambiguous matches)

## Phase 3 — RAG
- [ ] `EmbeddingProvider` abstraction + sentence-transformers implementation
- [ ] `VectorStore` abstraction + Qdrant implementation (collection create, payload index, filtered search)
- [ ] Schema-aware + narrative chunking (see docs/DATA_FLOW.md chunking levels)
- [ ] `AuthorizationContext` builder from PostgreSQL state
- [ ] Qdrant filter builder from `AuthorizationContext`
- [ ] `LLMProvider` abstraction (Groq default; Gemini/OpenAI alternates)
- [ ] `/api/rag/query` endpoint
- [ ] Citation validator
- [ ] `audit_logs` writes on every query
- [ ] Admin debug endpoint/view
- [ ] Frontend: login page, dashboard/chat, upload UI, admin view
- [ ] Ten acceptance tests from docs/PROJECT_REQUIREMENTS.md passing end-to-end

## Housekeeping
- [ ] First git commit of the Phase 1 scaffold + docs
- [ ] Push to https://github.com/NikhilMMugali/MediGaurd-RAG-.git once the user confirms the remote
