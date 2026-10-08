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

## Last Updated
2026-10-08
