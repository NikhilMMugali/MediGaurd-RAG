# MediGaurd RAG — Security Model

## The absolute rule

> **Unauthorized information must never be retrieved and sent to the LLM.**

Correct flow:

```text
authenticate user → determine authorization → build retrieval filter
→ retrieve only authorized records/chunks → send only authorized
context to LLM → generate grounded answer → attach exact citations
```

Disallowed shortcuts (never implement these):

```text
retrieve everything → send everything to LLM → ask LLM to hide restricted info
retrieve everything → filter restricted chunks out of the LLM's answer afterward
```

Both leak information to the LLM call itself (and, via logs/telemetry, potentially beyond it), and the second can still leak through a mistaken or bypassed post-filter. The filter must exist as a pre-retrieval boolean constraint on the vector search call.

## Roles

`DOCTOR`, `NURSE`, `FINANCE`, `RECEPTION`, `ADMIN` — stored server-side on the `users.role` column. A login request's `role` field is compared against this stored value and rejected on mismatch; it is never trusted as the source of authorization by itself.

## Role permission matrix

| Data Domain | Doctor | Nurse | Finance | Reception | Admin |
|---|---|---|---|---|---|
| Basic patient information | YES | YES | Limited | YES | YES |
| Conditions | YES | Limited | NO | NO | YES |
| Medications | YES | Limited | NO | NO | YES |
| Observations/Labs | YES | Limited | NO | NO | YES |
| Allergies | YES | YES | NO | NO | YES |
| Procedures | YES | Limited | NO | NO | YES |
| Care Plans | YES | Limited | NO | NO | YES |
| Immunizations | YES | Limited | NO | NO | YES |
| Imaging | YES | Limited | NO | NO | YES |
| Encounters | YES | YES | Limited | YES | YES |
| Claims | NO | NO | YES | NO | YES |
| Claim Transactions | NO | NO | YES | NO | YES |
| Payers | NO | NO | YES | NO | YES |
| Payer Transitions | NO | NO | YES | NO | YES |
| Providers | YES | YES | YES | YES | YES |
| Organizations | YES | YES | YES | YES | YES |
| Assigned patient scope | YES | YES | N/A | N/A | ALL |
| Ward scope | N/A | YES | N/A | N/A | ALL |

## Authorization context

Built per-request from PostgreSQL, never from client input:

```text
user_id
role
department
ward_ids
assigned_patient_ids
allowed_record_types
allowed_sensitivity_levels
allowed_document_ids
```

## Retrieval filter

The authorization context is translated into a Qdrant boolean filter evaluated by the vector store itself, before similarity scoring returns any chunk to the application:

```text
role in allowed_roles
AND (department matches OR patient_id in assigned_patient_ids OR ward_id in ward_ids)
AND record_type in allowed_record_types
AND sensitivity in allowed_sensitivity_levels
```

The exact boolean composition is implemented in `backend/app/authorization/` and must never degrade to a flat `role == requested_role` check — patient/ward/department scoping is part of the filter, not a secondary check.

## Row-level security alignment

Database-level authorization (which rows a user's queries against PostgreSQL may touch) and vector-retrieval authorization (which Qdrant chunks a search may return) must agree. A chunk existing in Qdrant never grants access by itself — PostgreSQL's `patient_assignments`, `document_acls`, and `user_departments` tables remain authoritative, and the Qdrant payload is only ever a mirror of that authorization state at indexing time.

## Sensitive identifiers

`SSN`, `DRIVERS`, `PASSPORT` from `patients.csv` are classified `sensitivity=restricted_pii` and are excluded from embeddings and from ordinary RAG answers regardless of role (including ADMIN, absent an explicit future policy).

## Denial responses must not leak

A denial must say only that the information is restricted — never hint at what the hidden record contains:

```text
Correct:   "Clinical diagnosis information is not available for your role."
Incorrect: "The patient has a serious condition, but I can't tell you what it is."
```

## Audit logging

Every query writes an `audit_logs` row: `timestamp`, `user_id`, `role`, `query`, `retrieved_source_ids`, `result_status` (`ALLOWED` / `DENIED` / `NO_AUTHORIZED_CONTEXT` / `ERROR`), `denial_reason`. No secrets or full PHI payloads are stored in the log.

## General security requirements

- Passwords hashed with bcrypt (via passlib); never logged or stored in plaintext.
- Secrets only in environment variables (`.env`, not committed); `.env.example` documents required keys.
- Server-side role verification on every authenticated request (JWT role claim is re-checked against the current database row).
- File upload validation: content-type/extension check, size limit, safe PDF parsing (PyMuPDF, no execution of embedded content).
- No unauthorized context ever placed in an LLM prompt; no unauthorized citation ever generated.
