"""OCR image upload endpoints (sit beside the PDF uploader in app/api/upload.py,
which is unchanged). The request validates and stores the image synchronously,
then OCR + indexing run as a background task whose progress is reported by the
existing GET /api/documents/{id}/status — real stages, nothing simulated.
"""
import hashlib
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.upload import _DOC_ROLES, _document_authorized, _patient_display_id
from app.auth.deps import require_roles
from app.authorization.context import build_authorization_context
from app.config import get_settings
from app.db.session import get_db, get_session_factory
from app.ingestion.image_prep import ImageValidationError, validate_image
from app.ingestion.ocr_store import load_ocr
from app.models.documents import IngestionJob, KnowledgeRecord, SourceDocument
from app.models.hospital import Patient
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.rag.pipeline import resolve_patient_reference
from app.schemas.documents import ConfirmPatientRequest, ImageUploadResponse, OcrLineResponse, OcrResponse
from app.services.image_ingestion import IN_PROGRESS_STATES, SOURCE_TYPE, indexed_ids, process_image_document

router = APIRouter(prefix="/api/documents", tags=["documents-ocr"])
settings = get_settings()

_STALE_AFTER = timedelta(minutes=15)  # an "in progress" job this old died with a server restart
_UPLOAD_ROLES = (RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.ADMIN)


def _safe_file_name(name: str | None) -> str:
    base = os.path.basename((name or "image").replace("\\", "/"))
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return (base or "image")[:255]


def _authorize_patient(db: Session, user: User, patient_ref: str) -> Patient:
    internal_id = resolve_patient_reference(db, "", patient_ref)
    patient = db.query(Patient).filter(Patient.id == internal_id).first() if internal_id else None
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    ctx = build_authorization_context(db, user)
    if ctx.assigned_patient_ids is not None and patient.id not in ctx.assigned_patient_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this patient.")
    return patient


def _ocr_document_or_404(db: Session, user: User, document_id: str) -> SourceDocument:
    doc = db.query(SourceDocument).filter(SourceDocument.id == document_id).first()
    if doc is None or doc.source_type != SOURCE_TYPE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image document not found.")
    ctx = build_authorization_context(db, user)
    if not _document_authorized(ctx, doc, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this document.")
    return doc


def _new_job(db: Session, document: SourceDocument, stage: str) -> IngestionJob:
    job = IngestionJob(id=new_uuid(), source_document_id=document.id, status=stage, started_at=datetime.utcnow())
    db.add(job)
    return job


def _write_image(document: SourceDocument, data: bytes, extension: str) -> None:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{document.id}{extension}"
    path.write_bytes(data)
    document.storage_path = str(path.relative_to(upload_dir))


def _handle_duplicate(
    db: Session,
    user: User,
    existing: SourceDocument,
    data: bytes,
    patient: Patient | None,
    background: BackgroundTasks,
    session_factory,
) -> ImageUploadResponse:
    """Same bytes uploaded again. Never answers "already uploaded" on faith:
    it verifies the stored file, OCR text, patient link, knowledge records and
    the vectors actually in Qdrant, and resumes whichever step is missing."""
    ctx = build_authorization_context(db, user)
    if not _document_authorized(ctx, existing, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this document.")

    def respond(state: str, message: str) -> ImageUploadResponse:
        return ImageUploadResponse(
            document_id=existing.id,
            file_name=existing.file_name,
            status=state,
            message=message,
            patient_id=_patient_display_id(db, existing.patient_id),
            duplicate=True,
        )

    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.source_document_id == existing.id)
        .order_by(IngestionJob.started_at.desc())
        .first()
    )
    if (
        existing.status in IN_PROGRESS_STATES
        and job is not None
        and job.started_at is not None
        and datetime.utcnow() - job.started_at < _STALE_AFTER
    ):
        return respond(existing.status, "This image is already being processed.")

    stored = load_ocr(existing.id)
    if stored is not None and stored.get("problem"):
        # Identical bytes give identical OCR — reprocessing cannot improve it.
        return respond("NEEDS_REVIEW", stored["problem"])

    confirm_identity = False
    if patient is not None and existing.patient_id is None and existing.status == "NEEDS_REVIEW":
        existing.patient_id = patient.id
        confirm_identity = True
    elif existing.status == "NEEDS_REVIEW" and existing.patient_id is None:
        return respond("NEEDS_REVIEW", (job.error_message if job else None) or "Awaiting patient confirmation.")

    file_ok = bool(existing.storage_path) and (Path(settings.upload_dir) / existing.storage_path).is_file()
    records = (
        db.query(KnowledgeRecord)
        .filter(KnowledgeRecord.source_document_id == existing.id, KnowledgeRecord.source_type == SOURCE_TYPE)
        .all()
    )
    complete = (
        existing.status == "COMPLETED"
        and file_ok
        and stored is not None
        and existing.patient_id is not None
        and bool(records)
        and {r.id for r in records} <= indexed_ids(records)
    )
    if complete:
        return respond("COMPLETED", f"This image was already uploaded and is ready ({len(records)} searchable chunk(s)).")

    # Something is missing — repair in place. The original bytes are in hand,
    # so a lost file is simply rewritten.
    if not file_ok:
        validated = validate_image(data, existing.file_name, settings.ocr_max_image_pixels)
        _write_image(existing, data, validated.extension)
    _new_job(db, existing, "RECEIVED")
    existing.status = "RECEIVED"
    db.commit()
    background.add_task(
        process_image_document, session_factory, existing.id, user_id=user.id, identity_confirmed=confirm_identity
    )
    return respond("RECEIVED", "This image was uploaded before but was not fully searchable — repairing it now.")


