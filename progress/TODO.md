# MediGuard RAG — TODO

## Immediate
- [x] Rebuilt on the clean 100-patient dataset (`data/clean/`) — old 108-patient/176,054-record DB and Qdrant collection kept as `.pre_clean_backup` — reindexed from 156,707 knowledge records
- [x] Push to https://github.com/NikhilMMugali/MediGaurd-RAG.git — pushed to `main` (a fresh PAT with `repo` scope fixed the earlier 403s); UI/UX redesign + Document Intelligence + Hospital Insights commits not yet pushed as of this entry — see "next push" below
- [ ] Switch to real PostgreSQL — brew finished installing postgresql@16; not yet migrated over (still on SQLite)
- [ ] Manual browser click-through of the frontend before the jury demo (no browser automation tool was available this session; verified via production build + dev-server transform + live curl/API smoke tests instead)

## Next push (2026-10-09 UI/UX + Document Intelligence + Hospital Insights + PDF retrieval fix)
- [ ] Commit and push this iteration's changes (sidebar/routing redesign, Document Intelligence, Hospital Insights, the `SourceDocument.patient_id`/OCR-persistence/uploader-assignment fixes, the PDF retrieval root-cause fixes + citation PDF viewer, 18 new tests, doc updates above)

## 2026-10-10 master audit prompt — done this pass vs. not started
- [x] Phase 5 (query classification robustness) — 7 reproduced real failures, 6 fixed, 1 documented as an intentional bounded gap; new 40-case eval suite; see progress/DECISIONS.md "Query classification robustness pass"
- [x] Phase 4 (Synthea dataset cleaning) — verified already correct from a prior session, not re-done; validator passes
- [x] Phase 9 (DB/security) — bounded spot-check only (SQLi, CORS, secret-key handling, patient-FK indexing) — no issues found; not a full audit
- [ ] Phase 1 (full written repo audit), Phase 2 (systematic dedup/dead-code sweep beyond the one spot-check above), Phase 3 (no destructive dataset work needed), Phase 6 (RAG quality beyond prior sessions' fixes), Phase 7 (PDF robustness beyond prior sessions' fixes), Phase 8 (frontend/UI-UX polish), Phase 9 (performance profiling/load testing), Phase 10 (broader eval suite — PDF ingestion/retrieval/citation/authorization/dataset-integrity beyond query classification) — not attempted this pass; the 14-phase prompt's full scope was treated as multiple future iterations, not one, per the final report's explicit scoping note

