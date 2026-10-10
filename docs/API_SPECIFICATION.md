# MediGuard RAG — API Specification

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

`400` — not a PDF or exceeds size limit. `422` — PDF could not be parsed at all (empty/malformed file).

**Duplicate file hash — no longer a dead-end `409`** (2026-10-09 fix, see `docs/DECISIONS.md` "PDF retrieval fix"). A duplicate now returns `200` with the *real* state of the already-existing document: if it already has indexed knowledge records, the response reports that (`status`, `chunks_indexed` from the existing document, same `document_id`); if it has none (it predates this fix, or indexing previously failed), the server repairs it in place — generates and indexes its narrative knowledge records against the *same* `document_id` — before responding, rather than returning a second confusing dead-end. See `app.api.upload._handle_duplicate_upload`.

### `GET /api/documents/limits`
Implemented. Returns `{"max_upload_size_mb": 20}` from server config, so the frontend's client-side size check is never a hardcoded guess.

### `GET /api/documents`
Implemented. Lists only documents the caller is authorized to see: every document for `ADMIN`; for `DOCTOR`/`NURSE`, documents they uploaded themselves plus documents belonging to a patient currently assigned to them (`app.api.upload._document_authorized`). Response: `{"documents": [{"document_id", "file_name", "status", "document_type", "patient_id", "uploaded_by", "created_at"}], "total": n}` — `patient_id` is always the display id, `uploaded_by` the uploader's full name, never raw internal ids.

### `GET /api/documents/{document_id}/status`
Implemented. `403` if the caller isn't authorized for that document (same rule as the list endpoint). Returns the persisted, authoritative processing state — `status`, `page_count` (computed live from the stored PDF), `records_created`, `chunks_created`, `error_message` — never an optimistic client-side guess.

### `GET /api/documents/{document_id}/file`
Implemented (2026-10-09, for the PDF citation viewer — section 10B). Streams the original PDF bytes (`Content-Type: application/pdf`). Authenticated and authorization-checked identically to every other document endpoint — `403` before the file is touched if the caller isn't authorized for that document; `404` if no file was ever stored. There is no unauthenticated static route for uploaded documents; the frontend fetches this with its `Authorization` header and turns the response into a blob object URL, never a plain `<iframe src>`/`<a href>`.

### `POST /api/documents/query`
Implemented — secure, document-scoped Q&A. Body: `{"document_id": "...", "question": "..."}`. `403` before any retrieval if the document isn't authorized for the caller. Internally calls `app.rag.pipeline.run_query(..., document_id=...)`, which adds a `source_document_id` condition to the Qdrant filter (or the SQL fast-path query) on top of every normal authorization condition — so even an authorized user only ever gets answers grounded in *that* document's own chunks, never another document's. Response shape matches `/api/rag/query`.

### Citation shape (both `/api/rag/query` and `/api/documents/query`)
Each citation now also carries `document_id` (the `source_documents.id` to pass to `GET /api/documents/{id}/file`, `null` for a Synthea-derived citation with no PDF) and `evidence_text` (the actual retrieved text this citation is grounded in, used by the frontend to locate/highlight the cited passage on the opened page). Added 2026-10-09 — see "PDF retrieval fix" in `docs/DECISIONS.md`.

## Patients (added for the frontend — reuses existing authorization/RAG, no new security logic)

### `GET /api/patients?limit=20&offset=0`
Implemented — `backend/app/api/patients.py`. Returns only patient ids the current user is authorized to see, using the same `AuthorizationContext` the RAG pipeline uses. `scope` is `"assigned"` (DOCTOR/NURSE, from real `patient_assignments`) or `"all"` (paginated, for roles with no patient-level scoping).

### `GET /api/patients/{patient_id}/status`
Implemented. Calls the same `retrieve_authorized_sources()` the chat endpoint uses, then classifies deterministically: an authorized `condition` record found → `"Attention"`; none → `"Stable"`; retrieval denied or empty → `"No Recent Information"`. Never a second, independent "status AI."

### `GET /api/patients/{patient_id}/summary`
Implemented (Phase 2). Row counts only (conditions/medications/encounters) — no clinical content.

## Health

### `GET /health`
Implemented. Returns `{"status": "ok", "service": "MediGuard RAG backend"}`. No authentication required.

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


## OCR image upload (Document Intelligence → "Upload Image using OCR")

Image endpoints live beside the PDF ones and share the same document authorization (`_document_authorized`): the uploader, an assigned clinician, or an admin. Roles: DOCTOR / NURSE / ADMIN to upload; FINANCE and RECEPTION receive `403`.

### `POST /api/documents/upload-image`
Multipart: `file` (JPG / JPEG / PNG / WEBP) and optional form field `patient_id` (display id, e.g. `P001`). The server — never the client — decides authorization: a `patient_id` the caller is not assigned to is `403`, an unknown one `404`.

Validation trusts the decoded content, not the extension or declared type: `400` unsupported type or over the size limit; `422` empty/corrupt/unreadable, or more than the pixel cap (decompression-bomb guard, checked before decoding).

Response `200`: `{document_id, file_name, status, message, patient_id, duplicate}`. The response returns as soon as the image is validated and stored (`status: "VALIDATING"`); OCR and indexing continue in the background and are observed through `GET /api/documents/{id}/status`. Stages, in order and each persisted as it begins: `VALIDATING → OCR_PROCESSING → IDENTIFYING_PATIENT → MAPPING → INDEXING → COMPLETED`, or stopping at `NEEDS_REVIEW` / `FAILED`. `COMPLETED` is set only after the chunks were indexed **and read back** from Qdrant.

`NEEDS_REVIEW` means a person must act and **nothing has been indexed**: OCR confidence/text too low (`ocr_quality: "poor"`; re-upload a clearer image), or the patient could not be established safely (ambiguous, a near-miss spelling of an existing patient, a patient the uploader may not access, or an explicitly selected patient whose name contradicts the image). Review messages never reveal the existence or id of a patient the uploader cannot access.

**Duplicates** (same bytes) return `200` with `duplicate: true` and the real state, after verifying the stored file, OCR text, patient link, knowledge records, and the vectors actually present in Qdrant; any missing piece is repaired in place (never a collection rebuild, never duplicate chunks).

### `GET /api/documents/{document_id}/ocr`
The extracted text with per-line `confidence` and `box` (`[x1,y1,x2,y2]` in the original image's pixels, EXIF orientation applied), plus `quality` (`good|fair|poor`), `mean_confidence`, and `problem`. Authorization-checked like the file itself; available for an image in review. `404` for a PDF.

### `POST /api/documents/{document_id}/confirm-patient`
Body `{ "patient_id": "P007" }`. Resolves an image in `NEEDS_REVIEW` for an identity reason. The caller must be able to see the document **and** be assigned to the target patient (or be admin); `409` if the image is not awaiting confirmation or its text is unreadable (a patient choice cannot make unreadable text trustworthy). Indexing then runs through the normal pipeline.

### Changed existing endpoints (PDF behaviour unchanged)
- `GET /api/documents/{id}/file` serves an OCR image with its real media type (`image/jpeg|png|webp`), `Content-Disposition: inline`, and `X-Content-Type-Options: nosniff`.
- `GET /api/documents/{id}/status` adds `source_type`, `ocr_quality`, `ocr_mean_confidence`; `GET /api/documents` adds `source_type` (`UPLOADED_PDF` | `OCR_IMAGE`).
- RAG citations add `source_type: "OCR_IMAGE"` (with `page: null` — an image has no pages), `highlight_text` (the supporting lines), and `ocr_confidence`.
