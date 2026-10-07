# MediGaurd RAG — Database Schema

## Source: Synthea CSV inventory (verified)

18 CSV files, ~108 patients.

| File | Rows |
|---|---|
| patients.csv | 108 |
| encounters.csv | 5,571 |
| conditions.csv | 3,517 |
| medications.csv | 3,850 |
| observations.csv | 68,648 |
| allergies.csv | 105 |
| procedures.csv | 15,884 |
| careplans.csv | 349 |
| immunizations.csv | 1,549 |
| imaging_studies.csv | 478 |
| devices.csv | 524 |
| supplies.csv | 2,225 |
| claims.csv | 9,421 |
| claims_transactions.csv | 85,047 |
| payers.csv | 10 |
| payer_transitions.csv | 3,815 |
| providers.csv | 278 |
| organizations.csv | 278 |

### patients
`Id, BIRTHDATE, DEATHDATE, SSN, DRIVERS, PASSPORT, PREFIX, FIRST, MIDDLE, LAST, SUFFIX, MAIDEN, MARITAL, RACE, ETHNICITY, GENDER, BIRTHPLACE, ADDRESS, CITY, STATE, COUNTY, FIPS, ZIP, LAT, LON, HEALTHCARE_EXPENSES, HEALTHCARE_COVERAGE, INCOME`

`SSN`, `DRIVERS`, `PASSPORT` → classified `restricted_pii`; excluded from embeddings and ordinary answers.

### encounters
`Id, START, STOP, PATIENT, ORGANIZATION, PROVIDER, PAYER, ENCOUNTERCLASS, CODE, DESCRIPTION, BASE_ENCOUNTER_COST, TOTAL_CLAIM_COST, PAYER_COVERAGE, REASONCODE, REASONDESCRIPTION`

### conditions
`START, STOP, PATIENT, ENCOUNTER, SYSTEM, CODE, DESCRIPTION`

### medications
`START, STOP, PATIENT, PAYER, ENCOUNTER, CODE, DESCRIPTION, BASE_COST, PAYER_COVERAGE, DISPENSES, TOTALCOST, REASONCODE, REASONDESCRIPTION`

### observations
`DATE, PATIENT, ENCOUNTER, CATEGORY, CODE, DESCRIPTION, VALUE, UNITS, TYPE`

### allergies
`START, STOP, PATIENT, ENCOUNTER, CODE, SYSTEM, DESCRIPTION, TYPE, CATEGORY, REACTION1, DESCRIPTION1, SEVERITY1, REACTION2, DESCRIPTION2, SEVERITY2`

### procedures
`START, STOP, PATIENT, ENCOUNTER, SYSTEM, CODE, DESCRIPTION, BASE_COST, REASONCODE, REASONDESCRIPTION`

### careplans
`Id, START, STOP, PATIENT, ENCOUNTER, CODE, DESCRIPTION, REASONCODE, REASONDESCRIPTION`

### immunizations
`DATE, PATIENT, ENCOUNTER, CODE, DESCRIPTION, BASE_COST`

### imaging_studies
`Id, DATE, PATIENT, ENCOUNTER, SERIES_UID, BODYSITE_CODE, BODYSITE_DESCRIPTION, MODALITY_CODE, MODALITY_DESCRIPTION, INSTANCE_UID, SOP_CODE, SOP_DESCRIPTION, PROCEDURE_CODE`

### devices
`START, STOP, PATIENT, ENCOUNTER, CODE, DESCRIPTION, UDI`

### supplies
`DATE, PATIENT, ENCOUNTER, CODE, DESCRIPTION, QUANTITY`

### claims
`Id, PATIENTID, PROVIDERID, PRIMARYPATIENTINSURANCEID, SECONDARYPATIENTINSURANCEID, DEPARTMENTID, PATIENTDEPARTMENTID, DIAGNOSIS1..8, REFERRINGPROVIDERID, APPOINTMENTID, CURRENTILLNESSDATE, SERVICEDATE, SUPERVISINGPROVIDERID, STATUS1, STATUS2, STATUSP, OUTSTANDING1, OUTSTANDING2, OUTSTANDINGP, LASTBILLEDDATE1, LASTBILLEDDATE2, LASTBILLEDDATEP, HEALTHCARECLAIMTYPEID1, HEALTHCARECLAIMTYPEID2`

Note: `APPOINTMENTID` exists here but Synthea does **not** provide a dedicated appointment-management table.

### claims_transactions
`ID, CLAIMID, CHARGEID, PATIENTID, TYPE, AMOUNT, METHOD, FROMDATE, TODATE, PLACEOFSERVICE, PROCEDURECODE, MODIFIER1, MODIFIER2, DIAGNOSISREF1..4, UNITS, DEPARTMENTID, NOTES, UNITAMOUNT, TRANSFEROUTID, TRANSFERTYPE, PAYMENTS, ADJUSTMENTS, TRANSFERS, OUTSTANDING, APPOINTMENTID, LINENOTE, PATIENTINSURANCEID, FEESCHEDULEID, PROVIDERID, SUPERVISINGPROVIDERID`

### payers
`Id, NAME, OWNERSHIP, ADDRESS, CITY, STATE_HEADQUARTERED, ZIP, PHONE, AMOUNT_COVERED, AMOUNT_UNCOVERED, REVENUE, COVERED_ENCOUNTERS, UNCOVERED_ENCOUNTERS, COVERED_MEDICATIONS, UNCOVERED_MEDICATIONS, COVERED_PROCEDURES, UNCOVERED_PROCEDURES, COVERED_IMMUNIZATIONS, UNCOVERED_IMMUNIZATIONS, UNIQUE_CUSTOMERS, QOLS_AVG, MEMBER_MONTHS`

### payer_transitions
`PATIENT, MEMBERID, START_DATE, END_DATE, PAYER, SECONDARY_PAYER, PLAN_OWNERSHIP, OWNER_NAME`

### providers
`Id, ORGANIZATION, NAME, GENDER, SPECIALITY, ADDRESS, CITY, STATE, ZIP, LAT, LON, ENCOUNTERS, PROCEDURES, NPI`

### organizations
`Id, NAME, ADDRESS, CITY, STATE, ZIP, LAT, LON, PHONE, REVENUE, UTILIZATION, NPI`

---

## Application tables (not from Synthea)

```text
users(id, username, full_name, hashed_password, role, department_id, is_active, created_at)
departments(id, name)
wards(id, name, department_id)
patient_assignments(id, patient_id, ward_id, assigned_user_id, assignment_type, active)
user_departments(user_id, department_id)
document_acls(id, document_id, allowed_roles, allowed_user_ids, allowed_department_ids)
audit_logs(id, timestamp, user_id, role, query, retrieved_source_ids, result_status, denial_reason)
ingestion_jobs(id, document_id, status, created_at, updated_at)
```

`users.role` is implemented as `app.models.user.RoleEnum` (`backend/app/models/user.py`); `users` and `departments` are the Phase 1 tables implemented so far — the remaining application tables above are Phase 2 scope.

## Knowledge / provenance tables

```text
source_documents(id, file_name, file_hash, uploaded_by, status, created_at)
document_chunks(id, source_document_id, chunk_text, source_page, source_section, record_type, sensitivity)
knowledge_records(id, document_chunk_id, source_table, source_record_id)
```

## Indexes

Create indexes on: `patient_id`, `encounter_id`, `provider_id`, `claim_id`, `department`, `role`, plus `users.username` (unique) and `source_documents.file_hash` (unique, for duplicate detection).
