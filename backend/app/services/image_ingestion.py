"""OCR image -> searchable knowledge, as a resumable, truthful state machine.

    VALIDATING -> OCR_PROCESSING -> IDENTIFYING_PATIENT -> MAPPING -> INDEXING
        -> COMPLETED | NEEDS_REVIEW | FAILED

Each stage is committed as it begins, so the status endpoint reports what is
actually happening — nothing is simulated and an image is only COMPLETED after
its chunks are indexed AND read back from the vector store.

Lives in app/services (not app/ingestion) because it depends on the embedding
and vector-store services; app/ingestion stays free of them (see pdf_mapper).

Reuses, rather than reimplements: the PDF identity extractor
(extract_patient_document_data), the Patient model and display-id allocator,
the knowledge-record helper, index_records, the embedding provider and the
Qdrant VectorStore. OCR chunks are ordinary knowledge_records
(record_type="document", source_type="OCR_IMAGE"), so the existing classifier,
authorization, retrieval and citation code serve them unchanged.

Rerunning is always safe: OCR is skipped when a stored result exists, records
are only created when none exist, and indexing upserts on the record id.

Identity policy (the dangerous part): an image is never attached to a patient
on a guess. Exact name/ID match to a patient the uploader may access links it;
a brand-new patient is created only from a plausible full name; anything
ambiguous, restricted, or conflicting goes to NEEDS_REVIEW with NOTHING indexed
until an authorized user confirms. Review messages never reveal the existence
or ID of a patient the uploader is not allowed to access.
"""
import difflib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion.image_prep import prepare_for_ocr
from app.ingestion.ocr_engine import OcrResult, OcrUnavailableError, assess_quality, run_ocr
from app.ingestion.ocr_store import load_ocr, result_from_stored, save_ocr
from app.ingestion.pdf_mapper import (
    _add_knowledge_record,
    _looks_like_a_name,
    extract_patient_document_data,
    find_or_create_patient,
)
from app.models.documents import IngestionJob, KnowledgeRecord, SourceDocument
from app.models.hospital import Patient
from app.models.provenance import new_uuid
from app.models.user import User
from app.models.ward import PatientAssignment
from app.rag.indexing import index_records
from app.schemas.ingestion import ExtractedPage, PdfExtractionResult
from app.schemas.pdf_normalization import PatientInfo
from app.services.embedding_provider import get_embedding_provider
from app.services.vector_store import get_vector_store
from app.authorization.context import build_authorization_context

logger = logging.getLogger(__name__)

SOURCE_TYPE = "OCR_IMAGE"

VALIDATING = "VALIDATING"
OCR_PROCESSING = "OCR_PROCESSING"
IDENTIFYING_PATIENT = "IDENTIFYING_PATIENT"
MAPPING = "MAPPING"
INDEXING = "INDEXING"
IN_PROGRESS_STATES = {"RECEIVED", VALIDATING, OCR_PROCESSING, IDENTIFYING_PATIENT, MAPPING, INDEXING}

# ~230 tokens: under MiniLM's 256-token window, so every word of a chunk is
# actually embedded (the PDF path's 3000-char chunks are silently truncated).
CHUNK_CHARS = 900
MAX_OCR_CHARS = 60_000
_FUZZY_MATCH_THRESHOLD = 0.88
_EXPLICIT_MISMATCH_THRESHOLD = 0.6

SessionFactory = Callable[[], Session]


