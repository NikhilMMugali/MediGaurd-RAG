# MediGaurd RAG Progress

## Current Phase
Phase 3 — Secure RAG (backend core implemented; UI/frontend not yet started)

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
- [x] PostgreSQL-compatible schema (SQLAlchemy, dialect-agnostic; running on SQLite locally — see Known Issues)
- [x] All 18 Synthea tables + application/authorization/provenance tables (29 total)
- [x] Alembic migrations (initial migration generated and verified against a blank DB)
- [x] Synthea import (`scripts/import_synthea.py`) — idempotent, row counts verified exact
- [x] Authorization tables seeded (`scripts/seed_authorization_data.py`)
- [x] PDF normalization foundation wired into `/api/documents/upload`
- [x] Knowledge record generation (`scripts/generate_knowledge_records.py`) — 176,054 records
- [x] Phase 2 API endpoints + tests (11 passing total through Phase 2)

## Phase 3 — Secure RAG
- [x] `EmbeddingProvider` abstraction (`backend/app/services/embedding_provider.py`) — Sentence Transformers (`all-MiniLM-L6-v2`), configurable
- [x] `VectorStore` abstraction (`backend/app/services/vector_store.py`) — Qdrant, embedded local mode by default (no server process required), payload indexes, swappable to a real Qdrant server via env vars
- [x] `scripts/index_knowledge.py` — batched (200/batch), idempotent upsert of all `knowledge_records` into Qdrant
- [x] `AuthorizationContext` builder (`backend/app/authorization/context.py`) — role → allowed record types/sensitivity/patient scope, resolved from real `patient_assignments` rows, never from client input
- [x] Qdrant filter builder (`backend/app/authorization/qdrant_filter.py`) — the actual retrieval-time authorization boundary
- [x] `LLMProvider` abstraction (`backend/app/services/llm_provider.py`) — Groq/OpenAI, with a non-hallucinating extractive fallback when no API key is configured (see progress/DECISIONS.md)
- [x] `POST /api/rag/query` (`backend/app/api/rag.py`) — authenticated, cited, audit-logged; `debug` block (filter + retrieved ids) returned only to ADMIN
- [x] Hard patient-level pre-retrieval denial (a specific unassigned patient never reaches Qdrant, let alone the LLM)
- [x] `audit_logs` writes on every query (ANSWERED/DENIED/NO_AUTHORIZED_CONTEXT)
- [x] 9 new focused security tests (6 in `test_rag_authorization.py` against a real temp Qdrant collection, 3 in `test_rag_pipeline.py` including the "security invariant" test that inspects the literal text handed to the LLM)
- [ ] Reranking / hybrid lexical search (explicitly optional per spec; not implemented)
- [ ] PDF-uploaded knowledge chunks are not yet auto-indexed into Qdrant on upload (Synthea backlog is indexed via the script; wiring the upload endpoint to index-on-upload is the next concrete task)
- [ ] Frontend (login/dashboard/chat/upload/admin UI) — not started
- [ ] Admin debug *view* (the API already returns the debug block to ADMIN; there's no UI page for it yet)

## Phase 3 Verification
- Real-Qdrant filter tests: PASS (6/6) — doctor sees only assigned-patient clinical+operational records; finance sees only claims, never clinical; reception sees only encounters; admin sees everything; a doctor with zero assignments matches nothing (not "everything")
- Security invariant test: PASS — `test_finance_query_never_sends_clinical_content_to_llm` inspects the actual context string passed to the LLM provider and asserts restricted content is absent from it, not just absent from the final answer
- Patient-level hard denial: PASS — an unassigned patient reference returns `DENIED` with `retrieved_count == 0` and the LLM provider is never even invoked
- Full backend suite: 20/20 passing (11 from Phase 1/2 + 9 new Phase 3 tests)
- Live indexing of the real 176,054 knowledge records into Qdrant: STARTED (see Known Issues — running at the time of this update)

## Latest Completed Work
Implemented the Phase 3 backend core: embedding provider, Qdrant vector store (embedded local mode), the authorization-context/filter pair that is the actual retrieval-time security boundary, the LLM provider abstraction with a grounded extractive fallback, and the `/api/rag/query` endpoint with citations and audit logging. Added 9 focused tests that exercise a real (temporary) Qdrant collection rather than mocking the filter logic, including one that inspects the literal prompt text sent to the LLM to prove restricted content was never supplied to it. Started a full re-index of the 176,054 Synthea-derived knowledge records.

## Latest Commit
(pending — see Next Task)

## Known Issues
- **Indexing the full 176,054 knowledge records into Qdrant is CPU-bound and was still running at the time this file was last updated.** Re-check `scripts/index_knowledge.py`'s output / the Qdrant collection count before relying on live end-to-end queries against real Synthea data; the authorization logic itself is already verified against a real Qdrant fixture collection independent of this.
- PostgreSQL still isn't running locally (see Phase 2 notes) — Phase 3 was also built and verified against SQLite + embedded Qdrant.
- GitHub push is still blocked — no credentials available on this machine (see below).
- `knowledge_records` doesn't yet cover allergies/procedures/careplans/immunizations/imaging/devices/payers (same gap as Phase 2).
- Query routing (section 17 of the Phase 3 spec — classifying a question as clinical/finance/operational before retrieval) is not implemented; the authorization filter alone determines what's retrievable, and semantic similarity determines relevance within that authorized set. This is simpler and still secure, just not as retrieval-quality-optimized as explicit routing would be.

## GitHub Push Status (2026-10-08)
`origin` is `https://github.com/NikhilMMugali/MediGaurd-RAG.git` (confirmed with the user). The remote's placeholder `main` branch was merged non-destructively into local `master`. Push is still blocked: no `gh` CLI, no SSH key, no stored HTTPS credentials on this machine. User chose to skip pushing for now. Local `master` remains ready to push as soon as credentials are available.

## Next Task
1. Let `scripts/index_knowledge.py` finish; verify the Qdrant collection count matches `knowledge_records` count, and run the acceptance-test questions live over HTTP.
2. Wire `/api/documents/upload` to index a newly-created knowledge record immediately (currently only Synthea's backlog is indexed by the script).
3. Build the minimal frontend (login, chat, upload, admin debug view).
4. Re-verify everything against real PostgreSQL once available, and push to GitHub once credentials are available.

## Last Updated
2026-10-08
