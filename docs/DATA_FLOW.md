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
7. STRUCTURED INFO EXTRACTION  rule-based "Label: Value" line parser     [implemented — app/ingestion/pdf_mapper.py::extract_patient_document_data; a per-line parser alone mangles a real-world header line that packs two fields onto one line ("Name : X Reg. No. : Y") — `_extract_identity_fallback` recovers a clean name/registration-id/gender from such lines via field-boundary-aware regexes, generic to any document using that layout, never keyed to one patient's name (2026-10-09 fix, docs/DECISIONS.md "PDF retrieval fix")]
8. SCHEMA MAPPING        map to patients/conditions/medications/allergies/procedures/encounters/claims [implemented — app/ingestion/pdf_mapper.py::map_to_database]
9. VALIDATION            Pydantic intermediate schema (app/schemas/pdf_normalization.py) [implemented]
10. DATABASE INSERTION   insert rows, stamped with source_type=UPLOADED_PDF + source_document_id [implemented; new-patient dedup via external_patient_id/name]
11. SCHEMA-AWARE KNOWLEDGE GENERATION  atomic + narrative chunks          [implemented for Synthea data (scripts/generate_knowledge_records.py, from the clean 100-patient dataset — see docs/CLEAN_DATASET.md for current counts) and for uploaded-PDF rows (app/ingestion/pdf_mapper.py — a knowledge_records row is created inline as each structured row is mapped, not a separate pass). **2026-10-09 fix**: every page's own text is now ALSO kept as a generic `record_type="document"` narrative knowledge record regardless of what (if anything) the structured parser recognized. Previously a document whose content didn't match any structured category — e.g. a lab report's test-result tables, which have no "Diagnosis:"/"Medication:" style lines at all — produced zero knowledge_records and was completely unretrievable despite a successful-looking upload (`records_created: 0, chunks_indexed: 0`, `status: COMPLETED`). See docs/DECISIONS.md "PDF retrieval fix" for the full root-cause writeup and docs/SECURITY_MODEL.md for why `"document"` had to be added to `CLINICAL_RECORD_TYPES`.]
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

## Citation → PDF viewer flow (section 10, 2026-10-09)

```text
User clicks a PDF-backed citation in Clinical Chat (ChatMessage.tsx)
   1. Frontend already has, from the citation object: document_id, page,
      file_name, evidence_text — no extra request needed to know WHERE to
      open
   2. PdfViewerPanel fetches GET /api/documents/{document_id}/file with the
      user's Authorization header (apiRequestBlob) → an authenticated
      fetch, never a plain <iframe src>/<a href>, which couldn't carry that
      header at all
   3. Backend re-checks _document_authorized() before streaming a single
      byte — the same check as every other document endpoint
   4. Frontend turns the response into a blob object URL, renders it via
      react-pdf (pdf.js), and jumps straight to the cited page
   5. Text-layer highlighting (customTextRenderer): each on-page text
      fragment is checked for whether it's a substring of the citation's
      own evidence_text; a match is wrapped in <mark>. Only attempted when
      evidence_text is reasonably short (<=500 chars) — a whole-page
      narrative citation's evidence_text IS that entire page, so
      "highlighting" it would mean highlighting the whole page, which is
      correct but not a useful visual cue; in that case the page still
      opens and the full evidence text is shown in the panel below instead
      (the explicit fallback this section allows for)
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


## OCR image pipeline (image uploads)

`POST /api/documents/upload-image` → authenticate + role check → validate content (type, size, pixel cap) → store the original bytes (`data/uploads/<id>.<ext>`) → **background**: preprocess → OCR → quality gate → identify patient → create chunks → embed → index → read back from Qdrant → `COMPLETED`.

- **Preprocessing is deliberately conservative** (`app/ingestion/image_prep.py`): EXIF orientation, a size clamp, grayscale, a mild contrast stretch. No binarising, denoising, sharpening or deskew — those erase decimal points, units, thin range dashes and faint handwriting. Images under ~2000px on their long side are upscaled for OCR only: measured on a rendered lab report, native 1100px made the engine drop word spaces ("Patient Name:MeeraKrishnan", "Vitamin D18", "30- 100") while ≥2× returned the text exactly. Boxes are mapped back to original-image pixels.
- **Persistence**: original image + `<id>.ocr.json` (lines, confidences, boxes, quality) beside it, so a retry resumes from the stored text instead of re-running OCR, and the viewer can draw real regions.
- **Identity** reuses the PDF extractor (`extract_patient_document_data`) and the `Patient` model. Exact name/ID match to a patient the uploader may access → linked; a plausible new full name → new patient (uploader becomes its only attending, as for PDFs); everything else → `NEEDS_REVIEW` with nothing indexed. A near-miss name never creates a duplicate patient.
- **Chunks** are ordinary `knowledge_records` (`record_type="document"`, `source_type="OCR_IMAGE"`, `source_section="ocr_image"`) split at line boundaries into ~900 characters so MiniLM embeds all of each chunk. **No structured SQL rows are created from OCR text**: a misread character there would become a "verified" fact in the deterministic answer path. OCR facts are answered through semantic retrieval, with citations.
- **Retrieval**: questions that refer to the upload ("this image", "the report", "uploaded") route to document text; for a patient who has upload text, the *observation* and *summary* intents skip the SQL-only fast path (which would answer "0 documented" or list unrelated vitals) and use semantic search over both sources. Citations list only sources the answer actually cites.
- **Not implemented**: OCR of scanned PDF pages (still `NEEDS_REVIEW`), handwriting-specific models, multi-image documents, rotation beyond EXIF, and medical image understanding.
