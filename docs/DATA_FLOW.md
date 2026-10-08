# MediGaurd RAG — Data Flow

> **Implementation status (Phase 2, 2026-10-08):** steps 1–10 below are implemented (`backend/app/api/upload.py`, `backend/app/ingestion/pdf_mapper.py`). Step 7's "structured info extraction" is currently a rule-based "Label: Value" line parser, not an LLM call — see progress/DECISIONS.md. Steps 11–14 (chunking beyond the schema-aware knowledge records already generated for Synthea data, embedding, Qdrant) are Phase 3.

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
12. EMBEDDING            EmbeddingProvider                                [Phase 3]
13. QDRANT UPSERT        chunk + full security metadata payload          [Phase 3]
14. READY FOR RAG        immediately queryable                           [Phase 3]
```

Each step's failure mode must produce a clear `ingestion_jobs.status = FAILED` with a reason, not a silent partial result. Status values: `RECEIVED, EXTRACTING, PARSING, MAPPING, VALIDATING, DATABASE_INSERT, CHUNKING, EMBEDDING, INDEXING, COMPLETED, FAILED`.

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
