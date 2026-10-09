from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.authorization.context import AuthorizationContext, build_authorization_context
from app.config import get_settings
from app.db.session import get_db
from app.ingestion.pdf_extractor import PdfExtractionError, extract_pdf
from app.ingestion.pdf_mapper import extract_patient_document_data, map_to_database
from app.models.documents import IngestionJob, KnowledgeRecord, SourceDocument
from app.models.hospital import Patient
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.rag.indexing import index_records
from app.rag.pipeline import run_query
from app.schemas.documents import (
    DocumentListItem,
    DocumentListResponse,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentStatusResponse,
    DocumentUploadLimits,
)
from app.schemas.ingestion import UploadResponse
from app.schemas.rag import CitationResponse
from app.services.embedding_provider import get_embedding_provider
from app.services.vector_store import get_vector_store

router = APIRouter(prefix="/api/documents", tags=["documents"])
settings = get_settings()

_DOC_ROLES = (RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.ADMIN)


def _document_authorized(ctx: AuthorizationContext, doc: SourceDocument, user_id: str) -> bool:
    """A document is visible to: the admin role, whoever uploaded it, or —
    for a patient-scoped role — anyone currently assigned to the patient it
    belongs to. An unassigned document (no patient resolved from it yet) is
    visible only to its uploader and admin, never to every clinical user,
    since there is no patient-assignment fact to check it against."""
    if ctx.role == RoleEnum.ADMIN:
        return True
    if doc.uploaded_by == user_id:
        return True
    if ctx.assigned_patient_ids is not None and doc.patient_id is not None:
        return doc.patient_id in ctx.assigned_patient_ids
    return False


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile,
    user: User = Depends(require_roles(RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.ADMIN)),
    db: Session = Depends(get_db),
) -> UploadResponse:
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported.")

    file_bytes = await file.read()

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the {settings.max_upload_size_mb}MB upload limit.",
        )

    try:
        result = extract_pdf(file_bytes, file.filename)
    except PdfExtractionError as exc:
        # A genuinely malformed/empty file — nothing usable to persist.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    existing = db.query(SourceDocument).filter(SourceDocument.file_hash == result.file_hash).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This file was already uploaded as document {existing.id} ({existing.status}).",
        )

    document = SourceDocument(
        id=new_uuid(),
        file_name=result.file_name,
        file_hash=result.file_hash,
        source_type="UPLOADED_PDF",
        uploaded_by=user.id,
        status="EXTRACTING",
    )
    db.add(document)
    db.flush()

    # Persist the original bytes — extraction only ever produced derived
    # text/structured rows; without this the actual source document would
    # be lost the moment the request finished (section 56 "file storage").
    # Always happens, even for a scanned/no-text PDF below, so the document
    # and its metadata survive for later review rather than vanishing.
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = upload_dir / f"{document.id}.pdf"
    storage_path.write_bytes(file_bytes)
    document.storage_path = str(storage_path.relative_to(upload_dir))

    job = IngestionJob(id=new_uuid(), source_document_id=document.id, status="EXTRACTING", started_at=datetime.utcnow())
    db.add(job)
    db.flush()

    if not result.is_text_extractable:
        # Scanned/image-only PDF — no OCR fallback yet. The file and its
        # metadata are already persisted above; mark for manual review
        # instead of silently indexing nothing or discarding the upload
        # (docs/DATA_FLOW.md "OCR scope").
        job.status = "NEEDS_REVIEW"
        job.error_message = "Scanned/image-only PDF — no extractable text. OCR is not yet supported."
        job.completed_at = datetime.utcnow()
        document.status = "NEEDS_REVIEW"
        db.commit()
        return UploadResponse(
            document_id=document.id,
            file_name=result.file_name,
            status="NEEDS_REVIEW",
            page_count=result.page_count,
            message=(
                f"Stored {result.page_count} page(s), but no extractable text was found. "
                "This looks like a scanned/image-only PDF; OCR is not yet supported, so it has "
                "been saved for manual review rather than indexed."
            ),
            patient_id=None,
            records_created=0,
            chunks_indexed=0,
        )

    job.status = "MAPPING"
    normalized = extract_patient_document_data(result)

    try:
        records_created, knowledge_record_ids, patient = map_to_database(db, normalized, document.id)
    except Exception as exc:  # defend against a malformed mapping, not a reason to lose the upload
        job.status = "FAILED"
        job.error_message = str(exc)
        job.completed_at = datetime.utcnow()
        document.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not map PDF content to the database schema.") from exc

    # Index immediately so the upload is searchable without an app restart
    # or a separate script run (docs/DATA_FLOW.md step 11-13). A failure here
    # does not fail the upload — the structured rows and knowledge_records
    # already committed are real; scripts/index_knowledge.py can catch up
    # later if Qdrant was briefly unavailable.
    job.status = "CHUNKING"
    chunks_indexed = 0
    if knowledge_record_ids:
        try:
            records = db.query(KnowledgeRecord).filter(KnowledgeRecord.id.in_(knowledge_record_ids)).all()
            chunks_indexed = index_records(records, get_embedding_provider(), get_vector_store())
        except Exception as exc:  # noqa: BLE001 — indexing failure must not lose the upload
            job.error_message = f"Indexing deferred: {exc}"

    job.status = "COMPLETED"
    job.records_created = records_created
    job.chunks_created = chunks_indexed
    job.completed_at = datetime.utcnow()
    document.status = "COMPLETED"
    # Was never actually set before — the column existed but every uploaded
    # document's patient_id stayed NULL, which silently broke document-level
    # authorization (a doctor's assigned-patient scope has nothing to match
    # against) and the "Available Documents" patient filter.
    document.patient_id = patient.id if patient else None
    db.commit()

    return UploadResponse(
        document_id=document.id,
        file_name=result.file_name,
        status="COMPLETED",
        page_count=result.page_count,
        message=(
            f"Extracted {result.page_count} page(s); mapped {records_created} structured record(s); "
            f"indexed {chunks_indexed} knowledge chunk(s) into Qdrant."
        ),
        patient_id=(patient.display_id or patient.id) if patient else None,
        records_created=records_created,
        chunks_indexed=chunks_indexed,
    )


