from pydantic import BaseModel


class ExtractedPage(BaseModel):
    page_number: int
    text: str
    has_tables: bool = False


class PdfExtractionResult(BaseModel):
    file_name: str
    file_hash: str
    page_count: int
    is_text_extractable: bool
    pages: list[ExtractedPage]


class UploadResponse(BaseModel):
    document_id: str
    file_name: str
    status: str
    page_count: int
    message: str
    # Display id ("P101"), never the raw internal UUID — None if nothing
    # mappable identified a patient at all.
    patient_id: str | None = None
    records_created: int = 0
    chunks_indexed: int = 0
