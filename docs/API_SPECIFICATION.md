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

### `POST /api/documents/upload`
Implemented (Phase 1 scope: validation + text extraction only). Requires `Authorization: Bearer <jwt>` for a `DOCTOR`, `NURSE`, or `ADMIN` user.

Multipart form field: `file` (PDF, ≤ `MAX_UPLOAD_SIZE_MB`).

Response `200`:
```json
{
  "document_id": "uuid",
  "file_name": "patient_p999.pdf",
  "status": "EXTRACTED",
  "page_count": 5,
  "message": "..."
}
```

`400` — not a PDF or exceeds size limit. `422` — PDF could not be parsed (empty, malformed, or scanned/image-only with no OCR fallback yet).

Planned for Phase 2/3 (not yet implemented): schema mapping to structured tables, database insertion, chunking, embedding, Qdrant indexing — see [DATA_FLOW.md](DATA_FLOW.md).

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