@router.post("/upload-image", response_model=ImageUploadResponse)
async def upload_image(
    background: BackgroundTasks,
    file: UploadFile,
    patient_id: str | None = Form(default=None),
    user: User = Depends(require_roles(*_UPLOAD_ROLES)),
    db: Session = Depends(get_db),
    session_factory=Depends(get_session_factory),
) -> ImageUploadResponse:
    file_name = _safe_file_name(file.filename)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"File exceeds the {settings.max_upload_size_mb}MB upload limit."
        )

    try:
        validated = validate_image(data, file_name, settings.ocr_max_image_pixels)
    except ImageValidationError as exc:
        code = status.HTTP_400_BAD_REQUEST if exc.unsupported else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    # The client only ever proposes a patient; the server decides whether the
    # authenticated user may attach anything to them.
    patient = _authorize_patient(db, user, patient_id) if patient_id else None

    file_hash = hashlib.sha256(data).hexdigest()
    existing = db.query(SourceDocument).filter(SourceDocument.file_hash == file_hash).first()
    if existing is not None:
        return _handle_duplicate(db, user, existing, data, patient, background, session_factory)

    document = SourceDocument(
        id=new_uuid(),
        file_name=file_name,
        file_hash=file_hash,
        source_type=SOURCE_TYPE,
        document_type="image",
        patient_id=patient.id if patient else None,
        uploaded_by=user.id,
        status="VALIDATING",
    )
    db.add(document)
    db.flush()
    _write_image(document, data, validated.extension)
    _new_job(db, document, "VALIDATING")
    db.commit()

    background.add_task(process_image_document, session_factory, document.id, user_id=user.id)
    return ImageUploadResponse(
        document_id=document.id,
        file_name=file_name,
        status="VALIDATING",
        message="Image received. Reading its text now.",
        patient_id=_patient_display_id(db, document.patient_id),
    )


@router.get("/{document_id}/ocr", response_model=OcrResponse)
def get_ocr_text(
    document_id: str,
    user: User = Depends(require_roles(*_DOC_ROLES)),
    db: Session = Depends(get_db),
) -> OcrResponse:
    """The extracted text and per-line boxes, authorization-checked exactly
    like the image file itself. Available for an image sent to review too, so
    the user can see what was read before confirming anything."""
    doc = _ocr_document_or_404(db, user, document_id)
    stored = load_ocr(doc.id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No OCR text is available for this image yet.")
    return OcrResponse(
        document_id=doc.id,
        width=stored["width"],
        height=stored["height"],
        mean_confidence=stored["mean_confidence"],
        quality=stored["quality"],
        problem=stored.get("problem"),
        text="\n".join(ln["text"] for ln in stored["lines"]),
        lines=[OcrLineResponse(**ln) for ln in stored["lines"]],
    )


@router.post("/{document_id}/confirm-patient", response_model=ImageUploadResponse)
def confirm_patient(
    document_id: str,
    payload: ConfirmPatientRequest,
    background: BackgroundTasks,
    user: User = Depends(require_roles(*_UPLOAD_ROLES)),
    db: Session = Depends(get_db),
    session_factory=Depends(get_session_factory),
) -> ImageUploadResponse:
    """Resolves an image sent to review for an identity reason. The user must
    be allowed to see the document AND the patient they are attaching it to;
    the confirmation is then indexed through the normal pipeline."""
    doc = _ocr_document_or_404(db, user, document_id)
    if doc.status != "NEEDS_REVIEW":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This image is not waiting for a patient confirmation.")
    stored = load_ocr(doc.id)
    if stored is None or stored.get("problem"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The text in this image could not be read reliably, so confirming a patient cannot make it searchable.",
        )
    patient = _authorize_patient(db, user, payload.patient_id)
    doc.patient_id = patient.id
    doc.status = "MAPPING"
    _new_job(db, doc, "MAPPING")
    db.commit()
    background.add_task(process_image_document, session_factory, doc.id, user_id=user.id, identity_confirmed=True)
    return ImageUploadResponse(
        document_id=doc.id,
        file_name=doc.file_name,
        status="MAPPING",
        message="Patient confirmed. Indexing the image text now.",
        patient_id=patient.display_id or patient.id,
    )
