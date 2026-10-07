# MediGaurd RAG — Tech Stack

## Backend

| Concern | Choice | Notes |
|---|---|---|
| Language/runtime | Python 3.12 | Python 3.14 was tried first but `psycopg2-binary`/ML wheels were not yet available for it on this machine; 3.12 installs cleanly. If your machine has 3.14 wheels available, it should still work — pin whichever 3.11–3.12 interpreter is available for the smoothest install. |
| Web framework | FastAPI + uvicorn | Async-ready, automatic OpenAPI docs at `/docs`. |
| ORM | SQLAlchemy 2.x | Declarative models in `backend/app/models/`. |
| DB driver | `psycopg[binary]` (psycopg3) | `psycopg2-binary` had no prebuilt wheel for the available Python version; psycopg3's binary extra avoids a local build. |
| Migrations | Alembic | To be wired up in Phase 2. |
| Auth | `python-jose` (JWT) + `passlib[bcrypt]` | `bcrypt` pinned to `4.0.1` — newer `bcrypt` 4.1+ removed an attribute `passlib` 1.7.4 reads, causing a `72 bytes` hashing error; pin until passlib is upgraded. |
| Config | `pydantic-settings` | Reads `.env`; see `.env.example`. |
| PDF extraction | PyMuPDF (`fitz`) primary, `pdfplumber` for tables | OCR fallback path reserved, not forced. |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2` default) | Swappable via `EMBEDDING_MODEL`. |
| Vector DB | `qdrant-client` against a Qdrant server | Collection + payload index, not FAISS/in-memory, so filtering is a first-class DB feature. |
| LLM | Provider-abstracted; Groq default, Gemini/OpenAI alternatives | Selected via `LLM_PROVIDER` env var. |
| Testing | `pytest` + FastAPI `TestClient`, in-memory SQLite (`StaticPool`) for DB-dependent tests | Postgres is not required to run the Phase 1 test suite. |

## Frontend

Next.js / React, enterprise-dashboard styling (no heavy animation libraries) — see [ARCHITECTURE.md](ARCHITECTURE.md) directory layout. Not yet scaffolded; Phase 1 focused on the backend foundation.

## Infrastructure

- PostgreSQL (source of truth)
- Qdrant (vector + metadata index)
- `docker-compose.yml` to run both locally

## Why not X

- **No Kubernetes / microservices** — single FastAPI service is enough for this scope; see "What not to build" in [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md).
- **No fine-tuning** — provider LLMs used as-is with grounded prompting.
- **No FAISS/in-memory vector index** — the problem statement specifically tests "vector DB internals," which calls for a real vector database with payload filtering, not an in-process index.
