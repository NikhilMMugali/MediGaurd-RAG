# MediGaurd RAG — RAG Design (Phase 3)

> **Implementation status (2026-10-08):** implemented in `backend/app/rag/pipeline.py`, `backend/app/authorization/`, `backend/app/services/{embedding_provider,vector_store,llm_provider}.py`. Qdrant runs in qdrant-client's embedded on-disk mode (`QDRANT_MODE=local`, no server process) so it needs no infrastructure beyond a writable directory; `QDRANT_MODE=server` + `QDRANT_URL` switches to a real Qdrant server with no other code changes. The LLM call itself falls back to a non-hallucinating extractive mode (returns the top authorized chunk's own text, cited) when no provider API key is configured — see `progress/DECISIONS.md`. Reranking and hybrid lexical search (stage 2-3 below) are not implemented.

## Pipeline

```text
User question
     ↓ query normalization
     ↓ AuthorizationContext (built from PostgreSQL: role, department,
         ward_ids, assigned_patient_ids, allowed_record_types,
         allowed_sensitivity_levels, allowed_document_ids)
     ↓ optional query/domain classification (clinical vs finance vs operational)
     ↓ embedding (EmbeddingProvider)
     ↓ filtered vector retrieval — Qdrant search() called WITH the
         authorization filter attached; restricted chunks never leave
         the vector store
     ↓ top-K authorized candidates
     ↓ optional reranking
     ↓ context assembly (only authorized chunks, with provenance kept)
     ↓ LLM generation
     ↓ citation validation (every citation must resolve to a chunk
         that was actually in the authorized context assembled above)
     ↓ audit_logs write
     ↓ grounded answer + citations
```

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
