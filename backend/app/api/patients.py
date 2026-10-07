from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db.session import get_db
from app.models.hospital import Condition, Encounter, Medication, Patient
from app.models.user import User
from app.schemas.admin import PatientSummary

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get("/{patient_id}/summary", response_model=PatientSummary)
def get_patient_summary(
    patient_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientSummary:
    """Row counts only — no clinical content. A full, role-filtered patient
    answer is Phase 3 (RAG + retrieval-time authorization); this endpoint
    exists now so Phase 2 can demonstrate the database is populated and
    queryable without bypassing the access-control work still to come."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    return PatientSummary(
        patient_id=patient.id,
        first=patient.first,
        last=patient.last,
        birthdate=str(patient.birthdate) if patient.birthdate else None,
        condition_count=db.query(Condition).filter(Condition.patient == patient_id).count(),
        medication_count=db.query(Medication).filter(Medication.patient == patient_id).count(),
        encounter_count=db.query(Encounter).filter(Encounter.patient == patient_id).count(),
    )
