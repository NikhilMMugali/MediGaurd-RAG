from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.config import get_settings
from app.db.session import get_db
from app.ingestion.pdf_extractor import PdfExtractionError, extract_pdf
from app.ingestion.pdf_mapper import extract_patient_document_data, map_to_database
from app.models.documents import IngestionJob, SourceDocument
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.schemas.ingestion import UploadResponse

router = APIRouter(prefix="/api/documents", tags=["documents"])
settings = get_settings()


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

    job = IngestionJob(id=new_uuid(), source_document_id=document.id, status="EXTRACTING", started_at=datetime.utcnow())
    db.add(job)
    db.flush()

    # Phase 2 scope: rule-based section mapping into the canonical schema.
    # Chunking, embedding and Qdrant indexing are Phase 3.
    job.status = "MAPPING"
    normalized = extract_patient_document_data(result)

    try:
        records_created = map_to_database(db, normalized, document.id)
    except Exception as exc:  # defend against a malformed mapping, not a reason to lose the upload
        job.status = "FAILED"
        job.error_message = str(exc)
        job.completed_at = datetime.utcnow()
        document.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not map PDF content to the database schema.") from exc

    job.status = "COMPLETED"
    job.records_created = records_created
    job.completed_at = datetime.utcnow()
    document.status = "COMPLETED"
    db.commit()

    return UploadResponse(
        document_id=document.id,
        file_name=result.file_name,
        status="COMPLETED",
        page_count=result.page_count,
        message=f"Extracted {result.page_count} page(s); mapped {records_created} structured record(s) into the database.",
    )
