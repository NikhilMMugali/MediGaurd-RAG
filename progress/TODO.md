# MediGaurd RAG — TODO

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
