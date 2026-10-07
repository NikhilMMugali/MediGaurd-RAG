# MediGaurd RAG — Data Flow

## PDF ingestion pipeline (full target, Phase 1 implements steps 1–3)

```text
1. UPLOAD                multipart POST, role-gated (DOCTOR/NURSE/ADMIN)
2. FILE VALIDATION       content-type/extension check, size limit        [implemented]
3. HASH / DUPLICATE CHECK  sha256 of file bytes against source_documents [extractor computes hash now; dedup check is Phase 2]
4. PDF TEXT EXTRACTION   PyMuPDF per-page text; pdfplumber for tables    [implemented]
5. PAGE PRESERVATION    page_number kept on every extracted unit         [implemented]
6. SECTION/TABLE DETECTION  heading/table detection                      [Phase 2]
7. STRUCTURED INFO EXTRACTION  LLM/rule-based entity extraction          [Phase 2]
8. SCHEMA MAPPING        map to patients/conditions/medications/...      [Phase 2]
9. VALIDATION            Pydantic models reject malformed/hallucinated fields [Phase 2]
10. DATABASE INSERTION   insert/merge rows, stamped with provenance      [Phase 2]
11. SCHEMA-AWARE KNOWLEDGE GENERATION  atomic + narrative chunks          [Phase 3]
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
