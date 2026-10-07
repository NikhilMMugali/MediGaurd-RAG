"""Converts structured hospital-database rows into canonical, human-readable
knowledge text (docs/DATA_FLOW.md step 11 "schema-aware knowledge
generation"). Phase 2 scope: produce the text and provenance only — no
embeddings and no Qdrant writes here (that's Phase 3).

Each generator returns a dict shaped for KnowledgeRecord: patient_id,
record_type, record_id, source_type, content, sensitivity.
"""
from app.models.hospital import Claim, ClaimTransaction, Condition, Encounter, Medication, Observation

CLINICAL = "clinical"
FINANCE = "finance"
OPERATIONAL = "operational"


def from_condition(row: Condition) -> dict:
    return {
        "patient_id": row.patient,
        "record_type": "condition",
        "record_id": row.id,
        "source_type": row.source_type,
        "sensitivity": CLINICAL,
        "content": (
            f"Patient: {row.patient}\n"
            f"Record Type: Condition\n"
            f"Condition: {row.description}\n"
            f"Start: {row.start}\n"
            f"Stop: {row.stop or 'ongoing'}"
        ),
    }


def from_medication(row: Medication) -> dict:
    return {
        "patient_id": row.patient,
        "record_type": "medication",
        "record_id": row.id,
        "source_type": row.source_type,
        "sensitivity": CLINICAL,
        "content": (
            f"Patient: {row.patient}\n"
            f"Record Type: Medication\n"
            f"Medication: {row.description}\n"
            f"Start: {row.start}\n"
            f"Stop: {row.stop or 'ongoing'}"
        ),
    }


def from_observation(row: Observation) -> dict:
    return {
        "patient_id": row.patient,
        "record_type": "observation",
        "record_id": row.id,
        "source_type": row.source_type,
        "sensitivity": CLINICAL,
        "content": (
            f"Patient: {row.patient}\n"
            f"Record Type: Observation\n"
            f"Observation: {row.description}\n"
            f"Value: {row.value} {row.units or ''}\n"
            f"Date: {row.date}"
        ),
    }


def from_encounter(row: Encounter) -> dict:
    return {
        "patient_id": row.patient,
        "record_type": "encounter",
        "record_id": row.id,
        "source_type": row.source_type,
        "sensitivity": OPERATIONAL,
        "content": (
            f"Patient: {row.patient}\n"
            f"Record Type: Encounter\n"
            f"Encounter: {row.description}\n"
            f"Class: {row.encounterclass}\n"
            f"Start: {row.start}\n"
            f"Stop: {row.stop}"
        ),
    }


def from_claim(row: Claim) -> dict:
    outstanding = row.outstandingp if row.outstandingp is not None else row.outstanding1
    return {
        "patient_id": row.patientid,
        "record_type": "claim",
        "record_id": row.id,
        "source_type": row.source_type,
        "sensitivity": FINANCE,
        "content": (
            f"Patient: {row.patientid}\n"
            f"Record Type: Claim\n"
            f"Claim ID: {row.id}\n"
            f"Outstanding: {outstanding}\n"
            f"Status: {row.statusp or row.status1}"
        ),
    }


def from_claim_transaction(row: ClaimTransaction) -> dict:
    return {
        "patient_id": row.patientid,
        "record_type": "claim_transaction",
        "record_id": row.id,
        "source_type": row.source_type,
        "sensitivity": FINANCE,
        "content": (
            f"Patient: {row.patientid}\n"
            f"Record Type: Claim Transaction\n"
            f"Claim ID: {row.claimid}\n"
            f"Type: {row.type}\n"
            f"Amount: {row.amount}\n"
            f"Payments: {row.payments}\n"
            f"Adjustments: {row.adjustments}\n"
            f"Outstanding: {row.outstanding}"
        ),
    }
