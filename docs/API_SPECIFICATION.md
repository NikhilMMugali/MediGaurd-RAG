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

## Health

### `GET /health`
Implemented. Returns `{"status": "ok", "service": "MediGaurd RAG backend"}`. No authentication required.

## Planned — RAG (Phase 3)

### `POST /api/rag/query`
Request: `{ "question": "What is patient P001's diagnosis?" }` with bearer token.
Response: `{ "answer": "...", "citations": [...], "authorization_debug": {...} }` (debug block visible to ADMIN only, or behind a separate admin endpoint).

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
