from pydantic import BaseModel

from app.schemas.rag import CitationResponse


class DocumentUploadLimits(BaseModel):
    max_upload_size_mb: int


class DocumentListItem(BaseModel):
    document_id: str
    file_name: str
    status: str
    document_type: str | None = None
    patient_id: str | None = None  # display id, never the raw UUID
    uploaded_by: str | None = None  # uploader's full name, never raw user id
    created_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    total: int


class DocumentStatusResponse(BaseModel):
    document_id: str
    file_name: str
    status: str  # RECEIVED | EXTRACTING | MAPPING | CHUNKING | COMPLETED | NEEDS_REVIEW | FAILED
    patient_id: str | None = None
    uploaded_by: str | None = None
    created_at: str
    page_count: int | None = None
    records_created: int = 0
    chunks_created: int = 0
    error_message: str | None = None


class DocumentQueryRequest(BaseModel):
    question: str
    document_id: str


class DocumentQueryResponse(BaseModel):
    answer: str
    status: str
    citations: list[CitationResponse]
    retrieved_count: int
