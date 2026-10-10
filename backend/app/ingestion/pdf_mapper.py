"""Rule-based section/field extraction from already-extracted PDF page text
(Phase 1's PyMuPDF extractor) into the validated intermediate schema
(app.schemas.pdf_normalization.PatientDocumentData), and the mapper that
turns that intermediate schema into real rows in the canonical hospital
tables, stamped with provenance.

This is deliberately a simple "Label: Value" line parser rather than an LLM
call — fast, free, and fully traceable for a hackathon demo, matching the
sample document format in docs/DATA_FLOW.md. A smarter extractor can replace
`extract_patient_document_data` later without touching the DB-mapping half.

Three real-world gaps were found and fixed here (progress/DECISIONS.md "PDF
retrieval fix"): (1) a document whose content doesn't match any of the
structured Label:Value categories below — e.g. a lab report's test-result
tables — previously produced zero knowledge_records and was therefore
completely unretrievable despite a successful-looking upload; every page's
text is now also kept as a generic narrative knowledge record regardless of
what structured fields were recognized. (2) the per-line parser garbles a
value when two fields share one physical line ("Name : X Reg. No. : Y",
common in real lab-report headers) because it captures everything from the
first colon to end-of-line; `_extract_identity_fallback` recovers a clean
name/registration-id/gender from such lines via field-boundary-aware regexes
instead. (3) a third, common form-style layout puts a bare label on its own
line with no colon at all and the value on the line immediately after it
("Patient Name" / "KAVYA DEMO PATIENT") — neither (1) nor (2) have any colon
to anchor on, so neither ever matches; `_extract_label_next_line_fields`
handles this as a third fallback tier."""
import re

from sqlalchemy.orm import Session

from app.models.documents import KnowledgeRecord, SourceDocument
from app.models.hospital import Allergy, Claim, Condition, Encounter, Medication, Patient, Procedure
from app.models.provenance import new_uuid
from app.models.ward import PatientAssignment
from app.schemas.ingestion import ExtractedPage, PdfExtractionResult
from app.schemas.pdf_normalization import (
    AllergyItem,
    ClaimItem,
    ConditionItem,
    EncounterItem,
    MedicationItem,
    NarrativeSection,
    PatientDocumentData,
    PatientInfo,
    ProcedureItem,
)

_LABEL_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z /]*?)\s*:\s*(.+?)\s*$")

_PATIENT_ID_LABELS = {"patient", "patient id", "patient_id", "reg no", "reg. no", "registration no", "mrn"}
_NAME_LABELS = {"name"}
_CONDITION_LABELS = {"diagnosis", "condition", "conditions"}
_MEDICATION_LABELS = {"medication", "medications"}
_ALLERGY_LABELS = {"allergy", "allergies"}
_PROCEDURE_LABELS = {"procedure", "procedures"}
_ENCOUNTER_LABELS = {"encounter", "visit", "encounters"}
_BILLING_LABELS = {"billing", "outstanding", "claim"}

# Page-text is scanned per-page (not one joined blob) so a boundary keyword
# on page N can never swallow a name that actually belongs to page N+1.
_FIELD_BOUNDARY = r"(?:\n|Reg\.?\s*No\.?|Age\b|Gender\b|Ref\.?\s*By\b|Location\b|Tele\s*No\.?|$)"
_NAME_FIELD_RE = re.compile(rf"\bName\s*:\s*(.+?)(?=\s*{_FIELD_BOUNDARY})", re.IGNORECASE)
_REGNO_FIELD_RE = re.compile(r"\b(?:Reg\.?\s*No\.?|Registration\s*No\.?|MRN)\s*:?\s*([A-Za-z0-9\-]{4,})\b", re.IGNORECASE)
_GENDER_FIELD_RE = re.compile(r"\bGender\s*:?\s*(Male|Female|Other)\b", re.IGNORECASE)

