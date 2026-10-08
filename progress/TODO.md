# MediGaurd RAG — TODO

## Immediate
- [x] Verify `scripts/index_knowledge.py` finished — 176,054/176,054 indexed — and live-tested doctor vs finance on the same patient/question over real HTTP
- [ ] Push to https://github.com/NikhilMMugali/MediGaurd-RAG.git — two tokens tried so far both got 403 (permission denied); needs a token with `repo` scope (classic) or explicit repo + Contents:Read-and-write (fine-grained)
- [ ] Switch to real PostgreSQL — brew finished installing postgresql@16; not yet migrated over (still on SQLite)
- [ ] Manual browser click-through of the frontend before the jury demo (no browser automation tool was available this session; verified via production build + dev-server transform + direct API/CORS checks instead)

## Frontend — remaining
- [ ] Admin retrieval-debug panel UI (backend already returns the `debug` block to ADMIN on `/api/rag/query` — just needs an expandable "Retrieval Details" section)
- [ ] Live ingestion status polling in the upload dialog (backend has RECEIVED→EXTRACTING→MAPPING→...→COMPLETED states on `ingestion_jobs`; dialog currently just shows the final result)
- [ ] A relevance score threshold on retrieval so an authorized-but-irrelevant top chunk doesn't get returned as if it answered the question (see Known Issues in PROGRESS.md)

## Phase 3 — remaining
- [ ] Optional reranking / hybrid lexical search (explicitly optional per spec — skip unless it demonstrably improves answers)
- [ ] Extend `knowledge_generator.py` to cover allergies/procedures/careplans/immunizations/imaging/devices/payers (currently: conditions/medications/observations/encounters/claims/claim_transactions) and re-run `scripts/index_knowledge.py`
- [ ] Query routing / domain classification (spec section 17) — not implemented; currently the authorization filter alone determines the retrievable set, semantic similarity determines relevance within it

## Known gaps to revisit (tracked in progress/DECISIONS.md and PROGRESS.md)
- [x] LLM calls fall back to a non-hallucinating extractive mode when no key is configured — `GROQ_API_KEY` now set, real generation is the normal path; fallback (`DevModeProvider`) only appears with an explicit "unavailable" message if the key is missing or the call fails
- [ ] Backfill `observation_category`/`record_date` into *existing* Qdrant payloads (currently only in SQL `knowledge_records`) so the general (no-patient-selected) retrieval path also gets category-aware filtering — `set_payload`, not a re-embed; low priority since the primary UX path always selects a patient first
- [ ] Qdrant embedded-local mode holds a file lock on `QDRANT_PATH` — only one process (API server or a script) can have it open at a time; fine for a single-demo-box setup, would need `QDRANT_MODE=server` for anything concurrent
- [ ] Smarter PDF extraction (current mapper is a rule-based "Label: Value" line parser; fine for the spec's sample document format, not for free-form scanned prose)
- [ ] `document_acls` is modeled but not yet populated or enforced anywhere — current authorization runs entirely on role + record_type/sensitivity + patient_assignments, which already covers every acceptance test; document-level ACLs would add per-document overrides on top of that if needed later
- [ ] Ambiguous new-patient matches (PDF upload) are created as new rows rather than flagged for review (no review UI yet)

## Housekeeping
- [x] Synthea CSV import verified against documented row counts
- [x] Idempotency verified for importer, knowledge-record generator, and Qdrant indexing (upsert on stable id)
- [x] 9 focused Phase 3 security tests passing against a real (temp) Qdrant collection, including the "security invariant" test (restricted content never reaches the LLM prompt)
