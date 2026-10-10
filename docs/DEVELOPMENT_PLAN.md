# MediGuard RAG — Development Plan

Three strict phases. Do not mix phases; a phase is complete only after implementation + tests + manual verification + documentation update + `progress/PROGRESS.md` update + commit (+ push, when requested).

## Phase 1 — Backend foundation (status: DONE for the scope below)

- [x] Repository scaffold (`frontend/`, `backend/`, `data/`, `scripts/`, `docs/`, `progress/`)
- [x] FastAPI app (`backend/app/main.py`)
- [x] Configuration via `pydantic-settings` (`backend/app/config.py`)
- [x] Password hashing (bcrypt via passlib)
- [x] JWT issuance/validation
- [x] Role system (`RoleEnum`: DOCTOR/NURSE/FINANCE/RECEPTION/ADMIN) + server-side role verification (selected role must match stored role)
- [x] `users`/`departments` models
- [x] `/api/auth/login`, `/api/auth/me`
- [x] `/api/documents/upload` reaching a PDF extraction service (PyMuPDF), with file-type/size validation and clear errors for empty/malformed/scanned PDFs
- [x] `/health`
- [x] Backend tests (9 passing: health, login success/failure/role-mismatch, `/me`, upload auth/validation/extraction)
- [x] Demo user seed script (`scripts/seed_users.py`)

Verified: server starts (`uvicorn app.main:app`), `/health` returns 200, login rejects a role that doesn't match the stored role, PDF upload reaches extraction and returns a page count.

Not yet in scope for Phase 1 (by design): PostgreSQL connection in actual use (tests use in-memory SQLite), Synthea import, chunking/embedding/Qdrant, RAG endpoint, frontend UI.

## Phase 2 — Database

- [ ] PostgreSQL + docker-compose
- [ ] Alembic migrations
- [ ] Synthea CSV import (18 files) into the core source tables
- [ ] Application/security tables: `wards`, `patient_assignments`, `user_departments`, `document_acls`, `audit_logs`, `ingestion_jobs`
- [ ] Provenance columns (`source_type`, `source_document_id`, `source_page`, etc.) on every importable table
- [ ] PDF → canonical schema mapping pipeline (intermediate JSON → Pydantic validation → DB insert)
- [ ] Deterministic demo ward/patient assignments using real imported patient ids
- [ ] Indexes on `patient_id`, `encounter_id`, `provider_id`, `claim_id`, `department`, `role`

Exit criteria: Synthea data lives in PostgreSQL; an uploaded PDF creates real structured rows (not just extracted text).

## Phase 3 — RAG

- [ ] Schema-aware + narrative chunking
- [ ] Embedding pipeline (`EmbeddingProvider`)
- [ ] Qdrant collection + payload schema + payload indexes
- [ ] `AuthorizationContext` builder + Qdrant filter builder (`backend/app/authorization/`)
- [ ] `/api/rag/query` endpoint with context-only, cited generation
- [ ] Citation validator
- [ ] Audit logging on every query
- [ ] Admin debug endpoint showing the authorization filter and retrieved-vs-excluded sources
- [ ] Frontend: login, dashboard/chat, upload UI, admin/debug view
- [ ] End-to-end acceptance tests (see README "Acceptance Tests")

Exit criteria: the full MVP flow in README/PRD section "MVP Priority" works live — login per role, grounded cited answers, denial without leakage, new-PDF ingestion immediately queryable.

## Working order within a phase

```text
FOUNDATION → DATABASE → INGESTION → VECTOR INDEX → AUTHORIZATION → RAG → CITATIONS → UI POLISH → TESTING
```

Backend correctness and authorization take priority over visual polish at every step.
