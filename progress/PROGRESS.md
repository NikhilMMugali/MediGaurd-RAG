# MediGaurd RAG Progress

## Current Phase
Frontend (core flows implemented) — backend Phases 1-3 complete and verified live against the full real dataset

## Overall Status
IN PROGRESS

## Phase 1 — Backend
Complete. See git history / docs for detail. 9 tests.

## Phase 2 — Database
Complete. 18 Synthea tables + application/authorization/provenance tables (29 total), idempotent importer (row counts verified exact), Alembic migration, 176,054 knowledge records generated. 11 tests (cumulative).

## Phase 3 — Secure RAG
Complete (backend). Qdrant (embedded local mode), Sentence Transformers embeddings, `AuthorizationContext`/Qdrant-filter retrieval-time security boundary, `POST /api/rag/query` with citations + audit logging, LLM provider with extractive fallback. 20 tests (cumulative).

**All 176,054 knowledge records are now actually indexed in Qdrant** (the background job that was running at the end of the last session finished: `Done. 176054 points upserted. Collection count: 176054`, ~78 minutes CPU-bound on this machine).

**Live-verified end-to-end against the real dataset** (not just the fixture-based tests): asked the identical question ("What conditions does this patient have?") about the same real assigned patient as both `doctor01` and `finance01`. Doctor received clinical conditions/observations; Finance — same patient, same question — only ever retrieved claims/claim_transactions, never clinical content. This confirms the retrieval-time filter works correctly against the full real index, not only the small test fixtures.

## Frontend (NEW)
Status: CORE FLOWS IMPLEMENTED

### Stack
Vite + React + TypeScript + Tailwind CSS v3 + hand-written shadcn-style components (Button, Input, Select, Card, Badge, Avatar, Dialog, Progress, Textarea, Separator, Label) over Radix UI primitives + lucide-react icons. No component framework beyond that — kept lightweight per the brief.

