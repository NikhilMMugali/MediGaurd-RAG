"""Rule-based section/field extraction from already-extracted PDF page text
(Phase 1's PyMuPDF extractor) into the validated intermediate schema
(app.schemas.pdf_normalization.PatientDocumentData), and the mapper that
turns that intermediate schema into real rows in the canonical hospital
tables, stamped with provenance.

This is deliberately a simple "Label: Value" line parser rather than an LLM
call — fast, free, and fully traceable for a hackathon demo, matching the
sample document format in docs/DATA_FLOW.md. A smarter extractor can replace
`extract_patient_document_data` later without touching the DB-mapping half.
"""
import re

from sqlalchemy.orm import Session

from app.models.hospital import Allergy, Claim, Condition, Encounter, Medication, Patient, Procedure
from app.models.provenance import new_uuid
from app.schemas.ingestion import PdfExtractionResult
from app.schemas.pdf_normalization import (
    AllergyItem,
    ClaimItem,
    ConditionItem,
    EncounterItem,
    MedicationItem,
    PatientDocumentData,
    PatientInfo,
    ProcedureItem,
)

_LABEL_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z /]*?)\s*:\s*(.+?)\s*$")

_PATIENT_ID_LABELS = {"patient", "patient id", "patient_id"}
_NAME_LABELS = {"name"}
_CONDITION_LABELS = {"diagnosis", "condition", "conditions"}
_MEDICATION_LABELS = {"medication", "medications"}
_ALLERGY_LABELS = {"allergy", "allergies"}
_PROCEDURE_LABELS = {"procedure", "procedures"}
_ENCOUNTER_LABELS = {"encounter", "visit", "encounters"}
_BILLING_LABELS = {"billing", "outstanding", "claim"}


def extract_patient_document_data(extraction: PdfExtractionResult) -> PatientDocumentData:
    """Scan "Label: Value" lines across every extracted page. Unrecognized
    labels are left out rather than guessed; a page with no recognizable
    label still contributes nothing but never raises."""
    data = PatientDocumentData()
    patient_id: str | None = None
    patient_name: str | None = None

    for page in extraction.pages:
        for line in page.text.splitlines():
            match = _LABEL_LINE.match(line)
            if not match:
                continue
            label, value = match.group(1).strip().lower(), match.group(2).strip()
            if not value:
                continue

            if label in _PATIENT_ID_LABELS:
                patient_id = value
            elif label in _NAME_LABELS:
                patient_name = value
            elif label in _CONDITION_LABELS:
                data.conditions.append(ConditionItem(description=value, source_page=page.page_number))
            elif label in _MEDICATION_LABELS:
                data.medications.append(MedicationItem(description=value, source_page=page.page_number))
            elif label in _PROCEDURE_LABELS:
                data.procedures.append(ProcedureItem(description=value, source_page=page.page_number))
            elif label in _ALLERGY_LABELS:
                data.allergies.append(AllergyItem(description=value, source_page=page.page_number))
            elif label in _ENCOUNTER_LABELS:
                data.encounters.append(EncounterItem(description=value, source_page=page.page_number))
            elif label in _BILLING_LABELS:
                try:
                    outstanding = float(re.sub(r"[^0-9.]", "", value) or 0)
                except ValueError:
                    outstanding = None
                data.claims.append(ClaimItem(outstanding=outstanding, source_page=page.page_number))

    if patient_id or patient_name:
        first, _, last = (patient_name or "").partition(" ")
        data.patient = PatientInfo(
            external_patient_id=patient_id,
            first=first or None,
            last=last or None,
        )

    return data


def find_or_create_patient(db: Session, info: PatientInfo | None, source_document_id: str) -> Patient | None:
    """Deduplicates on external_patient_id + name; never silently merges on
    name alone. An ambiguous case (same name, different external id) still
    creates a new row — flagging for review is Phase 3+ UI work, not a
    reason to guess here."""
    if info is None or not (info.external_patient_id or info.first or info.last):
        return None

    existing = None
    if info.external_patient_id:
        existing = (
            db.query(Patient).filter(Patient.external_patient_id == info.external_patient_id).first()
        )
    if existing is None and info.first and info.last:
        existing = (
            db.query(Patient)
            .filter(Patient.first == info.first, Patient.last == info.last, Patient.external_patient_id.is_(None))
            .first()
        )
    if existing is not None:
        return existing

    patient = Patient(
        id=new_uuid(),
        external_patient_id=info.external_patient_id,
        first=info.first,
        last=info.last,
        source_type="UPLOADED_PDF",
        source_document_id=source_document_id,
    )
    db.add(patient)
    db.flush()
    return patient


def map_to_database(db: Session, data: PatientDocumentData, source_document_id: str) -> int:
    """Inserts every mappable item as a real row in the canonical tables,
    stamped with source_type=UPLOADED_PDF + source_document_id + source_page.
    Returns the number of records created."""
    patient = find_or_create_patient(db, data.patient, source_document_id)
    patient_id = patient.id if patient else None
    created = 0

    for item in data.conditions:
        db.add(
            Condition(
                id=new_uuid(),
                patient=patient_id,
                description=item.description,
                source_type="UPLOADED_PDF",
                source_document_id=source_document_id,
            )
        )
        created += 1

    for item in data.medications:
        db.add(
            Medication(
                id=new_uuid(),
                patient=patient_id,
                description=item.description,
                source_type="UPLOADED_PDF",
                source_document_id=source_document_id,
            )
        )
        created += 1

    for item in data.allergies:
        db.add(
            Allergy(
                id=new_uuid(),
                patient=patient_id,
                description=item.description,
                severity1=item.severity,
                source_type="UPLOADED_PDF",
                source_document_id=source_document_id,
            )
        )
        created += 1

    for item in data.procedures:
        db.add(
            Procedure(
                id=new_uuid(),
                patient=patient_id,
                description=item.description,
                source_type="UPLOADED_PDF",
                source_document_id=source_document_id,
            )
        )
        created += 1

    for item in data.encounters:
        db.add(
            Encounter(
                id=new_uuid(),
                patient=patient_id,
                description=item.description,
                source_type="UPLOADED_PDF",
                source_document_id=source_document_id,
            )
        )
        created += 1

    for item in data.claims:
        db.add(
            Claim(
                id=new_uuid(),
                patientid=patient_id,
                outstandingp=item.outstanding,
                statusp=item.status,
                source_type="UPLOADED_PDF",
                source_document_id=source_document_id,
            )
        )
        created += 1

    db.commit()
    return created
