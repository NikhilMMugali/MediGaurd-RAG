# MediGaurd RAG — RAG Design (Phase 3)

> **Implementation status (2026-10-08):** implemented in `backend/app/rag/pipeline.py`, `backend/app/authorization/`, `backend/app/services/{embedding_provider,vector_store,llm_provider}.py`. Qdrant runs in qdrant-client's embedded on-disk mode (`QDRANT_MODE=local`, no server process) so it needs no infrastructure beyond a writable directory; `QDRANT_MODE=server` + `QDRANT_URL` switches to a real Qdrant server with no other code changes. The LLM call itself falls back to an explicit "generation unavailable" dev-mode message (never raw chunk data disguised as an answer) when no provider API key is configured or the call fails — see `progress/DECISIONS.md`. Reranking and hybrid lexical search (stage 2-3 below) are not implemented.
>
> **Hybrid retrieval update (2026-10-08):** the pipeline below describes the *semantic* path only. As of the "clean dataset + hybrid RAG" iteration, `app/rag/query_classification.py` first decides a `route` — `structured` (an exact SQL lookup in `app/rag/structured_answers.py` answers directly, no Qdrant/LLM call at all), `summary` (a deterministic cross-domain rollup, also no LLM), or `semantic` (the pipeline below). Authorization (`AuthorizationContext` + the record-type intersection) is computed once in `_authorize_and_classify()` and applies identically to all three routes — see progress/DECISIONS.md "Hybrid retrieval."

## Reused by Document Intelligence and Hospital Insights

Both newer AI Assistant features (section 4/5/6) sit on top of this same pipeline rather than a parallel one:

- **Document Intelligence Q&A** (`POST /api/documents/query`) calls `run_query(..., document_id=...)` — the exact function below, with one extra Qdrant/SQL condition (`source_document_id`) layered on top of the normal authorization filter. Same authorization, same citation validation, same audit log; see `docs/DATA_FLOW.md` "Document-scoped Q&A flow."
- **Hospital Insights** (`app/rag/insights.py`) does *not* call this pipeline — it is SQL-only for every number it reports, by design (section 6C: "SQL is the source of truth for numeric metrics"). It reuses `build_authorization_context` (the same function `_authorize_and_classify` calls here) so its scoping can never diverge from chat/document authorization, and reuses `get_llm_provider`/citation validation only to narrate already-computed metrics, never to retrieve or compute them. See `docs/DATA_FLOW.md` "Hospital Insights flow."

## Pipeline (semantic route)

```text
User question
     ↓ patient-context resolution (resolve_patient_reference: UI's
         Pxxx display id, or a pasted UUID, -> the real internal id)
     ↓ AuthorizationContext (built from PostgreSQL: role, department,
         ward_ids, assigned_patient_ids, allowed_record_types,
         allowed_sensitivity_levels, allowed_document_ids)
     ↓ query classification (app/rag/query_classification.py) — record
         type(s)/observation category/recency, always intersected with
         (never widening) the AuthorizationContext above
     ↓ embedding (EmbeddingProvider)
     ↓ filtered vector retrieval — Qdrant search() called WITH the
         authorization filter attached; restricted chunks never leave
         the vector store. A known patient uses an indexed-SQL-then-
         retrieve-by-id fast path instead of a filtered Qdrant scan
         (see progress/DECISIONS.md "Qdrant local-mode" entries)
     ↓ top-K authorized candidates, ranked by relevance (+ recency blend
         when the question asked for "recent"/"latest")
     ↓ context assembly (only authorized chunks, with provenance kept)
     ↓ LLM generation
     ↓ citation validation (every [SOURCE_n] the model cites must
         resolve to a source actually in the assembled context —
         anything else is stripped, never silently passed through)
     ↓ audit_logs write
     ↓ grounded answer + citations
```

Exact-fact questions (patient identity, medications, conditions,
allergies, procedures, encounters, finance, recent observations) skip
this entirely — `app/rag/structured_answers.py` builds the answer and
citations straight from SQLAlchemy rows once authorization has computed
the same allowed record types.

## System prompt contract

```text
You are MediGaurd RAG.
Answer only using the supplied authorized context.
Do not use outside knowledge to invent facts.
Do not infer sensitive facts that are absent.
Do not reveal restricted information.
If the authorized context does not contain enough information,
say that the information is unavailable.
Every factual claim must include a source citation.
Never cite a source that was not provided in the authorized context.
```

## Citation format

- Database-derived: `[Condition Record: <record_id>]` or `[Patient P999 | conditions table | record <id>]`.
- PDF-derived: `[patient_p999.pdf | Page 4 | Medications]`.

A post-generation validator checks every citation token against the set of chunk ids actually included in the assembled context; any citation that doesn't resolve is treated as a grounding failure (reject/regenerate, never silently pass through).

## Hallucination / denial handling

- Missing information: `"I couldn't find authorized information supporting that answer."`
- Role-restricted information: `"Clinical diagnosis information is not available for your role."` — never a hint about what the hidden record contains.

## Retrieval quality — staged approach

1. Baseline: dense vector retrieval + metadata filtering (ship this first).
2. Optional hybrid: add lexical/keyword search alongside dense retrieval.
3. Optional reranking: cross-encoder rerank of the filtered top-K.

Each stage sits behind the `VectorStore`/retrieval interface in `backend/app/rag/` so stage 2–3 can be added without rewriting the query flow.

## Provider abstractions

- `EmbeddingProvider` — Sentence Transformers (`EMBEDDING_MODEL` env var), swappable.
- `LLMProvider` — Groq / Gemini / OpenAI (`LLM_PROVIDER` env var), swappable. No vendor-specific code outside this abstraction.

## Admin debug view contract

Shows the query, the user, the constructed authorization filter, and a list of sources with retrieved/not-retrieved status — never the content of an excluded, restricted chunk.
