# MediGaurd RAG — Project Requirements (Acceptance Tests & Guardrails)

This document holds the acceptance criteria and explicit guardrails from the original build specification, kept separate from [REQUIREMENTS.md](REQUIREMENTS.md)'s requirement-to-implementation mapping so they're easy to check off literally.

## Acceptance tests

1. **Doctor clinical access** — `doctor01` asks "What conditions does patient P001 have?" → clinical answer + exact sources.
2. **Finance clinical denial** — `finance01` asks the same question → "Clinical information is restricted for your role." and clinical chunks are NOT retrieved (verifiable in the admin debug view).
3. **Finance billing access** — `finance01` asks "What is the outstanding amount for patient P001?" → finance info + source.
4. **Doctor billing denial** — doctor asks the billing question → restricted; no finance chunk enters LLM context.
5. **Reception encounter access** — `reception01` asks "When was patient P001's last encounter?" → allowed + exact source.
6. **Reception clinical denial** — `reception01` asks about medication → restricted.
7. **Nurse patient scope** — nurse asks about an assigned patient → allowed; asks about an unassigned patient → restricted, enforced at retrieval.
8. **Admin** — can retrieve across all authorized domains.
9. **New PDF** — upload → extract → normalize → DB records created → chunks created → vectors indexed → queryable from RAG.
10. **New patient access control** — upload P999; an assigned doctor gets an answer, an unassigned doctor does not, admin does.

Every answer in every test that contains a factual claim must carry a citation resolving to a database record or a PDF page/section.

## What not to build

```text
real hospital ERP, real payment gateway, real appointment booking,
mobile application, complex agent swarm, fine-tuning, training an LLM,
huge vector corpus, microservice explosion, Kubernetes, unnecessary animations
```

This project is about: secure RAG + access control + structured data + PDF ingestion + grounding + citations — nothing broader.

## Hard guardrails (non-negotiable)

- Never replace retrieval-layer authorization with application-layer filtering.
- Never send unauthorized context to the LLM, even if the intent is to ask it to withhold that information in its answer.
- Never fabricate data fields, appointments, or wards as if Synthea natively contained them.
- Never fabricate PDF-extracted fields; missing fields are `null`, not guessed.
- Never generate a citation without real provenance.
- Never hardcode secrets.
- Never skip tests or documentation updates when declaring a phase complete.
- When uncertain, prefer secure/traceable/modular/testable/explainable over fast-but-insecure.

## Final success criteria

See README.md "Success Criteria" for the full 20-point checklist carried over from the original specification (Synthea in DB, 5 roles, server-side permissions, PDF upload/extraction/mapping/indexing, pre-retrieval authorization, grounded + cited answers, audit logs, full documentation set, commits pushed, demo-explainable to a jury).