## 2026-10-10 verification pass — 3 real bugs found and fixed against the live app
- [x] Structured-intent miss (e.g. "what about his vitamin D result?" for a PDF-only patient) silently returned NO_AUTHORIZED_CONTEXT instead of falling back to semantic retrieval over the document's narrative chunks — fixed in `app/rag/pipeline.py::run_query`; see progress/DECISIONS.md "Verification pass"
- [x] `PdfViewerPanel.tsx` could show a stale page number from the previously-opened document when a structured-answer citation (page=None) was clicked next — fixed
- [x] `AssistantPanel.tsx` (Clinical Chat) didn't clear its chat transcript/active citation when switching patients, unlike `DocumentQuestionPanel.tsx`'s equivalent — fixed to match the existing correct pattern
- [x] Zero test coverage on `GET /api/documents/{document_id}/file` (the citation viewer's file-serving endpoint) despite it being the exact "guessing a document ID" security path the PDF-viewer feature's acceptance criteria call out — 6 tests added, including a path-traversal attempt
- [ ] No server-side multi-turn conversation memory — a follow-up relying on pronoun resolution against the previous turn (e.g. "Which page shows that?") doesn't resolve correctly; documented as a known architectural limitation, not fixed this pass (would be new feature work)
- [ ] Manual browser click-through still required — no browser automation tool is available in this environment (reconfirmed via ToolSearch); see the session's final report for the specific checklist

## 2026-10-10 citation/PDF-link deep-dive — traced the whole pipeline, added the first frontend tests
- [x] Traced the full citation-to-PDF flow end to end (backend citation construction → ChatMessage click gating → AssistantPanel state → PdfViewerPanel fetch/lifecycle → file endpoint) — no further core citation-correctness bugs found; the click-gating on `document_id`, the Synthea-native-rows-never-have-a-document_id invariant, and the fetch-cancellation guard were all already correct, now locked in by tests
- [x] `PdfViewerPanel.tsx` had no `onLoadError` — added, wired into the existing error state (react-pdf's own default already prevented a true infinite spinner, but this gives a consistent, styled error)
- [x] `GET /api/documents/{id}/file` sent `Content-Disposition: attachment` (Starlette's default) instead of `inline` — fixed; verified live against the real demo PDF
- [x] Added the repository's first-ever frontend test suite (Vitest + React Testing Library, `frontend/vitest.config.ts`) — 10 new tests across `ChatMessage.test.tsx` and `PdfViewerPanel.test.tsx` covering citation click handling, stale-page prevention, document-switch cleanup, load-failure error state, and the slow-stale-fetch race condition
- [x] Caught and fixed a real regression introduced by this pass's own first attempt at the Vitest setup: importing `defineConfig` from `"vitest/config"` inside `vite.config.ts` broke `tsc -b` (the production build) with a cross-package Vite-Plugin-type mismatch — caught by rerunning the build immediately, fixed by moving the test config into its own `vitest.config.ts` outside every tsconfig's `include`
- [x] 3 new backend citation-integrity tests (`test_rag_pipeline.py`, `test_documents.py`) — structured citations have `document_id=None`, semantic citations preserve `document_id`/`page`/`evidence_text`/`patient_id` unchanged, and two real documents' bytes are never cross-served
- [x] Backend 106/106, frontend build + lint + 10/10 vitest all passing — all reverified after the above regression was fixed, not assumed

## Frontend — remaining
- [ ] Admin retrieval-debug panel UI (backend already returns the `debug` block to ADMIN on `/api/rag/query` — just needs an expandable "Retrieval Details" section)
- [x] Live ingestion status display — `GET /api/documents/{id}/status` + `DocumentProcessingStatus.tsx` on the new Document Intelligence page reads the persisted `ingestion_jobs` state rather than only the upload response; the original small `UploadDialog` on the Patients page still just shows the final result (not revisited — Document Intelligence is the primary upload surface now)
- [x] A relevance score threshold on retrieval so an authorized-but-irrelevant top chunk doesn't get returned as if it answered the question — `RAG_SCORE_THRESHOLD` default raised to 0.35 and a falsy-coalescing bug that silently disabled it fixed (2026-10-09, see progress/DECISIONS.md "PDF retrieval fix")
- [ ] The citation → PDF viewer is only wired into Clinical Chat (`AssistantPanel.tsx`); Document Intelligence's own per-document Q&A panel (`DocumentQuestionPanel.tsx`) doesn't show it yet — that page's list/Q&A grid would need restructuring to fit a third column

## Phase 3 — remaining
- [ ] Optional reranking / hybrid lexical search (explicitly optional per spec — skip unless it demonstrably improves answers)
- [ ] Extend `knowledge_generator.py` to cover careplans/immunizations/imaging/devices/payers (allergies and procedures done this pass; these remain structured-DB-queryable but not semantically indexed)
- [x] Query routing / hybrid retrieval — `app/rag/query_classification.py` + `app/rag/structured_answers.py`: exact-fact questions (identity, medication, condition, allergy, procedure, encounter, finance, recent observations) now answer from a deterministic SQL lookup, never Qdrant/LLM; open-ended questions still use semantic retrieval
- [ ] Hospital-policy document corpus (infection-control guidance etc.) — deliberately not built this pass, see progress/DECISIONS.md "Scope decision"

## Known gaps to revisit (tracked in progress/DECISIONS.md and PROGRESS.md)
- [x] LLM calls fall back to a non-hallucinating extractive mode when no key is configured — `GROQ_API_KEY` now set, real generation is the normal path; fallback (`DevModeProvider`) only appears with an explicit "unavailable" message if the key is missing or the call fails
- [ ] Backfill `observation_category`/`record_date` into *existing* Qdrant payloads (currently only in SQL `knowledge_records`) so the general (no-patient-selected) retrieval path also gets category-aware filtering — `set_payload`, not a re-embed; low priority since the primary UX path always selects a patient first
- [ ] Qdrant embedded-local mode holds a file lock on `QDRANT_PATH` — only one process (API server or a script) can have it open at a time; fine for a single-demo-box setup, would need `QDRANT_MODE=server` for anything concurrent
- [ ] Smarter PDF extraction (current mapper is a rule-based "Label: Value" line parser; fine for the spec's sample document format, not for free-form prose)
- [ ] OCR for scanned/image-only PDFs — still not implemented; such an upload is now persisted with `status=NEEDS_REVIEW` and a clear explanation instead of being silently discarded (2026-10-09 fix), but there is still no path from "scanned PDF" to "extractable text"
- [ ] `document_acls` is modeled but not yet populated or enforced anywhere — current authorization runs entirely on role + record_type/sensitivity + patient_assignments, which already covers every acceptance test; document-level ACLs would add per-document overrides on top of that if needed later
- [ ] Ambiguous new-patient matches (PDF upload) are created as new rows rather than flagged for review (no review UI yet)
- [ ] No data-migration script to re-run identity extraction against patients created before the 2026-10-09 identity-extraction fix — such a patient keeps whatever garbled name the old per-line-only parser stored; re-uploading the same document only repairs its indexing state, not the patient row's name fields
- [ ] Text-layer citation highlighting only engages for evidence under 500 characters — a whole-page narrative citation (the common case for a document with no structured fields, e.g. a lab report) opens the right page but doesn't highlight a specific passage, since "highlighting" its own full-page evidence_text would mean highlighting the entire page

## Housekeeping
- [x] Synthea CSV import verified against documented row counts
- [x] Idempotency verified for importer, knowledge-record generator, and Qdrant indexing (upsert on stable id)
- [x] 9 focused Phase 3 security tests passing against a real (temp) Qdrant collection, including the "security invariant" test (restricted content never reaches the LLM prompt)


## 2026-10-10 OCR image upload — done / not done
- [x] Local OCR (RapidOCR) for JPG/PNG/WEBP; resumable background pipeline with real stages; identity matching with review states; chunks/embeddings/Qdrant via the existing services; image citations + viewer with real OCR boxes; two-tab Document Intelligence; docs updated (README setup, API spec, DATA_FLOW, SECURITY, DECISIONS)
- [ ] OCR for scanned/image-only **PDF pages** (still saved as NEEDS_REVIEW)
- [ ] Structured SQL mapping from OCR text — deliberately off until there is a human review step for it
- [ ] Re-OCR / "retake" flow for a low-quality image (today: upload a clearer image)
- [ ] Handwriting, non-English text, multi-image documents, skew correction beyond EXIF — untested/unsupported
- [ ] Real phone-photo and scanner samples to measure accuracy (only synthetic rendered images were tested)
- [ ] Cross-browser check (Chromium only so far); OCR of very large concurrent batches
- [ ] Remove the synthetic dev patient `P107` and its image if a clean demo database is wanted
