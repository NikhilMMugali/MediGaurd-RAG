from pydantic import BaseModel

from app.schemas.rag import CitationResponse


class PatientListResponse(BaseModel):
    patient_ids: list[str]
    total: int
    # "assigned" for DOCTOR/NURSE (their real patient_assignments rows);
    # "all" for roles with no patient-level scoping (FINANCE/RECEPTION/ADMIN).
    scope: str


class PatientStatusResponse(BaseModel):
    patient_id: str
    status: str  # "Stable" | "Attention" | "No Recent Information"
    summary: str
    citations: list[CitationResponse]