# Bare label on its own line, value on the next line — a common form/table
# export layout with no colon anywhere to anchor the two regexes above on.
# Matched by normalizing each line (strip, lowercase, drop a trailing colon)
# and checking membership in these label sets, generic to the layout and
# never keyed to any specific patient's name or id.
#
# Deliberately NOT including a bare "name" here (found via a real false
# positive during backfill testing: a quiz PDF's table had a row literally
# titled "The second name" — Python variable-aliasing trivia, nothing to do
# with a patient — table-extracted as "name" alone on one line followed by
# its answer "[1, 2, 3, 4]" on the next, which a bare "name" label matched
# as if it were a patient's name). Only multi-word, identity-form-specific
# phrasings are used, and `_looks_like_a_name` below rejects an
# implausible value regardless.
_NEXT_LINE_NAME_LABELS = {"patient name", "full name"}
_NEXT_LINE_ID_LABELS = {
    "patient id", "patient_id", "demo patient id", "mrn", "reg no", "reg. no",
    "registration no", "registration number", "patient registration number",
}
_NEXT_LINE_GENDER_LABELS = {"gender", "sex"}
_PLAUSIBLE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*){0,4}$")


def _looks_like_a_name(value: str) -> bool:
    """Letters/spaces/common name punctuation only, 2-5 words — rejects
    table/code content (digits, brackets, commas) a label match might
    otherwise accept on a non-medical document."""
    return bool(_PLAUSIBLE_NAME_RE.match(value)) and 2 <= len(value) <= 60


def _extract_label_next_line_fields(pages: list[ExtractedPage]) -> tuple[str | None, str | None, str | None]:
    """Third fallback tier: some PDF exports (often form/table layouts where
    PyMuPDF's plain-text mode linearizes a two-column form into sequential
    lines) render a field label alone on one line with the value on the very
    next line, with no colon anywhere to anchor a regex on — e.g.:

        Patient Name
        KAVYA DEMO PATIENT
        Demo Patient ID
        DEMO-PT-2026-1042

    Neither `_LABEL_LINE` (needs a colon) nor `_extract_identity_fallback`
    (also colon-anchored) can ever match this layout. Returns
    (name, external_patient_id, gender), any of which may be None."""
    name = external_id = gender = None
    for page in pages:
        lines = [ln.strip() for ln in page.text.splitlines()]
        for i, line in enumerate(lines[:-1]):
            key = line.rstrip(":").strip().lower()
            value = lines[i + 1].strip()
            if not value:
                continue
            if name is None and key in _NEXT_LINE_NAME_LABELS and _looks_like_a_name(value):
                name = _clean_identity_value(value)
            elif external_id is None and key in _NEXT_LINE_ID_LABELS:
                external_id = _clean_identity_value(value)
            elif gender is None and key in _NEXT_LINE_GENDER_LABELS and value.capitalize() in ("Male", "Female", "Other"):
                gender = value.capitalize()
        if name:
            break
    return name, external_id, gender

# Page content kept as a narrative knowledge record is capped so one chunk
# stays within a sensible embedding length; real lab-report pages are far
# shorter than this in practice.
_MAX_NARRATIVE_CHARS = 3000


def _clean_identity_value(value: str) -> str | None:
    """A genuinely clean extracted value is short and has no embedded
    label-looking text — used to decide whether the naive per-line capture
    (which took everything to end-of-line) is trustworthy as-is, or whether
    the field-boundary-aware fallback should be preferred instead."""
    value = re.sub(r"\s+", " ", value).strip(" :")
    if not value or len(value) > 60 or ":" in value:
        return None
    return value


def _extract_identity_fallback(pages: list[ExtractedPage]) -> tuple[str | None, str | None, str | None]:
    """Field-boundary-aware fallback for a real-world header line that packs
    more than one "Label: Value" pair onto a single physical line — returns
    (name, registration_id, gender), any of which may be None. Purely
    generic label matching; never keyed to any specific patient's name."""
    for page in pages:
        name_match = _NAME_FIELD_RE.search(page.text)
        name = _clean_identity_value(name_match.group(1)) if name_match else None
        if not name:
            continue
        regno_match = _REGNO_FIELD_RE.search(page.text)
        gender_match = _GENDER_FIELD_RE.search(page.text)
        return (
            name,
            regno_match.group(1) if regno_match else None,
            gender_match.group(1).capitalize() if gender_match else None,
        )
    return None, None, None


