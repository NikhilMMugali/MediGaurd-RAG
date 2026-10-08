from pydantic import BaseModel


class DatabaseStats(BaseModel):
    patients: int
    encounters: int
    conditions: int
    medications: int
    observations: int
    allergies: int
    procedures: int
    claims: int
    claims_transactions: int
    knowledge_records: int
    documents: int
    vectors: int


class IngestionJobStatus(BaseModel):
    id: str
    source_document_id: str
    status: str
    records_created: int
    chunks_created: int
    error_message: str | None = None


class RecentUpload(BaseModel):
    file_name: str
    status: str
    created_at: str
    patient_id: str | None = None  # display id, never the raw UUID


class RecentSecurityEvent(BaseModel):
    status: str  # "DENIED" | "NO_AUTHORIZED_CONTEXT"
    role: str | None = None
    timestamp: str
    reason: str | None = None


class RecentActivity(BaseModel):
    recent_uploads: list[RecentUpload]
    recent_security_events: list[RecentSecurityEvent]


class PatientSummary(BaseModel):
    patient_id: str
    first: str | None
    last: str | None
    birthdate: str | None
    condition_count: int
    medication_count: int
    encounter_count: int
