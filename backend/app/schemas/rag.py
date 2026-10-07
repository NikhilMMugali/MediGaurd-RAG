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


class RagQueryResponse(BaseModel):
    answer: str
    status: str
    citations: list[CitationResponse]
    retrieved_count: int
    debug: dict | None = None
