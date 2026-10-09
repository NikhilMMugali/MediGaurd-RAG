import hashlib

import fitz  # PyMuPDF

from app.schemas.ingestion import ExtractedPage, PdfExtractionResult


class PdfExtractionError(Exception):
    """Raised when a PDF cannot be safely parsed or contains no usable content."""


# Pages with fewer than this many characters of extracted text are treated as
# non-text (likely scanned) pages, which drives the OCR-fallback decision.
MIN_TEXT_CHARS_PER_PAGE = 20


def extract_pdf(file_bytes: bytes, file_name: str) -> PdfExtractionResult:
    if not file_bytes:
        raise PdfExtractionError(f"'{file_name}' is empty.")

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    try:
        document = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:  # malformed / non-PDF file
        raise PdfExtractionError(f"'{file_name}' could not be parsed as a PDF: {exc}") from exc

    if document.page_count == 0:
        document.close()
        raise PdfExtractionError(f"'{file_name}' contains no pages.")

    pages: list[ExtractedPage] = []
    extractable_pages = 0

    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        text = page.get_text("text").strip()
        has_tables = bool(page.find_tables().tables) if hasattr(page, "find_tables") else False

        if len(text) >= MIN_TEXT_CHARS_PER_PAGE:
            extractable_pages += 1

        pages.append(ExtractedPage(page_number=page_index + 1, text=text, has_tables=has_tables))

    document.close()

    is_text_extractable = extractable_pages > 0
    # No OCR fallback is wired up yet. This used to raise and discard the
    # upload entirely; now the caller (app.api.upload) persists the document
    # with status NEEDS_REVIEW instead of silently losing it — a scanned PDF
    # is a real, expected input, not a malformed one (docs/DATA_FLOW.md "OCR
    # scope").

    return PdfExtractionResult(
        file_name=file_name,
        file_hash=file_hash,
        page_count=len(pages),
        is_text_extractable=is_text_extractable,
        pages=pages,
    )
