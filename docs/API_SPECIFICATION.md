# MediGaurd RAG — API Specification

Base path: `/api` (health check is unprefixed at `/health`).

## Auth

### `POST /api/auth/login`
Implemented — `backend/app/api/auth.py`.

Request:
```json
{ "username": "doctor01", "password": "medigaurd123", "role": "DOCTOR" }
```

Response `200`:
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "username": "doctor01",
  "full_name": "Dr. Example",
  "role": "DOCTOR",
  "department": "Cardiology"
}
```

Response `401` when the password is wrong, or when `role` does not match the account's stored role (the server never trusts the client-selected role).

### `GET /api/auth/me`
Implemented. Requires `Authorization: Bearer <jwt>`. Returns the current user's username, full name, role, and department.

## Documents

All `/api/documents/*` endpoints below (except `/upload`'s own role check, identical) require `Authorization: Bearer <jwt>` for a `DOCTOR`, `NURSE`, or `ADMIN` user — `FINANCE`/`RECEPTION` get `403`, consistent with Document Intelligence being a clinical/administrative feature (see `app.api.upload._DOC_ROLES`).

### `POST /api/documents/upload`
Implemented end-to-end — `backend/app/api/upload.py`. Validate → hash/duplicate-check → persist PDF bytes to `UPLOAD_DIR` → extract text → map to structured tables → generate knowledge records → embed + index into Qdrant, all in one request (see [DATA_FLOW.md](DATA_FLOW.md)).

Multipart form field: `file` (PDF, ≤ `MAX_UPLOAD_SIZE_MB`).

Response `200` (text extracted and mapped):
```json
{
  "document_id": "uuid",
  "file_name": "patient_p999.pdf",
  "status": "COMPLETED",
  "page_count": 5,
  "message": "...",
  "patient_id": "P101",
  "records_created": 4,
  "chunks_indexed": 4
}
```

Response `200` (scanned/image-only PDF — no OCR yet): `status: "NEEDS_REVIEW"`, `patient_id: null`, `records_created: 0`, `chunks_indexed: 0`. The file and its `source_documents` row are still persisted — nothing is silently discarded (see "OCR scope" in [DATA_FLOW.md](DATA_FLOW.md)).

`400` — not a PDF or exceeds size limit. `409` — duplicate file hash. `422` — PDF could not be parsed at all (empty/malformed file).

### `GET /api/documents/limits`
Implemented. Returns `{"max_upload_size_mb": 20}` from server config, so the frontend's client-side size check is never a hardcoded guess.

### `GET /api/documents`
Implemented. Lists only documents the caller is authorized to see: every document for `ADMIN`; for `DOCTOR`/`NURSE`, documents they uploaded themselves plus documents belonging to a patient currently assigned to them (`app.api.upload._document_authorized`). Response: `{"documents": [{"document_id", "file_name", "status", "document_type", "patient_id", "uploaded_by", "created_at"}], "total": n}` — `patient_id` is always the display id, `uploaded_by` the uploader's full name, never raw internal ids.

### `GET /api/documents/{document_id}/status`
Implemented. `403` if the caller isn't authorized for that document (same rule as the list endpoint). Returns the persisted, authoritative processing state — `status`, `page_count` (computed live from the stored PDF), `records_created`, `chunks_created`, `error_message` — never an optimistic client-side guess.

### `POST /api/documents/query`
Implemented — secure, document-scoped Q&A. Body: `{"document_id": "...", "question": "..."}`. `403` before any retrieval if the document isn't authorized for the caller. Internally calls `app.rag.pipeline.run_query(..., document_id=...)`, which adds a `source_document_id` condition to the Qdrant filter (or the SQL fast-path query) on top of every normal authorization condition — so even an authorized user only ever gets answers grounded in *that* document's own chunks, never another document's. Response shape matches `/api/rag/query`.

## Patients (added for the frontend — reuses existing authorization/RAG, no new security logic)

### `GET /api/patients?limit=20&offset=0`
Implemented — `backend/app/api/patients.py`. Returns only patient ids the current user is authorized to see, using the same `AuthorizationContext` the RAG pipeline uses. `scope` is `"assigned"` (DOCTOR/NURSE, from real `patient_assignments`) or `"all"` (paginated, for roles with no patient-level scoping).

### `GET /api/patients/{patient_id}/status`
Implemented. Calls the same `retrieve_authorized_sources()` the chat endpoint uses, then classifies deterministically: an authorized `condition` record found → `"Attention"`; none → `"Stable"`; retrieval denied or empty → `"No Recent Information"`. Never a second, independent "status AI."

### `GET /api/patients/{patient_id}/summary`
Implemented (Phase 2). Row counts only (conditions/medications/encounters) — no clinical content.

## Health

### `GET /health`
Implemented. Returns `{"status": "ok", "service": "MediGaurd RAG backend"}`. No authentication required.

## RAG (Phase 3 — implemented)

### `POST /api/rag/query`
Implemented — `backend/app/api/rag.py`. Requires `Authorization: Bearer <jwt>`.

Request:
```json
{ "question": "What medications is P001 taking?", "patient_id": "P001" }
```
`patient_id` is optional and never a security parameter — it only disambiguates which already-authorized patient is meant. Callers pass the clean display id (`P001`, as shown in the UI); a legacy raw internal UUID is also accepted, and either form appearing literally in `question` text is detected automatically (`app.rag.pipeline.resolve_patient_reference`). Authorization always comes from the authenticated user, never from the request body.

Response `200`:
```json
{
  "answer": "...",
  "status": "ANSWERED",
  "citations": [
    {"source_id": "SOURCE_1", "source_type": "SYNTHEA", "record_id": "...", "file_name": null, "page": null, "section": "condition"}
  ],
  "retrieved_count": 3,
  "debug": null
}
```
`status` is one of `ANSWERED`, `DENIED` (a specific patient was identified and is not assigned to this user — the vector store is never even queried), or `NO_AUTHORIZED_CONTEXT` (no authorized chunk matched, or a patient-scoped role has zero assignments). `debug` (the constructed authorization filter + retrieved record ids) is populated only when the caller is `ADMIN`, and never contains the content of an excluded record.

## Insights

Requires `Authorization: Bearer <jwt>`; no role restriction (every role gets its own scoped view — see `app.rag.insights.build_overview`).

### `GET /api/insights/overview`
Implemented — `backend/app/api/insights.py`. Returns role-aware KPIs computed directly from SQL aggregates, never invented: `ADMIN` gets system-wide counts (patients, encounters, documents, knowledge records, live Qdrant vector count); `FINANCE` gets claim counts/outstanding totals/status breakdown; `RECEPTION` gets encounter counts/type breakdown; `DOCTOR`/`NURSE` get counts scoped strictly to their own `assigned_patient_ids`. A role with nothing to summarize (e.g. a doctor with zero assignments) gets `"metrics": [], "note": "..."` — never a fabricated zero.

```json
{
  "role": "FINANCE",
  "period": "All time",
  "generated_at": "2026-10-09T07:38:42Z",
  "metrics": [{"key": "outstanding_total", "label": "Total outstanding balance", "value": 570.73, "unit": "USD"}],
  "breakdown": {"label": "Claims by status", "items": [["CLOSED", 8971], ["BILLED", 7]]},
  "note": null
}
```

### `POST /api/insights/query`
Implemented. Body: `{"question": "..."}`. Re-computes the same SQL-backed overview, packages every metric as a single `[SOURCE_1]` evidence block, and asks the configured LLM to narrate/explain it — the model is structurally unable to cite a second source, so it cannot smuggle in an invented number under a fake citation. If there are no metrics to narrate (e.g. no assigned patients), the LLM is never called at all; the honest empty note is returned directly.

## Planned — Admin (Phase 3)

```text
GET /api/admin/documents
GET /api/admin/chunks
GET /api/admin/users
GET /api/admin/audit-logs
GET /api/admin/ingestion-jobs
POST /api/admin/debug-retrieval   # shows the authorization filter + what was/was not retrieved for a given query, without exposing restricted content
```

## Error format

All validation errors return FastAPI's standard `{"detail": [...]}` or `{"detail": "message"}` shape. No endpoint returns stack traces or secrets in error bodies.
