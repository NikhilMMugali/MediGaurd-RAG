from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.config import get_settings
from app.db.session import get_db
from app.ingestion.pdf_extractor import PdfExtractionError, extract_pdf
from app.ingestion.pdf_mapper import extract_patient_document_data, map_to_database
from app.models.documents import IngestionJob, KnowledgeRecord, SourceDocument
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.rag.indexing import index_records
from app.schemas.ingestion import UploadResponse
from app.services.embedding_provider import get_embedding_provider
from app.services.vector_store import get_vector_store

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

    job.status = "MAPPING"
    normalized = extract_patient_document_data(result)

    try:
        records_created, knowledge_record_ids = map_to_database(db, normalized, document.id)
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
    )
