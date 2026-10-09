"""Builds the AuthorizationContext for the current user straight from
PostgreSQL (docs/SECURITY.md) — never from anything the client sends. This
is the single place role → allowed-record-type/sensitivity/patient-scope
logic lives; app.authorization.qdrant_filter turns the result into the
actual Qdrant filter, and app.rag.pipeline is the only caller.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.user import RoleEnum, User
from app.models.ward import PatientAssignment

CLINICAL_RECORD_TYPES = [
    "condition",
    "medication",
    "observation",
    "allergy",
    "procedure",
    "careplan",
    "immunization",
    "imaging_study",
    "device",
    # Generic page-level narrative text from an uploaded PDF that doesn't
    # map to any of the structured types above (e.g. a lab report's test
    # tables) — see app.ingestion.pdf_mapper's per-page fallback. Without
    # this, such a document's only knowledge_records would never match any
    # role's allowed_record_types and would be structurally unretrievable
    # regardless of correct patient/authorization resolution.
    "document",
]
OPERATIONAL_RECORD_TYPES = ["encounter"]
FINANCE_RECORD_TYPES = ["claim", "claim_transaction", "payer", "payer_transition"]

# Role -> (allowed record_types, allowed sensitivity labels, patient-scoped?)
# "patient-scoped" roles only ever see rows for patients explicitly assigned
# to them (docs/SECURITY.md "Assigned patient scope").
ROLE_POLICY: dict[RoleEnum, tuple[list[str], list[str], bool]] = {
    RoleEnum.DOCTOR: (CLINICAL_RECORD_TYPES + OPERATIONAL_RECORD_TYPES, ["clinical", "operational"], True),
    RoleEnum.NURSE: (CLINICAL_RECORD_TYPES + OPERATIONAL_RECORD_TYPES, ["clinical", "operational"], True),
    RoleEnum.FINANCE: (FINANCE_RECORD_TYPES, ["finance"], False),
    RoleEnum.RECEPTION: (OPERATIONAL_RECORD_TYPES, ["operational"], False),
    RoleEnum.ADMIN: (
        CLINICAL_RECORD_TYPES + OPERATIONAL_RECORD_TYPES + FINANCE_RECORD_TYPES,
        ["clinical", "operational", "finance"],
        False,
    ),
}


@dataclass
class AuthorizationContext:
    user_id: str
    role: RoleEnum
    department_id: str | None
    allowed_record_types: list[str]
    allowed_sensitivity: list[str]
    # None means "no patient-level restriction" (finance/reception/admin).
    # An empty list means "patient-scoped role with zero assignments" —
    # deliberately distinct from None so the filter denies everything
    # rather than accidentally allowing everything.
    assigned_patient_ids: list[str] | None


def build_authorization_context(db: Session, user: User) -> AuthorizationContext:
    record_types, sensitivity, patient_scoped = ROLE_POLICY[user.role]

    assigned_patient_ids: list[str] | None = None
    if patient_scoped:
        rows = (
            db.query(PatientAssignment.patient_id)
            .filter(PatientAssignment.user_id == user.id, PatientAssignment.active.is_(True))
            .all()
        )
        assigned_patient_ids = [r[0] for r in rows]

    return AuthorizationContext(
        user_id=user.id,
        role=user.role,
        department_id=user.department_id,
        allowed_record_types=record_types,
        allowed_sensitivity=sensitivity,
        assigned_patient_ids=assigned_patient_ids,
    )
