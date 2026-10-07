# MediGaurd RAG — System Architecture

## High-level component diagram

```text
                    ┌──────────────┐
                    │   Frontend    │  (Next.js / React)
                    │  Login, Chat, │
                    │  Upload, Admin│
                    └──────┬───────┘
                           │ HTTPS/JSON
                    ┌──────▼───────┐
                    │   FastAPI     │
                    │   Backend     │
                    │               │
                    │ auth/ authz/  │
                    │ ingestion/    │
                    │ rag/          │
                    └──┬────────┬──┘
                       │        │
            ┌──────────▼──┐  ┌──▼───────────┐
            │ PostgreSQL   │  │   Qdrant      │
            │ (source of   │  │ (vector +     │
            │  truth)      │  │  metadata     │
            │              │  │  index)       │
            └──────────────┘  └──────────────┘
                       ▲
                       │ embeds / validates
            ┌──────────┴──────────┐
            │  LLM / Embedding     │
            │  provider (swappable)│
            └──────────────────────┘
```

## Why PostgreSQL is authoritative and Qdrant is not

PostgreSQL holds every structured fact (patients, encounters, conditions, claims, users, roles, assignments, document provenance). Qdrant holds chunked, embedded *knowledge units derived from* that same data, tagged with the same authorization metadata (role, department, ward, patient, sensitivity). Qdrant is never the only place a fact lives, and a chunk existing in Qdrant never by itself grants access — the authorization filter applied before every search is derived from the PostgreSQL authorization tables, not from anything stored in Qdrant.

## Request flow — chat query (authorization-first retrieval)

```text
User → FastAPI /api/rag/query
   1. Authenticate (JWT) → load User row from PostgreSQL
   2. Build AuthorizationContext from PostgreSQL:
        role, department, ward_ids, assigned_patient_ids,
        allowed_record_types, allowed_sensitivity_levels
   3. Translate AuthorizationContext → Qdrant filter (boolean AND/OR
      over allowed_roles, department, ward_id, patient_id,
      record_type, sensitivity)
   4. Qdrant.search(query_vector, filter=authz_filter) → ONLY
      authorized chunks are returned from the vector store itself
   5. Assemble context from returned chunks only
   6. LLM.generate(system_prompt, context, question)
   7. Validate every citation in the answer resolves to a chunk
      that was actually in the authorized context
   8. Write audit_logs row (user, role, query, retrieved ids, status)
   9. Return answer + citations to frontend
```

Step 3–4 is the critical boundary: restricted chunks never leave Qdrant, so they never reach step 5 or 6. This is what "authZ enforcement at the retrieval layer" means concretely in this codebase.

## Request flow — PDF upload

```text
Frontend → POST /api/documents/upload (multipart PDF + role-gated JWT)
   1. Validate file type/size
   2. Hash file, check for duplicate source_documents row
   3. Extract text per page (PyMuPDF), detect tables (pdfplumber)
      or sections; OCR fallback path if no extractable text
   4. Map extracted text to the canonical intermediate schema
      (patient/encounters/conditions/medications/...)
   5. Validate with Pydantic models
   6. Insert/merge structured rows into PostgreSQL, stamped with
      source_type=UPLOADED_PDF, source_document_id, source_page
   7. Generate schema-aware + narrative knowledge chunks
   8. Embed chunks (EmbeddingProvider)
   9. Upsert into Qdrant with full security metadata payload
   10. Mark ingestion_jobs row COMPLETED; chunks are now queryable
```

## Provider abstractions

To avoid vendor lock-in and scattered provider-specific code, four interfaces are defined in `backend/app/services/`:

- `EmbeddingProvider` — wraps a Sentence Transformers model today; swappable via `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL` env vars.
- `LLMProvider` — wraps Groq/Gemini/OpenAI; selected via `LLM_PROVIDER` env var.
- `VectorStore` — wraps the Qdrant client; isolates collection/payload/filter logic from the RAG pipeline.
- `DocumentExtractor` — wraps PyMuPDF/pdfplumber (and, later, OCR); isolates extraction-library specifics from the ingestion pipeline.

## Directory layout

```text
MediGaurd-RAG/
├── frontend/                 Next.js/React UI
├── backend/
│   ├── app/
│   │   ├── api/               FastAPI routers (auth, upload, rag, admin)
│   │   ├── auth/               JWT, password hashing, role dependencies
│   │   ├── db/                 SQLAlchemy session/engine
│   │   ├── models/              ORM models (Synthea + application tables)
│   │   ├── schemas/             Pydantic request/response + extraction schemas
│   │   ├── services/            Provider abstractions (LLM, embedding, vector store)
│   │   ├── rag/                 Retrieval, context assembly, generation, citations
│   │   ├── ingestion/           PDF extraction, schema mapping, chunking
│   │   ├── authorization/       AuthorizationContext builder, Qdrant filter builder
│   │   └── utils/                Logging, shared helpers
│   └── tests/
├── data/
│   ├── synthea/                 Synthea CSVs (not committed — see .gitignore)
│   └── uploads/                 Uploaded PDFs (runtime)
├── scripts/                      Seeders, import scripts
├── docs/                          This documentation set
├── progress/                      PROGRESS.md, TODO.md, DECISIONS.md
├── .env.example
├── .gitignore
└── docker-compose.yml
```
