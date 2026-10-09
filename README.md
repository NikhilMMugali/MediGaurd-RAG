# MediGaurd RAG

Secure hospital intelligence assistant built for the Code Carnival hackathon. Combines a preloaded synthetic hospital database (Synthea) with live PDF uploads into one unified, role-aware, cited RAG system.

**Team:** Nikhil Mugali (Lead), Prince Naliyapara, Titli Rajdev, Nanditi Joshi
**Repository:** https://github.com/NikhilMMugali/MediGaurd-RAG.git

## Problem Statement

> Secure Multi-Modal RAG System with Access Control
>
> Build a Retrieval-Augmented Generation system that ingests mixed data (PDFs, images with OCR, structured DB records), builds a unified vector + metadata index, and answers natural language queries but must enforce row/document-level access control so a query never leaks data the requesting user isn't authorised to see, and must cite exact sources for every claim in its answer. Tests: LLM/embedding pipeline design, vector DB internals, authZ enforcement at the retrieval layer (not just app layer), multi-modal data handling, hallucination/citation grounding.

## The core architectural principle

> **Unauthorized information must never be retrieved and sent to the LLM.**

```text
authenticate user → determine authorization → create retrieval filter
→ retrieve only authorized records/chunks → send only authorized
context to LLM → generate grounded answer → attach exact citations
```

Never: retrieve everything and ask the LLM to hide what's restricted. Full detail in [docs/SECURITY.md](docs/SECURITY.md).

## Features

- Five server-verified roles: DOCTOR, NURSE, FINANCE, RECEPTION, ADMIN — a client-selected role must match the account's stored role or login is rejected.
- Synthea-derived hospital database, narrowed to a clean, deterministic 100-patient demo dataset (`P001`–`P100`) — see [docs/CLEAN_DATASET.md](docs/CLEAN_DATASET.md).
- Hybrid RAG: exact-fact questions (identity, medications, conditions, encounters, finance) answer directly from SQL, no LLM/Qdrant call — open-ended questions use Qdrant + Groq synthesis. See [docs/RAG_DESIGN.md](docs/RAG_DESIGN.md).
- **Document Intelligence** (`/assistant/documents`) — upload, track, and ask questions about patient PDFs, grounded only in that document's own authorized chunks. PDF upload → extraction → schema mapping → database insertion → chunking → embedding → Qdrant indexing, all in one request, immediately queryable.
- **Hospital Insights** (`/assistant/insights`) — role-aware KPIs computed entirely from SQL, with an LLM-narrated (never LLM-computed) summary.
- Authorization enforced at the vector-retrieval layer via a pre-search Qdrant filter, not by post-filtering LLM output — applies identically across chat, Document Intelligence, and Hospital Insights.
- Every factual claim in an answer carries an exact citation (database record or PDF page/section), resolved to a friendly label — never a raw internal UUID.
- Audit logging of every query (user, role, query, retrieved sources, allow/deny outcome).
- Admin dashboard showing live (never hardcoded) counts plus recent uploads/security events.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md).

```text
Frontend (React + Vite) → FastAPI backend → PostgreSQL/SQLite (source of truth)
                                           → Qdrant (vector + metadata index)
```

### Navigation

```text
MediGaurd
├── Patients                      /patients
└── AI Assistant
    ├── Clinical Chat             /assistant/chat
    ├── Document Intelligence     /assistant/documents   (DOCTOR/NURSE/ADMIN)
    └── Hospital Insights         /assistant/insights
```

## Tech Stack

See [docs/TECH_STACK.md](docs/TECH_STACK.md) for the full list and version-pinning notes (Python 3.12, `psycopg[binary]`, `bcrypt==4.0.1`).

## Setup

### Backend

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env   # fill in real secrets/API keys locally, never commit .env
```

### Database

```bash
docker compose up -d postgres qdrant   # or point DATABASE_URL at any PostgreSQL instance
alembic -c backend/alembic.ini upgrade head
cd backend  # SYNTHEA_CSV_DIR/.env are resolved relative to cwd — run these from here
python ../scripts/build_clean_dataset.py     # data/raw/synthea_original -> data/clean (see docs/CLEAN_DATASET.md)
python ../scripts/validate_clean_dataset.py
python ../scripts/seed_users.py
python ../scripts/import_synthea.py          # imports data/clean
python ../scripts/seed_authorization_data.py
python ../scripts/generate_knowledge_records.py
```

Each script is idempotent — safe to re-run. **Current local dev state:** PostgreSQL/Docker were unavailable on the build machine, so local verification ran against SQLite (`DATABASE_URL=sqlite:///...` in `.env`); the schema is plain SQLAlchemy with no Postgres-specific types, so switching `DATABASE_URL` to a real PostgreSQL instance needs no code changes — see [progress/DECISIONS.md](progress/DECISIONS.md).

### Dataset

The app imports from `data/clean/` — a deterministic, demo-safe 100-patient
subset of the full Synthea sample (clean display ids, synthetic names,
sensitive identifiers dropped). See [docs/CLEAN_DATASET.md](docs/CLEAN_DATASET.md)
for what changed and why, and how to rebuild it from `data/raw/synthea_original/`
(the untouched original export; not committed — see `.gitignore`).
`scripts/import_synthea.py` imports every CSV in `SYNTHEA_CSV_DIR`
(`data/clean` by default) in dependency order and reports row counts.

