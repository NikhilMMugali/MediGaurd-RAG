# MediGuard RAG — Data Model

> **Implementation status (Phase 2, 2026-10-08):** all three table groups below are implemented as SQLAlchemy models (`backend/app/models/`) and created via the initial Alembic migration. Synthea import and knowledge-record generation are verified against SQLite locally (see progress/DECISIONS.md for why — PostgreSQL itself is not yet running on the dev machine); the schema has no Postgres-specific types, so this is a configuration swap, not a rewrite, once Postgres is available.

Full column-level schema lives in [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md). This document describes the *categories* of tables and how they relate.

## Three table groups

### 1. Core source tables (Synthea-derived, source_type=SYNTHEA by default)

```text
patients, encounters, conditions, medications, observations, allergies,
procedures, careplans, immunizations, imaging_studies, devices, supplies,
claims, claims_transactions, payers, payer_transitions, providers,
organizations
```

Loaded from the verified 18-file Synthea CSV export (~108 patients). Rows created later from an uploaded PDF land in these same tables, tagged `source_type=UPLOADED_PDF`, so a doctor's query never needs to know whether a fact came from the original dataset or a later upload.

### 2. Application / security tables

```text
users, roles(enum), departments, wards, patient_assignments,
user_departments, document_acls, audit_logs, ingestion_jobs
```

These do not exist in Synthea and are never claimed to. `wards` and `patient_assignments` are built on top of `encounters.csv` (the only operational-visit source Synthea provides) plus deterministic demo seeding against real imported patient ids.

### 3. Knowledge / provenance tables

```text
source_documents, document_chunks, knowledge_records
```

`source_documents` records an uploaded PDF (hash, filename, uploader, status). `document_chunks` records each chunk produced during ingestion (page/section, text, record_type, sensitivity) with a foreign key to `source_documents`. `knowledge_records` links a chunk back to the specific structured row(s) it was generated from, when applicable — this is what makes a citation resolvable.

## Provenance fields

Every table that can be populated by either Synthea import or PDF upload carries:

```text
source_type           SYNTHEA | UPLOADED_PDF | MANUAL
source_document_id     nullable FK to source_documents
source_file_name
source_page
source_section
source_record_id
created_at
updated_at
```

This is what makes citations exact rather than approximate: a generated answer can always point to `[patient_p999.pdf | Page 4 | Medications]` or `[conditions table | record <id>]`.

## New-patient handling

A PDF-introduced patient not present in Synthea gets a new `patients` row. The PDF's own patient identifier is kept as `external_patient_id` rather than overwriting or guessing a match against an existing Synthea patient. Deduplication compares identifier, name, and date of birth, and ambiguous matches are flagged rather than silently merged. It also gets the next free `display_id` (see below), so it shows up in the UI as `P101`, `P102`, ... rather than its raw UUID.

## Display id vs internal id

`patients.id` is the real internal id — every other table's patient FK (`conditions.patient`, `knowledge_records.patient_id`, `patient_assignments.patient_id`, etc.) points at it, unchanged. `patients.display_id` is a separate, independent, unique column holding the clean id the UI actually shows (`P001`..`P100` for the clean dataset, `P101`+ for anything introduced later via PDF upload) — see [docs/CLEAN_DATASET.md](CLEAN_DATASET.md). `app.rag.pipeline.resolve_patient_reference()` is the one place a display id (or a legacy raw UUID) is turned back into the internal id, before any authorization check or query runs.

## Entity relationship sketch

```text
patients 1───* encounters 1───* conditions
   │                │      └──* medications
   │                │      └──* observations
   │                │      └──* procedures
   │                │      └──* careplans
   │                │      └──* immunizations
   │                │      └──* imaging_studies
   │                │      └──* devices
   │                │      └──* supplies
   │                └──* claims ──* claims_transactions
   │
   └──* patient_assignments ──* wards
   └──* source_documents ──* document_chunks ──* knowledge_records

users ──* user_departments ──* departments
users ──* patient_assignments (assigned_user_id)
users ──* audit_logs
```
