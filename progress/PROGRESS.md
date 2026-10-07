# MediGaurd RAG Progress

## Current Phase
Phase 1 — Backend (complete for its scope) → starting Phase 2 — Database

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
- [ ] PostgreSQL setup
- [ ] Schema
- [ ] Migrations
- [ ] Synthea import
- [ ] Authorization tables
- [ ] PDF normalization
- [ ] Provenance

## Phase 3 — RAG
- [ ] Chunking
- [ ] Embeddings
- [ ] Qdrant
- [ ] Metadata filters
- [ ] Retrieval authorization
- [ ] LLM
- [ ] Citations
- [ ] Audit logging
- [ ] End-to-end tests

## Latest Completed Work
Scaffolded the full repository structure (frontend/backend/data/scripts/docs/progress), wrote the full documentation set, and built Phase 1 of the backend: FastAPI app with config management, JWT auth with bcrypt password hashing, server-verified roles (DOCTOR/NURSE/FINANCE/RECEPTION/ADMIN), `/health`, `/api/auth/login`, `/api/auth/me`, and `/api/documents/upload` wired to a PyMuPDF-based PDF text extractor with file-type/size validation and clear errors for malformed/scanned PDFs. Verified Synthea dataset (18 CSVs, matches documented inventory) extracted into `data/synthea/`. 9 backend tests pass against an in-memory SQLite DB; the live server was started and `/health` confirmed over HTTP.

## Latest Commit
(not yet committed — see Next Task)

## Known Issues
- Target Python 3.14 had no prebuilt wheels for `psycopg2-binary`/ML packages on this machine; switched the virtualenv to Python 3.12 and the DB driver to `psycopg[binary]` (psycopg3). Documented in docs/TECH_STACK.md.
- `bcrypt` must stay pinned to `4.0.1` for compatibility with `passlib==1.7.4` (newer bcrypt removed an attribute passlib reads, breaking password hashing).
- No PostgreSQL/Qdrant are running yet; Phase 1 tests deliberately use in-memory SQLite so they don't require infrastructure.

## Next Task
Phase 2: stand up PostgreSQL via docker-compose, write the full ORM schema for Synthea's 18 tables plus `wards`/`patient_assignments`/`user_departments`/`document_acls`/`audit_logs`/`ingestion_jobs`, and build the Synthea CSV importer.

## Last Updated
2026-10-08
