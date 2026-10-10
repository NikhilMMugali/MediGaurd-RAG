from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.authorization.context import AuthorizationContext, build_authorization_context
from app.config import get_settings
from app.db.session import get_db
from app.ingestion.pdf_extractor import PdfExtractionError, extract_pdf
from app.ingestion.pdf_mapper import (
    _add_knowledge_record,
    extract_patient_document_data,
    map_to_database,
    narrative_sections_for_document,
    repair_patient_link,
)
from app.models.documents import IngestionJob, KnowledgeRecord, SourceDocument
from app.models.hospital import Patient
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.models.ward import PatientAssignment
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


def _patient_display_id(db: Session, internal_patient_id: str | None) -> str | None:
    if not internal_patient_id:
        return None
    patient = db.query(Patient).filter(Patient.id == internal_patient_id).first()
    return (patient.display_id or patient.id) if patient else internal_patient_id


def _handle_duplicate_upload(db: Session, user: User, existing: SourceDocument, result) -> UploadResponse:
    """A duplicate file hash used to be a dead end — a 409 with no further
    checks, regardless of whether the existing document was ever actually
    indexed. A document that predates this session's fixes (or whose
    indexing failed the first time) would report "already uploaded,
    COMPLETED" while having zero retrievable content, which is exactly the
    reported bug: upload "succeeds" the second time too, but the assistant
    still has nothing to answer from (progress/DECISIONS.md "PDF retrieval
    fix"). This verifies the existing document's actual indexed state and
    repairs it in place when it's missing, instead of re-raising the same
    dead-end 409."""
    ctx = build_authorization_context(db, user)
    if not _document_authorized(ctx, existing, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this document.")

    existing_kr_count = db.query(KnowledgeRecord).filter(KnowledgeRecord.source_document_id == existing.id).count()
    # A document can have chunks AND still need repair — zero chunks is not
    # the only broken state. A document whose patient was never identified
    # (patient_id is None) is just as unretrievable for a patient-scoped
    # role, regardless of how many chunks were indexed under that missing
    # association, so this is checked independently of existing_kr_count.
    needs_patient_link = existing.patient_id is None
    if existing_kr_count > 0 and not needs_patient_link:
        return UploadResponse(
            document_id=existing.id,
            file_name=existing.file_name,
            status=existing.status,
            page_count=result.page_count,
            message=f"This document was already uploaded and is fully indexed ({existing_kr_count} knowledge chunk(s)).",
            patient_id=_patient_display_id(db, existing.patient_id),
            records_created=0,
            chunks_indexed=existing_kr_count,
        )

    if existing.status != "COMPLETED" and existing.status != "NEEDS_REVIEW":
        # FAILED or still mid-processing from a prior attempt — nothing
        # safe to repair automatically; say so rather than guessing.
        return UploadResponse(
            document_id=existing.id,
            file_name=existing.file_name,
            status=existing.status,
            page_count=result.page_count,
            message=f"This document was already uploaded but did not finish processing (status: {existing.status}).",
            patient_id=_patient_display_id(db, existing.patient_id),
            records_created=0,
            chunks_indexed=0,
        )

    # Broken/incomplete duplicate: repair in place. Only identity resolution
    # and narrative knowledge records are (re)created here, never the
    # structured rows — map_to_database's per-row inserts are not
    # idempotent, so re-running it against a document that already has some
    # structured rows would duplicate them.
    patient_linked_now = False
    if needs_patient_link:
        # Shared with scripts/backfill_pdf_documents.py — one tested
        # identity-resolution-and-linking implementation, not two.
        patient_linked_now = repair_patient_link(db, existing, result, assign_user_id=user.id) is not None

    display_ref = _patient_display_id(db, existing.patient_id) or "Unknown"

    new_knowledge_record_ids: list[str] = []
    if existing_kr_count == 0:
        narrative_sections = narrative_sections_for_document(result)
        new_knowledge_record_ids = [
            _add_knowledge_record(
                db,
                patient_id=existing.patient_id,
                record_type="document",
                record_id=None,
                sensitivity="clinical",
                content=f"Patient: {display_ref}\nDocument page {section.source_page}\n\n{section.content}",
                source_document_id=existing.id,
                source_page=section.source_page,
                source_section="document",
            )
            for section in narrative_sections
        ]
        db.commit()

    # Re-index: the brand-new records above, plus every pre-existing record
    # for this document if its patient association just changed (Qdrant
    # upsert is idempotent on the knowledge_record's own stable id, so this
    # simply overwrites the stale payload with the corrected one).
    record_ids_to_index = set(new_knowledge_record_ids)
    if patient_linked_now:
        record_ids_to_index.update(
            r.id for r in db.query(KnowledgeRecord.id).filter(KnowledgeRecord.source_document_id == existing.id).all()
        )
    chunks_indexed = 0
    if record_ids_to_index:
        records = db.query(KnowledgeRecord).filter(KnowledgeRecord.id.in_(record_ids_to_index)).all()
        chunks_indexed = index_records(records, get_embedding_provider(), get_vector_store())

    existing.status = "COMPLETED"
    db.commit()

    message_parts = []
    if patient_linked_now:
        message_parts.append(f"linked it to patient {display_ref}")
    if new_knowledge_record_ids:
        message_parts.append(f"indexed {len(new_knowledge_record_ids)} new knowledge chunk(s)")
    elif patient_linked_now:
        message_parts.append("re-indexed its existing chunks with the corrected patient association")
    message = (
        "This document was already uploaded; " + " and ".join(message_parts) + "."
        if message_parts
        else "This document was already uploaded and is fully indexed."
    )

    return UploadResponse(
        document_id=existing.id,
        file_name=existing.file_name,
        status="COMPLETED",
        page_count=result.page_count,
        message=message,
        patient_id=display_ref if existing.patient_id else None,
        records_created=0,
        chunks_indexed=existing_kr_count + len(new_knowledge_record_ids),
    )


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
        return _handle_duplicate_upload(db, user, existing, result)

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
        records_created, knowledge_record_ids, patient, patient_created = map_to_database(db, normalized, document.id)
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

    # A brand-new patient (not one of the clean dataset's existing P001..P100)
    # has no patient_assignments row at all — without this, the very user who
    # just uploaded the record could never ask about it afterward: a
    # patient-scoped role's assigned_patient_ids wouldn't include a patient
    # nobody has ever been assigned to, so both chat and document Q&A would
    # deny them. The uploader becomes that patient's attending by default,
    # same as any other real-world "who admitted this patient" assignment.
    if patient_created and patient is not None:
        db.add(
            PatientAssignment(
                id=new_uuid(),
                patient_id=patient.id,
                user_id=user.id,
                assignment_type="attending",
            )
        )
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


@router.get("/{document_id}/file")
def get_document_file(
    document_id: str,
    user: User = Depends(require_roles(*_DOC_ROLES)),
    db: Session = Depends(get_db),
):
    """Streams the original PDF bytes for the in-app viewer. Authenticated
    and authorization-checked exactly like every other document endpoint —
    there is no unauthenticated static-file route for uploaded documents
    (section 10B "every document fetch must verify authorization
    server-side"). The frontend fetches this with its Authorization header
    and turns the response into an object URL; it is never a plain <a href>
    or <iframe src> to this path."""
    doc = db.query(SourceDocument).filter(SourceDocument.id == document_id).first()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    ctx = build_authorization_context(db, user)
    if not _document_authorized(ctx, doc, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this document.")

    if not doc.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No stored file for this document.")

    upload_dir = Path(settings.upload_dir).resolve()
    full_path = (upload_dir / doc.storage_path).resolve()
    if upload_dir not in full_path.parents or not full_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file is missing.")

    # inline, not the Starlette default of attachment — the frontend fetches
    # this as a Blob (app/api/client.ts::apiRequestBlob) and never navigates
    # the browser to this URL directly, but a correct Content-Disposition
    # is still the right header to send for a PDF meant to be viewed, not
    # downloaded (section 5 "safe inline PDF rendering where supported").
    return FileResponse(full_path, media_type="application/pdf", filename=doc.file_name, content_disposition_type="inline")


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
                evidence_text=c.evidence_text,
                document_id=c.document_id,
            )
            for c in result.citations
        ],
        retrieved_count=result.retrieved_count,
    )
