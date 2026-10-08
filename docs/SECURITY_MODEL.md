# MediGaurd RAG — Security Model (Threat-Model View)

This document complements [SECURITY.md](SECURITY.md) (which defines the role matrix and policy) with the mechanics of *how* each threat is actually blocked in code.

## Threat: client sends a role it isn't assigned

**Mechanism**: `backend/app/api/auth.py::login` compares `payload.role` (from the request body) against `user.role` (loaded from PostgreSQL) and rejects on mismatch, before issuing a JWT. `backend/app/auth/deps.py::get_current_user` re-checks the JWT's role claim against the live database row on every subsequent request, so a stale or forged token claiming a higher role than the account currently has is also rejected.

## Threat: restricted chunk reaches the LLM

**Mechanism**: the Qdrant `search()` call itself is parameterized with a filter built from the requester's `AuthorizationContext` (Phase 3, `backend/app/authorization/` + `backend/app/rag/`). A restricted chunk is excluded by the vector database before the application process ever receives it — there is no step where "everything" is fetched and then trimmed. This is the literal answer to "authZ enforcement at the retrieval layer, not just the app layer."

**Implemented (2026-10-08) and tested against a real Qdrant collection** (not a mock of one): `backend/tests/test_rag_authorization.py` loads a tiny fixture collection with both authorized and unauthorized points and asserts, per role, exactly which content comes back from `VectorStore.search()`. `backend/tests/test_rag_pipeline.py::test_finance_query_never_sends_clinical_content_to_llm` goes one step further and inspects the literal context string handed to the LLM provider, not just the final answer text — proving the restricted content was never *in* the prompt, which is a stronger claim than "the model didn't repeat it."

**Patient-level denial short-circuits before any vector search or structured DB lookup.** A DOCTOR/NURSE role is "patient-scoped": `AuthorizationContext.assigned_patient_ids` holds their real `patient_assignments` rows. If a specific unassigned patient is identified in the request (explicit `patient_id` field — the clean display id like `P001`, or a legacy raw UUID — or either form detected in the question text via `app/rag/pipeline.py::resolve_patient_reference`), `run_query` returns `DENIED` immediately — neither Qdrant nor `app/rag/structured_answers.py` is ever queried for that turn, so "restricted content reached the LLM" isn't just unlikely, it's structurally impossible for that request. A patient-scoped user with zero assignments is handled the same way (empty list is treated as "deny everything," never as "no restriction" — this exact bug class is covered by `test_doctor_with_no_assignments_matches_nothing`).

## Threat: LLM is asked to hide information it was shown

**Mechanism**: disallowed by design — restricted chunks are never included in the prompt context in the first place (see above), so there is nothing for the LLM to "hide." The system prompt additionally forbids inferring or hinting at absent information.

## Threat: fabricated or dangling citation

**Mechanism**: a post-generation citation validator checks every citation against the actual set of chunk/record ids included in the assembled context for that request. A citation pointing to anything outside that set is a grounding failure, not a valid answer.

## Threat: sensitive PII leaks through embeddings

**Mechanism**: `SSN`, `DRIVERS`, `PASSPORT` are excluded at chunk-generation time (`sensitivity=restricted_pii`) — they are never embedded, so no similarity search can surface them, regardless of role.

## Threat: secrets in source control

**Mechanism**: all credentials/keys come from environment variables loaded via `pydantic-settings` (`backend/app/config.py`); `.env` is gitignored; `.env.example` documents required keys with placeholder values only.

## Threat: PDF upload abuse

**Mechanism**: content-type/extension check, file-size cap (`MAX_UPLOAD_SIZE_MB`), and parsing via PyMuPDF (`backend/app/ingestion/pdf_extractor.py`) in a try/except boundary that converts any malformed/empty/scanned PDF into a clear `422` rather than a crash or a silently empty ingestion.

## Residual/Phase-2+3 work

- `document_acls` row-level checks for individually-shared uploaded documents.
- `patient_assignments`/`wards` scoping for DOCTOR/NURSE (Phase 2).
- Reranking/hybrid retrieval must preserve the same pre-filter boundary — any added retrieval stage filters *within* the already-authorized candidate set, never widens it.
