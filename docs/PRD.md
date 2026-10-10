# MediGuard RAG — Product Requirements Document

## Problem Statement

> Secure Multi-Modal RAG System with Access Control
>
> Build a Retrieval-Augmented Generation system that ingests mixed data (PDFs, images with OCR, structured DB records), builds a unified vector + metadata index, and answers natural language queries but must enforce row/document-level access control so a query never leaks data the requesting user isn't authorised to see, and must cite exact sources for every claim in its answer. Tests: LLM/embedding pipeline design, vector DB internals, authZ enforcement at the retrieval layer (not just app layer), multi-modal data handling, hallucination/citation grounding.

## Users

- **Doctor** — treating clinician, needs clinical history for assigned/relevant patients.
- **Nurse** — bedside care staff, needs narrower clinical access scoped to assigned patients/ward.
- **Finance** — billing/insurance staff, needs claims and payer data, not clinical detail.
- **Reception** — front-desk/operational staff, needs patient identity and visit logistics only.
- **Admin** — system operator, unrestricted access for demo/debugging and system administration.

## Personas

- **Dr. Example (Doctor, Cardiology)** — logs in each morning, asks MediGuard about a patient's current conditions and medications before rounds.
- **Finance Example (Finance)** — reviews outstanding claim balances, must never see clinical diagnosis detail even if asking about the same patient.
- **Admin Example (Admin)** — verifies during the hackathon demo that the retrieval filter actually blocks unauthorized chunks, not just the final answer text.

## Goals

- Ingest Synthea structured hospital data and user-uploaded PDFs into one authoritative PostgreSQL schema.
- Build a unified vector + metadata index (Qdrant) that mirrors the database's authorization boundaries.
- Enforce access control **before** similarity search runs, not by post-filtering LLM output.
- Ground every generated answer in retrieved, authorized context with an exact, verifiable citation.
- Make the access-control mechanism visible and explainable to a technical jury via an admin debug view.

## Non-Goals

- No real hospital ERP, payment gateway, or appointment-booking system.
- No mobile app, agent swarm, or LLM fine-tuning.
- No fabricated data domains (e.g. a ward/appointment system) presented as if Synthea provided them natively — these are explicitly application-level additions.
- No exhaustive OCR pipeline for this prototype beyond an architecture-ready fallback path.

## Functional Requirements

1. Username/password login with a server-verified role; a client-selected role must match the stored role or the login is rejected.
2. Five roles: DOCTOR, NURSE, FINANCE, RECEPTION, ADMIN, each with a defined data-domain permission matrix (see [SECURITY.md](SECURITY.md)).
3. PDF upload endpoint that extracts text/pages, maps content to the canonical schema, writes structured records, and indexes resulting knowledge chunks.
4. Natural-language chat endpoint that answers only from authorized, retrieved context.
5. Every factual claim in an answer carries a citation resolvable to a database record or a PDF page/section.
6. Audit log entry for every query: user, role, query text, retrieved source ids, result status.
7. Admin debug view showing the authorization filter applied to a query and which sources were retrieved vs. excluded.

## Non-Functional Requirements

- Authorization must be enforced server-side and at the retrieval layer; the frontend is never a security boundary.
- Secrets (DB credentials, LLM/embedding API keys, JWT signing key) live only in environment variables, never in source.
- Passwords are hashed (bcrypt via passlib); plaintext passwords are never stored or logged.
- The system must degrade safely: a failed extraction, embedding, or LLM call produces a clear error, not a silent gap or a hallucinated answer.
- Sensitive identifiers (SSN, driver's license, passport) are classified as highly sensitive and excluded from embeddings and ordinary RAG answers.

## User Journeys

**Journey A — Doctor asks a clinical question**
Login as `doctor01` → ask "What conditions does patient P001 have?" → authorization context is built from the doctor's role and patient assignments → Qdrant filter restricts retrieval to clinical chunks for assigned/relevant patients → LLM generates an answer strictly from those chunks → answer is returned with citations to the `conditions` table records.

**Journey B — Finance asks the same question**
Login as `finance01` → same question → the authorization filter for FINANCE excludes `sensitivity=clinical` chunks entirely → no clinical chunk is retrieved → the answer states clinical information is restricted for this role, without hinting at its content.

**Journey C — New patient PDF**
An authorized Doctor uploads `new_patient_001.pdf` → extraction → schema mapping → validation → DB insert → knowledge-chunk generation → embeddings → Qdrant upsert → the same chat endpoint can now answer questions about the new patient, citing the PDF page/section.

## Role Model

See [SECURITY.md](SECURITY.md) for the full role permission matrix and the authorization context structure.

## Data Architecture

See [DATA_MODEL.md](DATA_MODEL.md) and [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for the relational schema (Synthea-derived + application + provenance tables) and [ARCHITECTURE.md](ARCHITECTURE.md) for how PostgreSQL and Qdrant relate (Postgres is the source of truth; Qdrant mirrors authorized, chunked knowledge with metadata for filtering).

## PDF Workflow

See [DATA_FLOW.md](DATA_FLOW.md) for the full ingestion pipeline: validation → hash/duplicate check → extraction → section/table detection → schema mapping → validation → DB insert → chunking → embedding → Qdrant upsert.

## RAG Workflow

See [RAG_DESIGN.md](RAG_DESIGN.md) for query normalization, authorization-context construction, filtered retrieval, context assembly, generation, and citation attachment.

## Security Model

See [SECURITY.md](SECURITY.md) and [SECURITY_MODEL.md](SECURITY_MODEL.md).

## Citation Model

Every factual claim must resolve to either:
- a database record reference, e.g. `[Condition Record: <record_id>]`, or
- a PDF location, e.g. `[patient_p999.pdf | Page 4 | Medications]`.

No citation may be generated for a source that was not actually present in the authorized retrieved context.

## Acceptance Criteria

See [README.md](../README.md) "Acceptance Tests" and section 46 of the original build specification (preserved in [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md)) for the ten required end-to-end tests covering per-role access, denial, and new-document ingestion.

## Future Scope

- OCR fallback for scanned PDFs.
- Hybrid lexical + dense retrieval and reranking.
- Multi-payer/multi-tenant organization scoping.
- Image modality (clinical images with OCR) beyond PDF text.