def extract_patient_document_data(extraction: PdfExtractionResult) -> PatientDocumentData:
    """Scan "Label: Value" lines across every extracted page for the
    structured categories below. Unrecognized labels are left out rather
    than guessed; a page with no recognizable label still contributes
    nothing to the structured lists, but every page's own text is always
    kept as a narrative knowledge record (see module docstring) so the
    document remains semantically searchable either way."""
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

    clean_name = _clean_identity_value(patient_name) if patient_name else None
    gender: str | None = None
    if not clean_name:
        # The naive capture is missing or garbled (two fields shared one
        # line) — recover a clean name/registration-id/gender generically.
        fallback_name, fallback_regno, gender = _extract_identity_fallback(extraction.pages)
        clean_name = fallback_name
        if fallback_regno and not patient_id:
            patient_id = fallback_regno
    if not clean_name:
        # Neither colon-anchored strategy matched at all — try the
        # label-on-its-own-line, value-on-the-next-line layout.
        fallback_name, fallback_id, fallback_gender = _extract_label_next_line_fields(extraction.pages)
        clean_name = fallback_name
        gender = gender or fallback_gender
        if fallback_id and not patient_id:
            patient_id = fallback_id

    if patient_id or clean_name:
        first, _, last = (clean_name or "").partition(" ")
        data.patient = PatientInfo(
            external_patient_id=patient_id,
            first=first or None,
            last=last or None,
            gender=gender,
        )

    for page in extraction.pages:
        text = re.sub(r"[ \t]+", " ", page.text).strip()
        if text:
            data.narrative_sections.append(NarrativeSection(content=text[:_MAX_NARRATIVE_CHARS], source_page=page.page_number))

    return data


def find_or_create_patient(
    db: Session, info: PatientInfo | None, source_document_id: str, source_type: str = "UPLOADED_PDF"
) -> tuple[Patient | None, bool]:
    """Deduplicates on external_patient_id + name; never silently merges on
    name alone. An ambiguous case (same name, different external id) still
    creates a new row — flagging for review is Phase 3+ UI work, not a
    reason to guess here. Returns (patient, created) — the caller uses
    `created` to decide whether the uploader needs a new PatientAssignment
    (see app.api.upload — a brand-new patient has no assignment at all yet,
    which previously left the very person who just uploaded their records
    unable to ask about them)."""
    if info is None or not (info.external_patient_id or info.first or info.last):
        return None, False

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
        return existing, False

    patient = Patient(
        id=new_uuid(),
        external_patient_id=info.external_patient_id,
        first=info.first,
        last=info.last,
        gender=info.gender,
        source_type=source_type,
        source_document_id=source_document_id,
        display_id=_next_display_id(db),
    )
    db.add(patient)
    db.flush()
    return patient, True


