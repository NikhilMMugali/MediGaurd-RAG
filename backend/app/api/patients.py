import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.authorization.context import build_authorization_context
from app.db.session import get_db
from app.models.hospital import Condition, Encounter, Medication, Patient
from app.models.user import User
from app.schemas.admin import PatientSummary
from app.schemas.patients import PatientListResponse, PatientStatusResponse
from app.schemas.rag import CitationResponse

router = APIRouter(prefix="/api/patients", tags=["patients"])

DEFAULT_LIST_LIMIT = 20
_DISPLAY_ID_RE = re.compile(r"^P\d{3,}$", re.IGNORECASE)


def _display_ids_for(db: Session, internal_ids: list[str]) -> dict[str, str]:
    """Internal id -> display id ('P001'), falling back to the internal
    id itself for a patient with none set (e.g. one introduced by an
    uploaded PDF before the next Pxxx is assigned — see
    docs/CLEAN_DATASET.md)."""
    if not internal_ids:
        return {}
    rows = db.query(Patient.id, Patient.display_id).filter(Patient.id.in_(internal_ids)).all()
    found = {pid: (display or pid) for pid, display in rows}
    return {pid: found.get(pid, pid) for pid in internal_ids}


def _resolve_to_internal_id(db: Session, patient_id: str) -> str:
    """A path param may be the clean display id ('P001') the UI actually
    shows, or a raw internal id for direct API/admin use — resolve the
    former, pass the latter through unchanged."""
    if _DISPLAY_ID_RE.match(patient_id):
        patient = db.query(Patient).filter(Patient.display_id == patient_id.upper()).first()
        return patient.id if patient else patient_id
    return patient_id


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
    returned instead (see docs/SECURITY.md "Assigned patient scope: N/A").
    Ids returned are the clean display ids ("P001") — never the raw
    internal UUID (docs/CLEAN_DATASET.md)."""
    ctx = build_authorization_context(db, user)

    if ctx.assigned_patient_ids is not None:
        page = ctx.assigned_patient_ids[offset : offset + limit]
        display_by_id = _display_ids_for(db, page)
        return PatientListResponse(
            patient_ids=[display_by_id[pid] for pid in page], total=len(ctx.assigned_patient_ids), scope="assigned"
        )

    total = db.query(Patient).count()
    rows = db.query(Patient.id, Patient.display_id).order_by(Patient.id).offset(offset).limit(limit).all()
    return PatientListResponse(patient_ids=[display or pid for pid, display in rows], total=total, scope="all")


@router.get("/{patient_id}/summary", response_model=PatientSummary)
def get_patient_summary(
    patient_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientSummary:
    """Row counts only — no clinical content. Admin/debug use; the
    role-filtered patient answer for ordinary users is /api/rag/query."""
    internal_id = _resolve_to_internal_id(db, patient_id)
    patient = db.query(Patient).filter(Patient.id == internal_id).first()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    return PatientSummary(
        patient_id=patient.display_id or patient.id,
        first=patient.first,
        last=patient.last,
        birthdate=str(patient.birthdate) if patient.birthdate else None,
        condition_count=db.query(Condition).filter(Condition.patient == internal_id).count(),
        medication_count=db.query(Medication).filter(Medication.patient == internal_id).count(),
        encounter_count=db.query(Encounter).filter(Encounter.patient == internal_id).count(),
    )


@router.get("/{patient_id}/status", response_model=PatientStatusResponse)
def get_patient_status(
    patient_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientStatusResponse:
    """A conservative, evidence-based status using the SAME authorization
    rules the RAG pipeline applies (role-allowed record types + real
    patient_assignments scope) — never a second, independent "status AI"
    and never frontend-invented.

    Deliberately does NOT go through embeddings/Qdrant: this is a plain,
    deterministic "does an authorized condition row exist" check, so it
    answers in milliseconds via an indexed SQL query rather than paying an
    embedding-model + full-collection vector search on every dashboard
    card. See progress/DECISIONS.md — the dashboard was previously firing
    one RAG query per visible patient, which is what made it slow; the
    chat endpoint (which genuinely needs semantic retrieval) is unaffected."""
    internal_id = _resolve_to_internal_id(db, patient_id)
    ctx = build_authorization_context(db, user)

    patient_authorized = ctx.assigned_patient_ids is None or internal_id in ctx.assigned_patient_ids
    role_sees_conditions = "condition" in ctx.allowed_record_types

    if not patient_authorized or not role_sees_conditions:
        return PatientStatusResponse(
            patient_id=patient_id,
            status="No Recent Information",
            summary="No authorized recent information is available.",
            citations=[],
        )

    condition = db.query(Condition).filter(Condition.patient == internal_id).first()
    patient_status = "Attention" if condition else "Stable"
    summary = (
        "Authorized records include a documented condition for this patient."
        if condition
        else "Authorized records available to your role do not show a condition requiring attention."
    )
    citations = (
        [
            CitationResponse(
                source_id="SOURCE_1",
                source_type=condition.source_type,
                record_id=condition.id,
                file_name=None,
                page=None,
                section="condition",
                date=str(condition.start) if condition.start else None,
                patient_id=patient_id,
            )
        ]
        if condition
        else []
    )

    return PatientStatusResponse(patient_id=patient_id, status=patient_status, summary=summary, citations=citations)