### Index knowledge into Qdrant

```bash
python scripts/index_knowledge.py
```

Embeds every `knowledge_records` row (batched, idempotent) into Qdrant's embedded local store at `QDRANT_PATH` (no separate Qdrant server needed — see `.env.example`). CPU-bound; a newly uploaded PDF's records are indexed immediately by the upload endpoint itself, so this script only needs to run once for the initial backlog (or to catch up anything that failed to index at upload time, or after rebuilding the clean dataset).

### Run the backend

```bash
cd backend
uvicorn app.main:app --reload
```

Then `curl http://127.0.0.1:8000/health` → `{"status":"ok","service":"MediGaurd RAG backend"}`.

### Run the frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL, defaults to http://localhost:8000
npm run dev
```

Open `http://localhost:5173`. The login page's "Use demo account" selector autofills the seeded credentials below for the chosen role — the backend still independently verifies the stored role on every login.

### Run tests

```bash
cd backend
pytest tests/ -v
```

Runs against an in-memory SQLite database — no PostgreSQL required. **Stop any locally running `uvicorn` process first** — qdrant-client's embedded local mode holds an exclusive file lock on `QDRANT_PATH`, and a handful of these tests open a real (temp-directory) Qdrant collection of their own; running them while the dev server also has the real collection open will crash whichever process opened it second (see `progress/DECISIONS.md`).

## Environment Variables

See [.env.example](.env.example) for the full list: app secret key, JWT settings, `DATABASE_URL`, `QDRANT_URL`, embedding/LLM provider selection and API keys, upload limits, Synthea CSV directory.

## Demo Users (seeded via `scripts/seed_users.py`)

| Username | Role | Password |
|---|---|---|
| doctor01 | DOCTOR | medigaurd123 |
| nurse01 | NURSE | medigaurd123 |
| finance01 | FINANCE | medigaurd123 |
| reception01 | RECEPTION | medigaurd123 |
| admin01 | ADMIN | medigaurd123 |

## Sample Questions

- "What conditions does patient P001 have?" (DOCTOR → answered with citation; FINANCE → restricted)
- "What is the outstanding amount for patient P001?" (FINANCE → answered with citation; DOCTOR → restricted)
- "When was patient P001's last encounter?" (RECEPTION → answered with citation)
- Document Intelligence: upload a patient PDF, then ask "Summarize this report." or "What medications are mentioned in this document?" — answered only from that document's own chunks.
- Hospital Insights: "Summarize recent activity and highlight any data gaps." — every number in the answer traces back to a live SQL aggregate shown on the same page.

## Security Model

See [docs/SECURITY.md](docs/SECURITY.md) (policy/role matrix) and [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) (threat-model mechanics).

## PDF Upload Workflow

See [docs/DATA_FLOW.md](docs/DATA_FLOW.md).

## Acceptance Tests

Ten end-to-end tests covering per-role access, per-role denial, and new-document ingestion — see [docs/PROJECT_REQUIREMENTS.md](docs/PROJECT_REQUIREMENTS.md).

## Success Criteria

1. Synthea data lives in our own PostgreSQL database.
2. Password-based login for five roles, server-side-verified.
3. PDFs can be uploaded, extracted, mapped to the canonical schema, and inserted as real records.
4. Knowledge chunks with provenance are embedded and indexed in Qdrant.
5. Retrieval applies the authorization filter before returning any chunk.
6. Unauthorized information never enters the LLM context.
7. Every factual claim carries a citation.
8. Audit logs exist for every query.
9. All ten acceptance tests pass.
10. Full documentation set (this README, `docs/`, `progress/`) stays current, and major phases are committed (and pushed, when requested).

## Screenshots

_(placeholder — add once the frontend UI exists)_

## Future Enhancements

OCR for scanned PDFs, hybrid lexical+dense retrieval with reranking, multi-tenant organization scoping, image-modality clinical documents.

## Documentation Index

- [docs/PRD.md](docs/PRD.md) — product requirements
- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) — requirement → implementation traceability
- [docs/PROJECT_REQUIREMENTS.md](docs/PROJECT_REQUIREMENTS.md) — acceptance tests & hard guardrails
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) / [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) — component & deployment views
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) / [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) — schema
- [docs/DATA_FLOW.md](docs/DATA_FLOW.md) — ingestion pipeline
- [docs/RAG_DESIGN.md](docs/RAG_DESIGN.md) — retrieval & generation design
- [docs/SECURITY.md](docs/SECURITY.md) / [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) — authorization policy & mechanics
- [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md) — endpoint reference
- [docs/TECH_STACK.md](docs/TECH_STACK.md) — dependency choices and why
- [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) — phase plan and exit criteria
- [progress/PROGRESS.md](progress/PROGRESS.md), [progress/TODO.md](progress/TODO.md), [progress/DECISIONS.md](progress/DECISIONS.md)
