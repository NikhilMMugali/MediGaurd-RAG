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
    source_type: str = "UPLOADED_PDF"  # UPLOADED_PDF | OCR_IMAGE


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    total: int


class DocumentStatusResponse(BaseModel):
    document_id: str
    file_name: str
    # PDF: RECEIVED | EXTRACTING | MAPPING | CHUNKING | COMPLETED | NEEDS_REVIEW | FAILED
    # OCR image: VALIDATING | OCR_PROCESSING | IDENTIFYING_PATIENT | MAPPING | INDEXING |
    #            COMPLETED | NEEDS_REVIEW | FAILED
    status: str
    patient_id: str | None = None
    uploaded_by: str | None = None
    created_at: str
    page_count: int | None = None
    records_created: int = 0
    chunks_created: int = 0
    error_message: str | None = None
    source_type: str = "UPLOADED_PDF"
    # OCR images only: the engine's own confidence in the text it read.
    ocr_quality: str | None = None  # good | fair | poor
    ocr_mean_confidence: float | None = None


class DocumentQueryRequest(BaseModel):
    question: str
    document_id: str


class DocumentQueryResponse(BaseModel):
    answer: str
    status: str
    citations: list[CitationResponse]
    retrieved_count: int


class ImageUploadResponse(BaseModel):
    document_id: str
    file_name: str
    status: str
    message: str
    patient_id: str | None = None  # display id; None until a patient is resolved
    duplicate: bool = False


class ConfirmPatientRequest(BaseModel):
    patient_id: str  # display id ("P001")


class OcrLineResponse(BaseModel):
    text: str
    confidence: float
    box: list[float]  # [x1, y1, x2, y2] in the original image's pixels


class OcrResponse(BaseModel):
    document_id: str
    width: int
    height: int
    mean_confidence: float
    quality: str
    problem: str | None = None
    text: str
    lines: list[OcrLineResponse]
