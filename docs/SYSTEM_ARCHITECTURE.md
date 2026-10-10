# MediGuard RAG — System Architecture (Deployment View)

For the component/request-flow view, see [ARCHITECTURE.md](ARCHITECTURE.md). This document covers how the pieces run and talk to each other.

## Runtime topology

```text
┌────────────┐      ┌──────────────┐      ┌────────────────┐
│  Frontend   │ ───▶ │   Backend     │ ───▶ │  PostgreSQL     │
│  (Next.js)  │ JSON │   (FastAPI,   │ SQL  │  :5432          │
│  :3000      │◀─── │   uvicorn)    │◀───  │                 │
└────────────┘      │   :8000       │      └────────────────┘
                     │               │
                     │               │ gRPC/HTTP ┌────────────────┐
                     │               │ ─────────▶│  Qdrant         │
                     │               │◀──────────│  :6333          │
                     └───────┬───────┘           └────────────────┘
                             │ HTTPS
                     ┌───────▼───────┐
                     │  LLM / Embed   │
                     │  provider API  │
                     │  (Groq/Gemini/ │
                     │  OpenAI /      │
                     │  local ST model│
                     └───────────────┘
```

## Local development

`docker-compose.yml` brings up PostgreSQL and Qdrant; the backend runs via `uvicorn app.main:app --reload` from a Python virtualenv (see [TECH_STACK.md](TECH_STACK.md) for the pinned versions that proved compatible on this machine — Python 3.12, not 3.14, due to ML package wheel availability). The frontend runs via `npm run dev`.

## Environments

- **development** — local docker-compose Postgres/Qdrant, `.env` with local placeholder secrets, `APP_DEBUG=true`.
- **demo (hackathon)** — same topology, run on the presenter's machine; no separate staging/production tier is in scope for this prototype (see "What not to build" in [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md)).

## Why this topology satisfies the problem statement

- **Vector DB internals** are exercised directly: Qdrant collection + payload index + filter, not hidden behind a generic "retriever" call.
- **AuthZ at the retrieval layer** is structural, not incidental: the authorization filter is a parameter of the Qdrant call, enforced by the database that owns similarity search, not by code that runs after it.
- **Source of truth stays single**: PostgreSQL. Qdrant can be rebuilt/re-indexed at any time from PostgreSQL + source documents without losing any fact.
