from pydantic import BaseModel, Field


class RagQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Optional precision aid: Synthea patient ids are UUIDs, not human-
    # friendly codes, so callers may pass one explicitly instead of relying
    # on it appearing literally in free text. This is never a security
    # parameter — it only narrows *which* already-authorized patient is
    # meant; authorization itself always comes from the server-side user.
    patient_id: str | None = None


class CitationResponse(BaseModel):
    source_id: str
    source_type: str
    record_id: str | None = None
    file_name: str | None = None
    page: int | None = None
    section: str | None = None
    # The record's own event date (ISO date string), when known — lets the
    # frontend show "Observation record · 12 Sep 2026" instead of a raw
    # UUID (docs/DECISIONS.md "RAG quality fix").
    date: str | None = None
    # The patient's clean display id ("P001"), never the raw internal UUID
    # (docs/CLEAN_DATASET.md).
    patient_id: str | None = None
    # The actual retrieved text this citation is grounded in — lets the
    # frontend's PDF viewer locate/highlight this passage on the cited page.
    evidence_text: str | None = None
    # SourceDocument.id — lets the frontend fetch GET /api/documents/{id}/file
    # to open the cited PDF. None when the citation isn't PDF-backed.
    document_id: str | None = None
    # The passage on the cited page that supports the answer — what the PDF
    # viewer highlights (app.rag.highlight). None when nothing matched.
    highlight_text: str | None = None


class RagQueryResponse(BaseModel):
    answer: str
    status: str
    citations: list[CitationResponse]
    retrieved_count: int
    debug: dict | None = None
