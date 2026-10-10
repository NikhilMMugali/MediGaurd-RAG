# MediGuard RAG — Security Model (Threat-Model View)

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

## Threat: unauthorized document access via Document Intelligence

**Mechanism**: `app.api.upload._document_authorized(ctx, doc, user_id)` is checked before the list, status, or query endpoint touches anything else. It denies unless the caller is `ADMIN`, the document's own uploader, or — for a patient-scoped role — the document's resolved patient is in `assigned_patient_ids`. `test_documents.py::test_document_query_denied_before_any_retrieval_for_unauthorized_document` asserts the `403` happens before `run_query` (and therefore before Qdrant or the LLM) is ever reached. A second test (`test_document_query_scopes_retrieval_to_the_named_document_only`) proves that even an authorized, correctly-scoped query for one document cannot surface a *different* document's chunks for the same patient — the `source_document_id` Qdrant filter is additive to every other authorization condition, never a replacement for them.

## Threat: Hospital Insights aggregates across an unauthorized scope

**Mechanism**: `app.rag.insights.build_overview` calls `build_authorization_context` and, for `DOCTOR`/`NURSE`, filters every SQL `COUNT`/`SUM` to `assigned_patient_ids` — there is no code path that aggregates over every patient for a patient-scoped role, regardless of how the question is phrased (section 6D "a doctor must never gain access to financial records solely by using natural language" — `DOCTOR`/`NURSE` simply have no finance metrics defined at all, matching their existing `ROLE_POLICY`). `test_insights.py::test_doctor_metrics_scoped_to_assigned_patients_only` seeds two patients, assigns only one, and asserts the unassigned patient's condition/medication rows are not counted.

## Residual/Phase-2+3 work

- `document_acls` row-level checks for individually-shared uploaded documents.
- `patient_assignments`/`wards` scoping for DOCTOR/NURSE (Phase 2).
- Reranking/hybrid retrieval must preserve the same pre-filter boundary — any added retrieval stage filters *within* the already-authorized candidate set, never widens it.
