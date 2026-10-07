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
