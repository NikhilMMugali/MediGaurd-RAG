# MediGaurd RAG — Data Flow

> **Implementation status (2026-10-09):** all 14 steps below are implemented end-to-end in a single upload request (`backend/app/api/upload.py`, `backend/app/ingestion/pdf_mapper.py`, `backend/app/rag/indexing.py`) — a successfully-mapped PDF is queryable immediately, no separate script run needed. Step 7's "structured info extraction" is a rule-based "Label: Value" line parser, not an LLM call — see progress/DECISIONS.md.

## PDF ingestion pipeline

```text
1. UPLOAD                multipart POST, role-gated (DOCTOR/NURSE/ADMIN)
2. FILE VALIDATION       content-type/extension check, size limit        [implemented]
3. HASH / DUPLICATE CHECK  sha256 of file bytes against source_documents [implemented — duplicate file hash rejected with 409]
4. PDF TEXT EXTRACTION   PyMuPDF per-page text; pdfplumber for tables    [implemented]
5. PAGE PRESERVATION    page_number kept on every extracted unit         [implemented]
6. SECTION/TABLE DETECTION  heading/table detection                      [not yet — current parser matches "Label: Value" lines directly, see progress/DECISIONS.md]
7. STRUCTURED INFO EXTRACTION  rule-based "Label: Value" line parser     [implemented — app/ingestion/pdf_mapper.py::extract_patient_document_data]
8. SCHEMA MAPPING        map to patients/conditions/medications/allergies/procedures/encounters/claims [implemented — app/ingestion/pdf_mapper.py::map_to_database]
9. VALIDATION            Pydantic intermediate schema (app/schemas/pdf_normalization.py) [implemented]
10. DATABASE INSERTION   insert rows, stamped with source_type=UPLOADED_PDF + source_document_id [implemented; new-patient dedup via external_patient_id/name]
11. SCHEMA-AWARE KNOWLEDGE GENERATION  atomic + narrative chunks          [implemented for Synthea data (scripts/generate_knowledge_records.py, from the clean 100-patient dataset — see docs/CLEAN_DATASET.md for current counts) and for uploaded-PDF rows (app/ingestion/pdf_mapper.py — a knowledge_records row is created inline as each structured row is mapped, not a separate pass)]
12. EMBEDDING            EmbeddingProvider                                [implemented — app/api/upload.py calls app/rag/indexing.py::index_records inline, in the same request, right after the structured rows commit]
13. QDRANT UPSERT        chunk + full security metadata payload          [implemented — same call; a failure here is caught and deferred (job.error_message), never fails the already-committed upload]
14. READY FOR RAG        immediately queryable                           [implemented — no app restart or separate script run needed; verified live via POST /api/documents/query and POST /api/rag/query]
```

Each step's failure mode must produce a clear `ingestion_jobs.status = FAILED` (a malformed/empty file, or extracted content that fails DB mapping) with a reason, not a silent partial result — except a scanned/image-only PDF (no extractable text), which is a different, expected case: `status = NEEDS_REVIEW`, not `FAILED`. The file and its `source_documents` row are still persisted (storage_path written, hash recorded) so nothing is lost; there is simply no extractable text to map or index yet. Status values in practice: `RECEIVED, EXTRACTING, MAPPING, CHUNKING, COMPLETED, NEEDS_REVIEW, FAILED`.

## OCR scope (section 5I)

The current pipeline is text-extraction only (PyMuPDF). There is no OCR fallback wired up. `app/ingestion/pdf_extractor.py::extract_pdf` detects a page with fewer than `MIN_TEXT_CHARS_PER_PAGE` characters of extracted text as non-text; if *every* page falls under that threshold, `PdfExtractionResult.is_text_extractable` is `False` and `app/api/upload.py` marks the upload `NEEDS_REVIEW` instead of attempting to map or index empty content. This is never silently reported as a successful, fully-indexed upload — the UI's Document Intelligence page shows `NEEDS_REVIEW` with an explanation, and the document is still listed and downloadable-by-reference for manual follow-up.

## Document-scoped Q&A flow (section 5G)

```text
User question + document_id → app.api.upload::query_document
   1. Load the source_documents row; 404 if it doesn't exist
   2. Build AuthorizationContext from the authenticated user
   3. _document_authorized(ctx, doc, user.id) → 403 if not authorized
      (uploader, admin, or assigned to the document's resolved patient)
   4. doc.status != COMPLETED → return NO_AUTHORIZED_CONTEXT, no retrieval
   5. app.rag.pipeline.run_query(..., patient_id=doc.patient_id,
      document_id=doc.id) — the SAME authorization + retrieval pipeline
      chat uses, with one extra Qdrant/SQL condition: source_document_id
      must match this document, so only this document's own chunks can
      ever answer the question
   6. Citation validation, audit log, response — identical to /api/rag/query
```

## Hospital Insights flow (section 6C)

```text
User question (or just loading the overview) → app.rag.insights
   1. build_authorization_context(user) — same context as chat/documents
   2. Role-specific SQL aggregation ONLY (app.rag.insights.build_overview):
      ADMIN: system-wide counts; FINANCE: claim/outstanding aggregates;
      RECEPTION: encounter counts/breakdown; DOCTOR/NURSE: counts filtered
      to assigned_patient_ids. No cross-role widening is possible here —
      the same ROLE_POLICY scoping as every other retrieval path applies.
   3. (query endpoint only) Every computed metric is packaged as the
      single citable [SOURCE_1] block
   4. LLM narrates/explains that block — it is never asked to compute or
      invent a total; if there are no metrics to narrate, the LLM is not
      called at all
   5. Audit log (action="insights_query")
```

## Chunking strategy (Phase 3)

- **Level 1 — page-aware**: keep page boundaries from extraction.
- **Level 2 — section-aware**: detect headings (Patient Information, Diagnosis, Medications, Allergies, Laboratory Results, Procedures, Billing, Insurance, Discharge Summary) and avoid splitting a section mid-way.
- **Level 3 — schema-aware knowledge units**: one atomic chunk per structured record type per patient (e.g. "Patient P999 — Diagnosis: Hypertension"), tagged with `record_type` for metadata filtering.
- **Level 4 — narrative chunks**: for prose that doesn't map to a table, semantic/section-aware chunks of roughly 500–900 tokens with 80–120 token overlap, tuned by structure rather than a blind fixed size. Tables are never split in a way that destroys row meaning.

## Vector point payload (Phase 3)

```json
{
  "chunk_id": "uuid",
  "source_type": "UPLOADED_PDF",
  "source_document_id": "uuid",
  "source_file_name": "patient_p999.pdf",
  "source_page": 4,
  "source_section": "Medications",
  "patient_id": "P999",
  "department": "cardiology",
  "ward_id": "ward_01",
  "record_type": "medication",
  "sensitivity": "clinical",
  "allowed_roles": ["DOCTOR", "NURSE", "ADMIN"],
  "allowed_user_ids": [],
  "allowed_department_ids": ["cardiology"]
}
```

## Query flow (Phase 3)

```text
User question → query normalization → AuthorizationContext (from Postgres)
→ embedding → Qdrant filtered search (filter from AuthorizationContext)
→ top-K authorized chunks only → optional rerank → context assembly
→ LLM generation (context-only, cited) → citation validation
→ audit_logs write → response
```

See [RAG_DESIGN.md](RAG_DESIGN.md) for the filter construction and grounding rules in detail.