def _next_display_id(db: Session) -> str:
    """The next free Pxxx — a genuinely new patient (not one of the clean
    dataset's P001..P100) still gets a clean display id rather than
    showing its raw UUID in the UI (docs/CLEAN_DATASET.md). Compares the
    numeric part: ordering the strings ("P999" > "P1000") would hand out an
    id that already exists once the count passes 999."""
    highest = 0
    for (display_id,) in db.query(Patient.display_id).filter(Patient.display_id.isnot(None)).all():
        match = re.match(r"P(\d+)$", display_id or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"P{highest + 1:03d}"


def _add_knowledge_record(
    db: Session,
    *,
    patient_id: str | None,
    record_type: str,
    record_id: str | None,
    sensitivity: str,
    content: str,
    source_document_id: str,
    source_page: int | None,
    source_section: str | None,
    source_type: str = "UPLOADED_PDF",
) -> str:
    """Mirrors app.services.knowledge_generator's pattern for Synthea data,
    but for PDF-derived rows so an uploaded document's knowledge is
    immediately indexable (see api/upload.py), not just inserted as a
    structured row with no corresponding retrievable text."""
    kr_id = new_uuid()
    db.add(
        KnowledgeRecord(
            id=kr_id,
            patient_id=patient_id,
            record_type=record_type,
            record_id=record_id,
            source_type=source_type,
            source_document_id=source_document_id,
            source_page=source_page,
            source_section=source_section,
            sensitivity=sensitivity,
            content=content,
        )
    )
    return kr_id


def narrative_sections_for_document(result: PdfExtractionResult) -> list[NarrativeSection]:
    """Thin wrapper so app.api.upload's duplicate-repair path can regenerate
    just the narrative knowledge records (never the structured rows, which
    are not idempotent to re-insert) without re-running the full extractor."""
    return extract_patient_document_data(result).narrative_sections


def repair_patient_link(
    db: Session, document: SourceDocument, result: PdfExtractionResult, assign_user_id: str | None
) -> Patient | None:
    """Shared by two callers that both need to fix a document whose patient
    was never resolved: app.api.upload's duplicate-upload repair path (a
    user re-uploads a document that's already in this broken state) and
    scripts/backfill_pdf_documents.py (an offline sweep over every document
    in that state, without anyone re-uploading anything). One tested
    implementation, not two divergent ones.

    Re-runs identity extraction against already-extracted PDF content, links
    the document to the resolved patient, and backfills `patient_id` onto
    any of that document's existing knowledge_records that still have none.
    Returns the resolved Patient, or None if identity still can't be
    determined (or the document already had a patient_id — nothing to do).

    Idempotent: a document that already has a patient_id is a no-op; a
    patient that already exists (matched by external_patient_id or name) is
    reused via `find_or_create_patient`, never duplicated; an assignment is
    only created for `assign_user_id` when the patient was newly created AND
    no active assignment for that (patient, user) pair already exists.

    Deliberately does NOT re-index into Qdrant — this module has no
    dependency on the embedding/vector-store services (app.rag/app.services
    import app.ingestion, never the reverse). The caller re-indexes any
    knowledge_records this function touched."""
    if document.patient_id is not None:
        return None

    normalized = extract_patient_document_data(result)
    patient, patient_created = find_or_create_patient(db, normalized.patient, document.id)
    if patient is None:
        return None

    document.patient_id = patient.id
    db.query(KnowledgeRecord).filter(
        KnowledgeRecord.source_document_id == document.id, KnowledgeRecord.patient_id.is_(None)
    ).update({"patient_id": patient.id})

    if patient_created and assign_user_id:
        existing_assignment = (
            db.query(PatientAssignment)
            .filter(
                PatientAssignment.patient_id == patient.id,
                PatientAssignment.user_id == assign_user_id,
                PatientAssignment.active.is_(True),
            )
            .first()
        )
        if existing_assignment is None:
            db.add(
                PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=assign_user_id, assignment_type="attending")
            )

    db.commit()
    return patient


