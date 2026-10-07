import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.auth.deps import require_roles
from app.config import get_settings
from app.ingestion.pdf_extractor import PdfExtractionError, extract_pdf
from app.models.user import RoleEnum
from app.schemas.ingestion import UploadResponse

router = APIRouter(prefix="/api/documents", tags=["documents"])
settings = get_settings()


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile,
    _user=Depends(require_roles(RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.ADMIN)),
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

    # Phase 1 scope: validate and extract only. Schema mapping, database
    # insertion, chunking, embedding and vector indexing are implemented in
    # Phase 2 (ingestion pipeline) and Phase 3 (RAG indexing).
    return UploadResponse(
        document_id=str(uuid.uuid4()),
        file_name=result.file_name,
        status="EXTRACTED",
        page_count=result.page_count,
        message="PDF text extracted successfully. Schema mapping and indexing are not yet wired up (Phase 2/3).",
    )
