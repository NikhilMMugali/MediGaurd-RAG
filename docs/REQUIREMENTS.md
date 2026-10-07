# MediGaurd RAG — Requirements Traceability

## Problem Statement

> Secure Multi-Modal RAG System with Access Control
>
> Build a Retrieval-Augmented Generation system that ingests mixed data (PDFs, images with OCR, structured DB records), builds a unified vector + metadata index, and answers natural language queries but must enforce row/document-level access control so a query never leaks data the requesting user isn't authorised to see, and must cite exact sources for every claim in its answer. Tests: LLM/embedding pipeline design, vector DB internals, authZ enforcement at the retrieval layer (not just app layer), multi-modal data handling, hallucination/citation grounding.

## Requirement → Implementation Mapping

| Problem statement requirement | Implementation |
|---|---|
| Mixed data ingestion | Synthea CSV import into PostgreSQL (Phase 2) + PDF upload/extraction pipeline (`backend/app/ingestion/`); OCR-ready architecture for image modality |
| Unified vector + metadata index | Qdrant collection with per-chunk metadata payload (`patient_id`, `department`, `ward_id`, `record_type`, `sensitivity`, `allowed_roles`, provenance fields) — see [DATA_FLOW.md](DATA_FLOW.md) |
| Natural language questions | RAG chat endpoint (`backend/app/rag/`, Phase 3) |
| Row/document-level access control | PostgreSQL authorization tables (`patient_assignments`, `document_acls`, `user_departments`) + a pre-retrieval Qdrant filter built from the requesting user's authorization context — see [SECURITY.md](SECURITY.md) |
| Exact source citations | `source_document_id`, `source_page`, `source_section`, `source_record_id` provenance columns/payload fields carried from ingestion through to the final answer |
| LLM/embedding pipeline design | `EmbeddingProvider` / `LLMProvider` abstractions (`backend/app/services/`) so the vendor is swappable via `.env` |
| Vector DB internals | Qdrant collection design, payload indexing, and boolean filter construction documented in [RAG_DESIGN.md](RAG_DESIGN.md) |
| AuthZ at retrieval layer (not just app layer) | Authorization filter is attached to the Qdrant `search()` call itself; restricted chunks are never returned to the application, let alone the LLM — see [SECURITY_MODEL.md](SECURITY_MODEL.md) |
| Multi-modal data handling | PDF text extraction now (PyMuPDF/pdfplumber); OCR fallback path defined but not forced on text-extractable PDFs |
| Hallucination/citation grounding | System prompt restricts generation to supplied authorized context only; citation validator rejects any citation not present in the retrieved set — see [RAG_DESIGN.md](RAG_DESIGN.md) |

## Explicit Non-Requirements / Guardrails

- Synthea does **not** contain `appointments.csv`, `wards.csv`, or `departments.csv`. Wards, departments, and patient-assignment scope are application-level constructs built on top of `encounters.csv`, never claimed as native Synthea data.
- Unauthorized information must never be retrieved and sent to the LLM. Post-hoc filtering of LLM output, or asking the LLM to "hide" restricted information it was shown, is explicitly disallowed — see section 22/55 of the original specification, preserved in [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md).

## Dataset Inventory (verified)

18 CSV files, ~108 patients. See [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for full column listings per file, carried over unchanged from the verified inventory in the original specification.