def map_to_database(
    db: Session, data: PatientDocumentData, source_document_id: str, source_type: str = "UPLOADED_PDF"
) -> tuple[int, list[str], Patient | None, bool]:
    """Inserts every mappable item as a real row in the canonical tables,
    stamped with source_type=UPLOADED_PDF + source_document_id + source_page,
    and a matching knowledge_records row so it's immediately indexable.
    Returns (records_created, new_knowledge_record_ids, patient, patient_created)."""
    patient, patient_created = find_or_create_patient(db, data.patient, source_document_id, source_type)
    patient_id = patient.id if patient else None
    created = 0
    knowledge_record_ids: list[str] = []

    for item in data.conditions:
        record_id = new_uuid()
        db.add(
            Condition(
                id=record_id,
                patient=patient_id,
                description=item.description,
                source_type=source_type,
                source_document_id=source_document_id,
            )
        )
        knowledge_record_ids.append(
            _add_knowledge_record(
                db,
                patient_id=patient_id,
                record_type="condition",
                record_id=record_id,
                sensitivity="clinical",
                content=f"Patient: {patient_id}\nRecord Type: Condition\nCondition: {item.description}",
                source_document_id=source_document_id,
                source_page=item.source_page,
                source_section=item.source_section,
                source_type=source_type,
            )
        )
        created += 1

    for item in data.medications:
        record_id = new_uuid()
        db.add(
            Medication(
                id=record_id,
                patient=patient_id,
                description=item.description,
                source_type=source_type,
                source_document_id=source_document_id,
            )
        )
        knowledge_record_ids.append(
            _add_knowledge_record(
                db,
                patient_id=patient_id,
                record_type="medication",
                record_id=record_id,
                sensitivity="clinical",
                content=f"Patient: {patient_id}\nRecord Type: Medication\nMedication: {item.description}",
                source_document_id=source_document_id,
                source_page=item.source_page,
                source_section=item.source_section,
                source_type=source_type,
            )
        )
        created += 1

    for item in data.allergies:
        record_id = new_uuid()
        db.add(
            Allergy(
                id=record_id,
                patient=patient_id,
                description=item.description,
                severity1=item.severity,
                source_type=source_type,
                source_document_id=source_document_id,
            )
        )
        knowledge_record_ids.append(
            _add_knowledge_record(
                db,
                patient_id=patient_id,
                record_type="allergy",
                record_id=record_id,
                sensitivity="clinical",
                content=f"Patient: {patient_id}\nRecord Type: Allergy\nAllergen: {item.description}",
                source_document_id=source_document_id,
                source_page=item.source_page,
                source_section=item.source_section,
                source_type=source_type,
            )
        )
        created += 1

    for item in data.procedures:
        record_id = new_uuid()
        db.add(
            Procedure(
                id=record_id,
                patient=patient_id,
                description=item.description,
                source_type=source_type,
                source_document_id=source_document_id,
            )
        )
        knowledge_record_ids.append(
            _add_knowledge_record(
                db,
                patient_id=patient_id,
                record_type="procedure",
                record_id=record_id,
                sensitivity="clinical",
                content=f"Patient: {patient_id}\nRecord Type: Procedure\nProcedure: {item.description}",
                source_document_id=source_document_id,
                source_page=item.source_page,
                source_section=item.source_section,
                source_type=source_type,
            )
        )
        created += 1

    for item in data.encounters:
        record_id = new_uuid()
        db.add(
            Encounter(
                id=record_id,
                patient=patient_id,
                description=item.description,
                source_type=source_type,
                source_document_id=source_document_id,
            )
        )
        knowledge_record_ids.append(
            _add_knowledge_record(
                db,
                patient_id=patient_id,
                record_type="encounter",
                record_id=record_id,
                sensitivity="operational",
                content=f"Patient: {patient_id}\nRecord Type: Encounter\nEncounter: {item.description}",
                source_document_id=source_document_id,
                source_page=item.source_page,
                source_section=item.source_section,
                source_type=source_type,
            )
        )
        created += 1

    for item in data.claims:
        record_id = new_uuid()
        db.add(
            Claim(
                id=record_id,
                patientid=patient_id,
                outstandingp=item.outstanding,
                statusp=item.status,
                source_type=source_type,
                source_document_id=source_document_id,
            )
        )
        knowledge_record_ids.append(
            _add_knowledge_record(
                db,
                patient_id=patient_id,
                record_type="claim",
                record_id=record_id,
                sensitivity="finance",
                content=f"Patient: {patient_id}\nRecord Type: Claim\nOutstanding: {item.outstanding}",
                source_document_id=source_document_id,
                source_page=item.source_page,
                source_section=item.source_section,
                source_type=source_type,
            )
        )
        created += 1

    # Always index every page's own text as a generic narrative knowledge
    # record, regardless of what (if anything) the structured parser above
    # recognized — this is the fix for a document whose content simply
    # doesn't match any of the Label:Value categories (e.g. a lab report's
    # test-result tables): previously such a document produced zero
    # knowledge_records and was completely unretrievable despite uploading
    # successfully (progress/DECISIONS.md "PDF retrieval fix"). These do not
    # count toward `created` (no canonical table row backs them — "records
    # created" keeps meaning structured rows), but they do get embedded and
    # indexed, so the upload response can honestly report "0 records
    # created, N chunks indexed" for a document like this.
    display_ref = patient.display_id if patient and patient.display_id else (patient_id or "Unknown")
    unit = "image" if source_type == "OCR_IMAGE" else "page"
    for section in data.narrative_sections:
        knowledge_record_ids.append(
            _add_knowledge_record(
                db,
                patient_id=patient_id,
                record_type="document",
                record_id=None,  # no canonical table row backs a raw narrative page chunk
                sensitivity="clinical",
                content=f"Patient: {display_ref}\nDocument {unit} {section.source_page}\n\n{section.content}",
                source_document_id=source_document_id,
                source_page=section.source_page,
                source_section="ocr_image" if source_type == "OCR_IMAGE" else "document",
                source_type=source_type,
            )
        )

    db.commit()
    return created, knowledge_record_ids, patient, patient_created
