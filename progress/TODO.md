# MediGaurd RAG — TODO

## Immediate
- [ ] Verify `scripts/index_knowledge.py` finished and the Qdrant collection count matches `knowledge_records` count; run the acceptance-test questions live over HTTP against real Synthea data
- [ ] Push to https://github.com/NikhilMMugali/MediGaurd-RAG.git — blocked on credentials (no `gh` CLI, SSH key, or stored HTTPS creds on this machine); user chose to skip for now
- [ ] Get a real PostgreSQL running locally (brew build was still compiling last checked, or install Docker) and re-point `DATABASE_URL`; re-run migrations/import/seed/knowledge-gen/indexing against it

## Phase 3 — remaining
- [ ] Frontend: login page, dashboard/chat, upload UI with ingestion progress, admin debug view (the API already returns the debug block to ADMIN on `/api/rag/query` — there's just no page for it yet)
- [ ] Optional reranking / hybrid lexical search (explicitly optional per spec — skip unless it demonstrably improves answers)
- [ ] Extend `knowledge_generator.py` to cover allergies/procedures/careplans/immunizations/imaging/devices/payers (currently: conditions/medications/observations/encounters/claims/claim_transactions) and re-run `scripts/index_knowledge.py`
- [ ] Query routing / domain classification (spec section 17) — not implemented; currently the authorization filter alone determines the retrievable set, semantic similarity determines relevance within it

## Known gaps to revisit (tracked in progress/DECISIONS.md and PROGRESS.md)
- [ ] LLM calls fall back to a non-hallucinating extractive mode (top chunk, verbatim, cited) when no `GROQ_API_KEY`/`OPENAI_API_KEY`/`LLM_API_KEY` is set — add a real key before the final demo for more fluent multi-source answers
- [ ] Qdrant embedded-local mode holds a file lock on `QDRANT_PATH` — only one process (API server or a script) can have it open at a time; fine for a single-demo-box setup, would need `QDRANT_MODE=server` for anything concurrent
- [ ] Smarter PDF extraction (current mapper is a rule-based "Label: Value" line parser; fine for the spec's sample document format, not for free-form scanned prose)
- [ ] `document_acls` is modeled but not yet populated or enforced anywhere — current authorization runs entirely on role + record_type/sensitivity + patient_assignments, which already covers every acceptance test; document-level ACLs would add per-document overrides on top of that if needed later
- [ ] Ambiguous new-patient matches (PDF upload) are created as new rows rather than flagged for review (no review UI yet)

## Housekeeping
- [x] Synthea CSV import verified against documented row counts
- [x] Idempotency verified for importer, knowledge-record generator, and Qdrant indexing (upsert on stable id)
- [x] 9 focused Phase 3 security tests passing against a real (temp) Qdrant collection, including the "security invariant" test (restricted content never reaches the LLM prompt)