def _letters(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


def _name_key(first: str | None, last: str | None) -> str:
    return _letters(f"{first or ''}{last or ''}")


def chunk_lines(lines: list[str], max_chars: int = CHUNK_CHARS) -> list[str]:
    """Splits OCR lines into chunks at line boundaries — a line (a table cell
    or a sentence fragment) is never cut in half, so a value never gets
    separated from its own unit."""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        if current and size + len(line) + 1 > max_chars:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


@dataclass
class IdentityOutcome:
    patient: Patient | None
    created: bool = False
    review_reason: str | None = None


def _identity_info(ocr_text: str, file_name: str) -> PatientInfo | None:
    result = PdfExtractionResult(
        file_name=file_name,
        file_hash="",
        page_count=1,
        is_text_extractable=True,
        pages=[ExtractedPage(page_number=1, text=ocr_text)],
    )
    return extract_patient_document_data(result).patient


def _user_may_access(db: Session, user: User, patient_id: str) -> bool:
    ctx = build_authorization_context(db, user)
    return ctx.assigned_patient_ids is None or patient_id in ctx.assigned_patient_ids


def resolve_identity(db: Session, document: SourceDocument, user: User, ocr_text: str) -> IdentityOutcome:
    info = _identity_info(ocr_text, document.file_name)
    if info is None or not (info.first and info.last):
        return IdentityOutcome(
            None,
            review_reason=(
                "No patient name could be read from this image. Confirm which patient it belongs to "
                "to make it searchable."
            ),
        )

    wanted = _name_key(info.first, info.last)
    shown_name = f"{info.first} {info.last}"

    exact: list[Patient] = []
    near: list[Patient] = []
    if info.external_patient_id:
        exact = db.query(Patient).filter(Patient.external_patient_id == info.external_patient_id).all()
    if not exact:
        for patient in db.query(Patient).filter(Patient.first.isnot(None), Patient.last.isnot(None)).all():
            key = _name_key(patient.first, patient.last)
            if key == wanted:
                exact.append(patient)
            elif difflib.SequenceMatcher(None, key, wanted).ratio() >= _FUZZY_MATCH_THRESHOLD:
                near.append(patient)

    if len(exact) == 1:
        if _user_may_access(db, user, exact[0].id):
            return IdentityOutcome(exact[0])
        # The single match is outside the uploader's scope: say nothing about who.
        return IdentityOutcome(
            None,
            review_reason=(
                f"The name read from the image ({shown_name}) matches a patient record you are not assigned to. "
                "Ask an administrator or the assigned clinician to confirm the association."
            ),
        )
    if len(exact) > 1:
        return IdentityOutcome(
            None,
            review_reason=(
                f"The name read from the image ({shown_name}) could not be matched to a single patient. "
                "Confirm which patient it belongs to."
            ),
        )
    accessible_near = [p for p in near if _user_may_access(db, user, p.id)]
    if accessible_near:
        options = ", ".join(sorted(p.display_id or p.id for p in accessible_near))
        return IdentityOutcome(
            None,
            review_reason=(
                f"The name read from the image ({shown_name}) is close to an existing patient ({options}) but not identical — "
                "OCR may have misread it. Confirm the patient so a duplicate record is not created."
            ),
        )
    if near:
        return IdentityOutcome(
            None,
            review_reason=(
                f"The name read from the image ({shown_name}) resembles a patient you are not assigned to. "
                "Ask an administrator to confirm the association."
            ),
        )

    if not _looks_like_a_name(shown_name):
        return IdentityOutcome(
            None,
            review_reason=f'The text read as a patient name ("{shown_name}") does not look like a name. Confirm the patient.',
        )
    patient, created = find_or_create_patient(db, info, document.id, SOURCE_TYPE)
    if patient is None:
        return IdentityOutcome(None, review_reason="Could not determine the patient. Please confirm the patient.")
    if created:
        # Existing policy for a brand-new patient (see app.api.upload): the
        # uploader becomes the attending — and ONLY the uploader.
        db.add(PatientAssignment(id=new_uuid(), patient_id=patient.id, user_id=user.id, assignment_type="attending"))
    return IdentityOutcome(patient, created=created)


def explicit_patient_mismatch(db: Session, patient: Patient, ocr_text: str, file_name: str) -> str | None:
    """A user-selected patient is authoritative — unless the name printed on
    the image clearly contradicts it, which is exactly the wrong-chart error
    that must be caught before the text is filed under that patient."""
    info = _identity_info(ocr_text, file_name)
    if info is None or not (info.first and info.last) or not (patient.first and patient.last):
        return None
    ratio = difflib.SequenceMatcher(None, _name_key(patient.first, patient.last), _name_key(info.first, info.last)).ratio()
    if ratio >= _EXPLICIT_MISMATCH_THRESHOLD:
        return None
    return (
        f"The name read from the image ({info.first} {info.last}) does not match the selected patient. "
        "Confirm that this image belongs to them."
    )


def _set_stage(db: Session, document: SourceDocument, job: IngestionJob, stage: str) -> None:
    document.status = stage
    job.status = stage
    db.commit()


def _finish(db: Session, document: SourceDocument, job: IngestionJob, status: str, message: str | None) -> None:
    document.status = status
    job.status = status
    job.error_message = message
    job.completed_at = datetime.utcnow()
    db.commit()


def _latest_job(db: Session, document_id: str) -> IngestionJob:
    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.source_document_id == document_id)
        .order_by(IngestionJob.started_at.desc())
        .first()
    )
    if job is None:
        job = IngestionJob(id=new_uuid(), source_document_id=document_id, status="RECEIVED", started_at=datetime.utcnow())
        db.add(job)
        db.commit()
    return job


def indexed_ids(records: list[KnowledgeRecord]) -> set[str]:
    """Ids actually present in the vector store (read back, not assumed)."""
    ids = [r.id for r in records]
    if not ids:
        return set()
    return {str(p.id) for p in get_vector_store().retrieve_by_ids(ids)}


