from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.authorization.context import build_authorization_context
from app.db.session import get_db
from app.models.hospital import Condition, Encounter, Medication, Patient
from app.models.user import User
from app.rag.pipeline import retrieve_authorized_sources
from app.schemas.admin import PatientSummary
from app.schemas.patients import PatientListResponse, PatientStatusResponse
from app.schemas.rag import CitationResponse

router = APIRouter(prefix="/api/patients", tags=["patients"])

DEFAULT_LIST_LIMIT = 20


@router.get("", response_model=PatientListResponse)
def list_patients(
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientListResponse:
    """Returns only patient ids the current user is authorized to see — the
    same AuthorizationContext the RAG pipeline uses, so the dashboard's
    patient list can never diverge from what /api/rag/query would actually
    answer about. DOCTOR/NURSE get their real assigned patients; other
    roles have no patient-level scope, so a plain paginated id list is
    returned instead (see docs/SECURITY.md "Assigned patient scope: N/A")."""
    ctx = build_authorization_context(db, user)

    if ctx.assigned_patient_ids is not None:
        ids = ctx.assigned_patient_ids[offset : offset + limit]
        return PatientListResponse(patient_ids=ids, total=len(ctx.assigned_patient_ids), scope="assigned")

    total = db.query(Patient).count()
    rows = db.query(Patient.id).order_by(Patient.id).offset(offset).limit(limit).all()
    return PatientListResponse(patient_ids=[r[0] for r in rows], total=total, scope="all")


@router.get("/{patient_id}/summary", response_model=PatientSummary)
def get_patient_summary(
    patient_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientSummary:
    """Row counts only — no clinical content. Admin/debug use; the
    role-filtered patient answer for ordinary users is /api/rag/query."""
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


@router.get("/{patient_id}/status", response_model=PatientStatusResponse)
def get_patient_status(
    patient_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientStatusResponse:
    """A conservative, evidence-based status derived from the SAME
    authorization-aware retrieval used by /api/rag/query — never a second,
    independent "status AI" and never frontend-invented. If retrieval is
    denied or finds nothing authorized, the status is "No Recent
    Information", not a guess. Classification is deterministic (did an
    authorized 'condition' record come back for this patient?) rather than
    free-form LLM text, so it can never drift into an unsupported severity
    claim like "Critical"."""
    outcome = retrieve_authorized_sources(
        db, user, "current clinical status and recent conditions", patient_id=patient_id
    )

    if outcome.status != "OK":
        return PatientStatusResponse(
            patient_id=patient_id,
            status="No Recent Information",
            summary=outcome.denial_answer or "No authorized recent information is available.",
            citations=[],
        )

    has_condition = any(s.get("record_type") == "condition" for s in outcome.sources)
    patient_status = "Attention" if has_condition else "Stable"
    summary = (
        "Authorized records include a documented condition for this patient."
        if has_condition
        else "Authorized records available to your role do not show a condition requiring attention."
    )

    citations = [
        CitationResponse(
            source_id=f"SOURCE_{i+1}",
            source_type=s["source_type"],
            record_id=s.get("knowledge_record_id"),
            file_name=s.get("source_document_id"),
            page=s.get("source_page"),
            section=s.get("source_section") or s.get("record_type"),
        )
        for i, s in enumerate(outcome.sources[:2])
    ]

    return PatientStatusResponse(patient_id=patient_id, status=patient_status, summary=summary, citations=citations)