### Completed
- [x] API client (`src/api/client.ts`) — token in sessionStorage, 401 → auto-logout, generic error messages (never raw server internals)
- [x] Auth state (`src/auth/AuthContext.tsx`) — login/logout/me, used by every page
- [x] Login page — username/password/role, "Use demo account" autofill per role (never bypasses backend validation)
- [x] App shell — sidebar with Patients/Assistant nav, role icon + name + department, logout
- [x] Patients dashboard — patient IDs only (no names/DOB/PII), status badges (Stable/Attention/No Recent Information) sourced from the new `/api/patients/{id}/status` endpoint, which reuses the exact same `retrieve_authorized_sources()` the chat endpoint uses — not a second independent "status AI" and not frontend-invented
- [x] Patient card click → opens Assistant with patient context chip
- [x] RAG chat — role-specific placeholder + quick prompts, renders answer + citations, distinct UI for DENIED ("Access restricted") and NO_AUTHORIZED_CONTEXT ("No authorized information found")
- [x] PDF upload dialog — gated to DOCTOR/NURSE/ADMIN in the UI (backend still enforces independently), shows processing state and the real backend response message, refreshes the patient list on success
- [x] Admin stats bar (patients/conditions/medications/claims/knowledge_records) — ADMIN role only, real backend numbers
- [x] CORS configured on the backend for `http://localhost:5173`
- [x] Production build verified clean (`npm run build`, no TS errors)
- [ ] Admin retrieval-debug panel UI (the API already returns the `debug` block to ADMIN on `/api/rag/query` — no page surfaces it yet)
- [ ] Ingestion status polling UI (upload dialog shows the final result; no live RECEIVED→EXTRACTING→...→COMPLETED progress stream yet — backend has the states, frontend doesn't poll them)

### New backend endpoints added for the frontend (reuse existing authorization/RAG, no new security logic)
- `GET /api/patients` — authorized patient ids only, scoped identically to what RAG would retrieve for that user (`assigned` for DOCTOR/NURSE from real `patient_assignments`, `all`-paginated otherwise)
- `GET /api/patients/{id}/status` — deterministic, evidence-based status derived from the same retrieval pipeline (condition record found → "Attention"; none → "Stable"; retrieval denied/empty → "No Recent Information")
- `app/rag/pipeline.py` refactored to expose `retrieve_authorized_sources()` so both the chat endpoint and the status endpoint share one retrieval-authorization code path rather than duplicating it

### Frontend Verification
- [x] Production build succeeds, no TypeScript errors
- [x] Vite dev server serves and transforms the module graph correctly
- [x] CORS preflight from `localhost:5173` to the backend succeeds
- [ ] Manual in-browser click-through (no browser automation tool was available in this session — verified via build + dev-server module transform + direct API checks instead; a human should still click through once before the jury demo)

## Known Issues
- GitHub push still blocked: both tokens provided so far got a 403 ("Permission ... denied to NikhilMMugali") — token likely needs `repo` scope (classic) or explicit repository + Contents:Read-and-write access (fine-grained). Everything is committed locally and ready the instant a working token is provided.
- PostgreSQL 16 finished installing via Homebrew (background job completed) but the project has not been switched over yet — still running on SQLite + embedded Qdrant. Not blocking; do before the final demo per the original Phase 2 plan.
- `backend/data/qdrant` and `frontend/node_modules`, `frontend/dist` are gitignored (build/test artifacts, not source).
- The general (no-patient-selected) retrieval path narrows by record type via query classification but not by observation category — that metadata lives only in SQL `knowledge_records`, not yet backfilled into existing Qdrant payloads. Not a problem for the primary UX path (patient always selected first), see progress/DECISIONS.md.

## RAG quality fix (2026-10-08)
Fixed the "answers look like raw database dumps" complaint end to end:
- Real LLM generation (Groq, `openai/gpt-oss-120b`) replaces the extractive fallback as the normal path; the fallback (renamed `DevModeProvider`) now only ever appears with an explicit `[DEV MODE] ... unavailable` message, never disguised as a real answer.
- Deterministic query classification (`app/rag/query_classification.py`) narrows retrieval to the record type(s)/observation-category the question is actually about, always intersected with — never widening — the role's authorization.
- Recency-aware ranking: `knowledge_records.record_date`/`observation_category` (backfilled for all 176k existing rows) let "recent observations" blend relevance with how recent a record actually is, instead of pure cosine similarity pulling in an old, unrelated-but-similar-worded row.
- Citations resolve the real file name and record date instead of a raw UUID.
- Full before/after and the 10-point focused verification are in progress/DECISIONS.md's "RAG quality fix" entry.

## Latest Commit
(pending — see Next Task)

## Next Task
1. Commit and push both the earlier performance fix and this RAG quality fix once a working GitHub token is available.
2. Manual click-through in an actual browser before the jury demo (login per role, patient click → chat, upload → immediately queryable, role-switch denial).
3. Optional: admin retrieval-debug panel UI, ingestion status polling, switch to real PostgreSQL, backfill observation_category into existing Qdrant payloads for the general (no-patient) retrieval path.

## Clean dataset + hybrid RAG + chat quality + UI/UX pass (2026-10-08)

### Data Refinement
- [x] Clean 100-patient dataset (`scripts/build_clean_dataset.py` — deterministic, no RNG)
- [x] Synthetic demographics (fictional name pairs, SSN/DRIVERS/PASSPORT dropped)
- [x] Observation filtering (RAG knowledge layer excludes survey/social-history/uncategorized; structured DB keeps everything)
- [x] Finance cleanup (claims/claims_transactions/payers/payer_transitions filtered to the 100 patients; reference tables kept whole)
- [x] Referential validation (`scripts/validate_clean_dataset.py`)
- [x] Database reimport (fresh DB from `data/clean/`, old 108-patient/176k-record DB preserved as `medigaurd_dev.db.pre_clean_backup`)
- [x] Knowledge regeneration (added allergy/procedure generators; observation generator now category-filtered)
- [x] Qdrant reindex (old `data/qdrant` preserved as `data/qdrant.pre_clean_backup`, fresh collection built from the new knowledge records)

### Hybrid RAG
- [x] Query routing (`app/rag/query_classification.py` now returns a `route`: structured/summary/semantic)
- [x] Structured exact retrieval (`app/rag/structured_answers.py` — identity, medication, condition, allergy, procedure, encounter, finance outstanding/payer, recent observations — zero LLM calls, can't hallucinate)
- [x] Semantic retrieval (unchanged Qdrant+LLM path for open-ended/contextual questions)
- [x] Hybrid/summary (deterministic cross-domain rollup, also no LLM)
- [x] Patient-context handling (`Patient.display_id` "Pxxx" + `resolve_patient_reference()`; frontend resends the selected patient with every message, so pronoun follow-ups like "what about his allergies?" resolve correctly without any server-side session state)
- [x] Recency handling (date-aware structured retrieval for "recent observations"; relevance+recency blend retained for the semantic path)
- [x] Answer synthesis (structured routes build markdown directly; semantic path's LLM prompt unchanged from the prior RAG-quality-fix session)
- [x] Citation validation (`_validate_citations` strips any `[SOURCE_n]` the LLM cites beyond what was actually retrieved)

### UX
- [x] Markdown rendering (`react-markdown` + `remark-gfm` in `ChatMessage.tsx`, replacing raw `**bold**`/`|table|` text)
- [x] Better answer layout (narrower max-width, lighter source separation instead of a boxed list)
- [x] Better citation display (grouped by record type + date instead of one row per source; real file names resolved for PDF citations)
- [x] Patient ID cleanup (dashboard/chip/input placeholder show `Pxxx`, never the raw UUID)
- [x] Chat spacing (tightened message/source spacing)
- [x] Loading state ("MediGaurd is thinking..." + spinner, was "...retrieving authorized information...")
- [x] Patient card refinement (no more UUID truncation; status still backend-derived)
- [ ] Upload UX refinement (not touched this pass — existing dialog/polling behavior kept as-is)

See progress/DECISIONS.md for the full architecture writeup and docs/CLEAN_DATASET.md for the dataset build details.

## 2026-10-09 — UI/UX redesign + Document Intelligence + Hospital Insights

### Navigation / UI redesign
- [x] React Router wired up for real (previously local `tab` state) — `/patients`, `/assistant/chat`, `/assistant/documents`, `/assistant/insights`
- [x] Sidebar redesigned: General/AI Assistant grouped nav, active-route highlighting, collapsible AI Assistant group, Document Intelligence link hidden from roles that can't use it (FINANCE/RECEPTION)
- [x] Mobile layout: sidebar hidden below `md`, replaced with a top bar (menu toggle + page title + role badge) and a slide-out overlay nav
- [x] Selected-patient context now flows through React Router's `Outlet` context instead of prop-drilling from a single top-level component

### Document Intelligence (new, `/assistant/documents`)
- [x] Fixed a real pre-existing bug: `SourceDocument.patient_id` was never actually set on upload — document-level authorization and patient filtering were silently broken against this column
- [x] Fixed OCR handling: a scanned/no-text PDF previously raised a 422 with **nothing persisted at all**; now the document and file bytes are saved with `status=NEEDS_REVIEW` and a clear explanation, matching the "preserve the upload safely" requirement
- [x] New endpoints: `GET /api/documents` (authorized list), `GET /api/documents/limits`, `GET /api/documents/{id}/status`, `POST /api/documents/query` (document-scoped Q&A) — all in `app/api/upload.py`, reusing the existing upload router/role gate
- [x] `app/rag/pipeline.py::run_query` gained an optional `document_id` param, threaded into both the Qdrant filter (`build_retrieval_filter`) and the known-patient SQL fast path (`_retrieve_for_known_patient`) — document Q&A reuses the exact same authorization + citation-validation + audit-log code as chat, scoped additionally to one document's chunks
- [x] Frontend: `DocumentUploader` (drag-and-drop, backend-driven size limit), `DocumentProcessingStatus` (reads the persisted record, not an optimistic guess), `DocumentList` (search by filename/patient id), `DocumentQuestionPanel` (per-document chat reusing `ChatMessage`)
- [x] Hardened `_validate_citations`' regex to also catch full-width bracket citations (`〔SOURCE_1〕`) the LLM occasionally emits — found during live testing, same function used by chat, documents, and insights

### Hospital Insights (new, `/assistant/insights`)
- [x] New `app/rag/insights.py` — every metric is a real SQL aggregate, scoped through the exact same `AuthorizationContext` as chat/documents (role-wide for FINANCE/RECEPTION, `assigned_patient_ids`-filtered for DOCTOR/NURSE, system-wide for ADMIN); a role with nothing to summarize gets an honest empty-state note, never a fabricated zero
- [x] `POST /api/insights/query` packages those metrics as a single `[SOURCE_1]` evidence block — the LLM narrates, it structurally cannot cite a second (invented) source; the no-metrics case never calls the LLM at all
- [x] Frontend: KPI cards, a plain CSS bar-list breakdown (no charting library added), and an "Ask about these insights" panel

### Verification
- [x] Live end-to-end smoke test against the real running backend: login as all 5 roles, insights overview per role, a real PDF upload → list → status → document-scoped Q&A with a correct citation, and authorization denials (unassigned nurse → 403, finance → 403) — see this session's transcript
- [x] 12 new focused backend tests (`tests/test_documents.py`, `tests/test_insights.py`) covering the authorization properties above; full suite run with the dev server stopped first (embedded Qdrant's single-writer lock) — **42/42 passing, zero regressions**
- [x] Frontend production build (`npm run build`) and lint (`npm run lint`) both clean
- [ ] Manual browser click-through of the new UI not done this pass either — still no browser automation tool available; verified via build + live curl smoke tests instead (see TODO.md)

## 2026-10-09 (later) — PDF retrieval fix + citation PDF viewer

Reproduced a real reported bug (uploaded lab report → "tell me about <patient>" → "no information found" with unrelated patients' records shown as sources) using a synthetic fixture matching the real document's structure, traced to four compounding root causes, and fixed all four. Full writeup: `progress/DECISIONS.md` "PDF retrieval fix."

### Root-cause fixes
- [x] Narrative page-text fallback (`record_type="document"`) — every PDF page is now indexed regardless of whether its content matches any structured Label:Value category; previously a lab-report-shaped document produced zero knowledge_records and was completely unretrievable
- [x] Field-boundary-aware identity extraction fallback — recovers a clean name/registration-id/gender from a real-world header line that packs two fields onto one line ("Name : X Reg. No. : Y"), which the naive per-line parser garbled
- [x] Free-text patient-name resolution (`_resolve_patient_by_name`) — a question naming a patient by name, not just by Pxxx id, now resolves; previously had no resolution path at all and silently searched unscoped across every patient
- [x] Relevance-threshold bug fixed (`score_threshold or None` was silently discarding the configured floor whenever it was `0.0`, which was also the default) — default raised to `0.35`; applied to both the Qdrant search branch and the known-patient SQL fast path's ranking

### Also fixed
- [x] Duplicate-upload handling — no longer a dead-end 409; a duplicate with zero actual knowledge records is repaired in place against the same document_id, not re-reported as a confusing "already uploaded, COMPLETED"
- [x] Citations gained `document_id` + `evidence_text` fields (needed for the viewer below)

### New: citation → PDF viewer (Clinical Chat)
- [x] `GET /api/documents/{document_id}/file` — authenticated, `_document_authorized`-checked PDF streaming endpoint
- [x] `PdfViewerPanel.tsx` (react-pdf/pdf.js) — opens on citation click, jumps to the cited page, zoom/page controls, attempts text-layer highlighting of the citation's evidence text (skipped for whole-page narrative citations — shows full text in the panel instead)
- [x] `ChatMessage.tsx` citations are now clickable when PDF-backed (`document_id` present)

### Verification
- [x] Full end-to-end reproduction against a fresh synthetic fixture: upload → correct name/gender extraction → free-text name question → ANSWERED with correct citation (document_id, page, evidence_text) → authenticated file-fetch returns byte-identical PDF
- [x] Authorization re-verified: unassigned nurse gets DENIED for the same name-based question and 403 on the file endpoint directly
- [x] 6 new backend tests (`tests/test_pdf_retrieval_fix.py`, plus 2 rewritten duplicate-upload tests in `tests/test_upload.py`) — **49/49 backend tests passing**, dev server stopped first (Qdrant lock)
- [x] Frontend production build clean (`npm run build`)
- [ ] Manual browser click-through of the new PDF viewer not done — no browser automation tool available; verified via live API calls (byte-identical file fetch) and clean build instead

### Known limitation
A patient record created before this fix keeps whatever garbled name the old parser stored — no data-migration script re-runs identity extraction against already-ingested patients. Re-uploading an old document only repairs its indexing state, not a patient row's already-stored name fields.

## Last Updated
2026-10-09