def process_image_document(
    session_factory: SessionFactory, document_id: str, *, user_id: str, identity_confirmed: bool = False
) -> None:
    settings = get_settings()
    db = session_factory()
    document: SourceDocument | None = None
    job: IngestionJob | None = None
    try:
        document = db.query(SourceDocument).filter(SourceDocument.id == document_id).first()
        user = db.query(User).filter(User.id == user_id).first()
        if document is None or user is None or not document.storage_path:
            return
        job = _latest_job(db, document_id)
        job.started_at = job.started_at or datetime.utcnow()
        job.completed_at = None
        job.error_message = None

        _set_stage(db, document, job, VALIDATING)
        image_path = Path(settings.upload_dir) / document.storage_path
        try:
            image_bytes = image_path.read_bytes()
        except OSError:
            _finish(db, document, job, "FAILED", "The stored image file is missing; please upload it again.")
            return

        # --- OCR (skipped when a stored result exists: resume, not redo) ---
        stored = load_ocr(document.id)
        if stored is None:
            _set_stage(db, document, job, OCR_PROCESSING)
            try:
                result = run_ocr(prepare_for_ocr(image_bytes, settings.ocr_max_side_px))
            except OcrUnavailableError as exc:
                _finish(db, document, job, "FAILED", str(exc))
                return
            quality, problem = assess_quality(result, settings.ocr_min_mean_confidence, settings.ocr_min_text_chars)
            save_ocr(document.id, result, quality, problem)
        else:
            result = result_from_stored(stored)
            quality, problem = stored["quality"], stored.get("problem")

        if problem:
            _finish(db, document, job, "NEEDS_REVIEW", problem)
            return

        ocr_text = result.text[:MAX_OCR_CHARS]

        # --- Patient identity ---
        _set_stage(db, document, job, IDENTIFYING_PATIENT)
        existing = (
            db.query(KnowledgeRecord)
            .filter(KnowledgeRecord.source_document_id == document.id, KnowledgeRecord.source_type == SOURCE_TYPE)
            .all()
        )
        patient: Patient | None = None
        if document.patient_id:
            patient = db.query(Patient).filter(Patient.id == document.patient_id).first()
            if patient is not None and not existing and not identity_confirmed:
                conflict = explicit_patient_mismatch(db, patient, ocr_text, document.file_name)
                if conflict:
                    _finish(db, document, job, "NEEDS_REVIEW", conflict)
                    return
        if patient is None:
            outcome = resolve_identity(db, document, user, ocr_text)
            if outcome.patient is None:
                db.commit()
                _finish(db, document, job, "NEEDS_REVIEW", outcome.review_reason)
                return
            patient = outcome.patient
            document.patient_id = patient.id
            db.commit()

        # --- Knowledge records (chunks with provenance) ---
        _set_stage(db, document, job, MAPPING)
        if not existing:
            display = patient.display_id or patient.id
            chunks = chunk_lines([ln.text for ln in result.lines], CHUNK_CHARS)
            for number, chunk in enumerate(chunks, start=1):
                part = f" (part {number}/{len(chunks)})" if len(chunks) > 1 else ""
                _add_knowledge_record(
                    db,
                    patient_id=patient.id,
                    record_type="document",
                    record_id=None,
                    sensitivity="clinical",
                    content=f"Patient: {display}\nDocument image 1{part}\n\n{chunk}",
                    source_document_id=document.id,
                    source_page=1,
                    source_section="ocr_image",
                    source_type=SOURCE_TYPE,
                )
            db.commit()
        else:
            for record in existing:
                if record.patient_id != patient.id:
                    record.patient_id = patient.id
            db.commit()

        # --- Index, then read back from the vector store before declaring ready ---
        _set_stage(db, document, job, INDEXING)
        records = (
            db.query(KnowledgeRecord)
            .filter(KnowledgeRecord.source_document_id == document.id, KnowledgeRecord.source_type == SOURCE_TYPE)
            .all()
        )
        index_records(records, get_embedding_provider(), get_vector_store())
        missing = {r.id for r in records} - indexed_ids(records)
        if missing:
            _finish(
                db, document, job, "FAILED",
                "The text was read but could not be confirmed in the search index. Upload the image again to repair it.",
            )
            return

        job.records_created = 0
        job.chunks_created = len(records)
        note = (
            f"Text was read with {result.mean_confidence:.0%} average confidence — check important values against the image."
            if quality == "fair"
            else None
        )
        _finish(db, document, job, "COMPLETED", note)
    except Exception:  # noqa: BLE001 — never leave a document stuck mid-stage
        logger.exception("Image processing failed for document %s", document_id)
        try:
            db.rollback()
            if document is not None and job is not None:
                _finish(db, document, job, "FAILED", "Processing failed unexpectedly. Please try uploading the image again.")
        except Exception:  # noqa: BLE001
            logger.exception("Could not record failure for document %s", document_id)
    finally:
        db.close()
