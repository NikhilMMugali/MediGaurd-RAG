"""Intermediate, validated representation of what was found in an uploaded
PDF, between raw extraction (Phase 1) and canonical database rows. Every
item carries source_page/source_section provenance; missing information is
left as None, never guessed (docs/DATA_FLOW.md step 7-9)."""
from pydantic import BaseModel


class ExtractedItem(BaseModel):
    source_page: int | None = None
    source_section: str | None = None
    confidence: float | None = None


class PatientInfo(ExtractedItem):
    external_patient_id: str | None = None
    first: str | None = None
    last: str | None = None
    birthdate: str | None = None
    gender: str | None = None


class ConditionItem(ExtractedItem):
    description: str
    start: str | None = None
    stop: str | None = None


class MedicationItem(ExtractedItem):
    description: str
    start: str | None = None
    stop: str | None = None


class AllergyItem(ExtractedItem):
    description: str
    severity: str | None = None
    reaction: str | None = None


class ProcedureItem(ExtractedItem):
    description: str
    start: str | None = None


class EncounterItem(ExtractedItem):
    description: str | None = None
    start: str | None = None
    stop: str | None = None


class ClaimItem(ExtractedItem):
    outstanding: float | None = None
    status: str | None = None


class NarrativeSection(ExtractedItem):
    content: str


class PatientDocumentData(BaseModel):
    """The full normalized payload produced from one uploaded PDF."""

    patient: PatientInfo | None = None
    encounters: list[EncounterItem] = []
    conditions: list[ConditionItem] = []
    medications: list[MedicationItem] = []
    allergies: list[AllergyItem] = []
    procedures: list[ProcedureItem] = []
    claims: list[ClaimItem] = []
    narrative_sections: list[NarrativeSection] = []