@router.get("/limits", response_model=DocumentUploadLimits)
def upload_limits(user: User = Depends(require_roles(*_DOC_ROLES))) -> DocumentUploadLimits:
    return DocumentUploadLimits(max_upload_size_mb=settings.max_upload_size_mb)


@router.get("", response_model=DocumentListResponse)
def list_documents(
    user: User = Depends(require_roles(*_DOC_ROLES)),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    """Authorized documents only — never a global list. Admin sees every
    document; a patient-scoped role (DOCTOR/NURSE) sees documents it
    uploaded itself plus documents belonging to a patient currently
    assigned to it, mirroring the exact same authorization rules the RAG
    pipeline applies (see _document_authorized above)."""
    ctx = build_authorization_context(db, user)

    query = db.query(SourceDocument)
    if ctx.role != RoleEnum.ADMIN:
        conditions = [SourceDocument.uploaded_by == user.id]
        if ctx.assigned_patient_ids:
            conditions.append(SourceDocument.patient_id.in_(ctx.assigned_patient_ids))
        query = query.filter(or_(*conditions))

    docs = query.order_by(SourceDocument.created_at.desc()).all()

    patient_internal_ids = {d.patient_id for d in docs if d.patient_id}
    display_ids = {
        pid: (display or pid)
        for pid, display in db.query(Patient.id, Patient.display_id).filter(Patient.id.in_(patient_internal_ids)).all()
    }
    uploader_ids = {d.uploaded_by for d in docs if d.uploaded_by}
    uploader_names = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(uploader_ids)).all()}

    return DocumentListResponse(
        documents=[
            DocumentListItem(
                document_id=d.id,
                file_name=d.file_name,
                status=d.status,
                document_type=d.document_type,
                patient_id=display_ids.get(d.patient_id),
                uploaded_by=uploader_names.get(d.uploaded_by),
                created_at=d.created_at.isoformat(),
            )
            for d in docs
        ],
        total=len(docs),
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def document_status(
    document_id: str,
    user: User = Depends(require_roles(*_DOC_ROLES)),
    db: Session = Depends(get_db),
) -> DocumentStatusResponse:
    doc = db.query(SourceDocument).filter(SourceDocument.id == document_id).first()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    ctx = build_authorization_context(db, user)
    if not _document_authorized(ctx, doc, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this document.")

    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.source_document_id == document_id)
        .order_by(IngestionJob.started_at.desc())
        .first()
    )

    # Computed live from the stored file rather than a persisted column —
    # keeps the schema minimal and is always accurate even if the document
    # predates this field being tracked at all.
    page_count: int | None = None
    if doc.storage_path:
        try:
            import fitz  # PyMuPDF

            full_path = Path(settings.upload_dir) / doc.storage_path
            with fitz.open(full_path) as pdf:
                page_count = pdf.page_count
        except Exception:  # noqa: BLE001 — status must never 500 over a file-read hiccup
            page_count = None

    display_id = None
    if doc.patient_id:
        patient = db.query(Patient).filter(Patient.id == doc.patient_id).first()
        display_id = (patient.display_id or patient.id) if patient else doc.patient_id
    uploader = db.query(User).filter(User.id == doc.uploaded_by).first() if doc.uploaded_by else None

    return DocumentStatusResponse(
        document_id=doc.id,
        file_name=doc.file_name,
        status=doc.status,
        patient_id=display_id,
        uploaded_by=uploader.full_name if uploader else None,
        created_at=doc.created_at.isoformat(),
        page_count=page_count,
        records_created=job.records_created if job else 0,
        chunks_created=job.chunks_created if job else 0,
        error_message=job.error_message if job else None,
    )


@router.post("/query", response_model=DocumentQueryResponse)
def query_document(
    payload: DocumentQueryRequest,
    user: User = Depends(require_roles(*_DOC_ROLES)),
    db: Session = Depends(get_db),
) -> DocumentQueryResponse:
    """Secure document-focused Q&A (section 5G). Authorization is checked
    here first — a 403 for an unauthorized document never even reaches
    run_query — and the same per-request AuthorizationContext/patient-scope
    checks the chat assistant uses are then applied again inside run_query,
    scoped additionally to this one document's chunks."""
    doc = db.query(SourceDocument).filter(SourceDocument.id == payload.document_id).first()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    ctx = build_authorization_context(db, user)
    if not _document_authorized(ctx, doc, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this document.")

    if doc.status not in ("COMPLETED",):
        return DocumentQueryResponse(
            answer=(
                "This document has not finished processing yet "
                f"(status: {doc.status}), so there is nothing indexed to answer from."
            ),
            status="NO_AUTHORIZED_CONTEXT",
            citations=[],
            retrieved_count=0,
        )

    result = run_query(db, user, payload.question, patient_id=doc.patient_id, document_id=payload.document_id)

    return DocumentQueryResponse(
        answer=result.answer,
        status=result.status,
        citations=[
            CitationResponse(
                source_id=c.source_id,
                source_type=c.source_type,
                record_id=c.record_id,
                file_name=c.file_name,
                page=c.page,
                section=c.section,
                date=c.date,
                patient_id=c.patient_id,
            )
            for c in result.citations
        ],
        retrieved_count=result.retrieved_count,
    )
