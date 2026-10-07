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


class IngestionJobStatus(BaseModel):
    id: str
    source_document_id: str
    status: str
    records_created: int
    chunks_created: int
    error_message: str | None = None


class PatientSummary(BaseModel):
    patient_id: str
    first: str | None
    last: str | None
    birthdate: str | None
    condition_count: int
    medication_count: int
    encounter_count: int
