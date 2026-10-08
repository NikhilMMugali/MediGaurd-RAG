"""Exact structured-fact answers (docs/DECISIONS.md "hybrid RAG"). These
handlers answer directly from PostgreSQL/SQLAlchemy — never from Qdrant —
for questions the database already has an exact answer to: identity,
medications, conditions, allergies, procedures, encounters, finance, and
date-aware "recent observations." No LLM call is involved, so these answers
can never hallucinate and are built deterministically from the same
authorization-narrowed record types app.rag.pipeline already computes.

Every handler takes the already-authorized `record_types` (the
intersection of query classification and AuthorizationContext — computed
by the caller) and returns `None` when nothing is authorized/available, so
the caller falls back to the standard "I couldn't find enough authorized
information" denial rather than this module ever deciding what counts as
a denial on its own.
"""
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.hospital import Allergy, Claim, Condition, Encounter, Medication, Observation, Patient, Payer, PayerTransition, Procedure

CLINICAL_OBSERVATION_CATEGORIES = ["vital-signs", "laboratory", "exam", "imaging", "procedure", "therapy"]


@dataclass
class StructuredSource:
    record_type: str
    record_id: str
    date: str | None
    source_type: str = "SYNTHEA"
    source_document_id: str | None = None


@dataclass
class StructuredAnswer:
    markdown: str
    sources: list[StructuredSource]


def _fmt_date(value) -> str:
    if value is None:
        return "unknown date"
    if isinstance(value, (datetime, date)):
        return value.strftime("%d %b %Y")
    return str(value)


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _src(row, record_type: str, when) -> StructuredSource:
    """Builds a citation from any ProvenanceMixin row, carrying its real
    source_type/source_document_id so a fact pulled from an uploaded PDF's
    mapped record is still citable back to that PDF, not mislabeled as
    Synthea data (see app.models.provenance.ProvenanceMixin)."""
    return StructuredSource(
        record_type=record_type,
        record_id=row.id,
        date=_iso(when),
        source_type=getattr(row, "source_type", "SYNTHEA"),
        source_document_id=getattr(row, "source_document_id", None),
    )


def answer_identity(db: Session, patient_internal_id: str, display_id: str) -> StructuredAnswer | None:
    patient = db.query(Patient).filter(Patient.id == patient_internal_id).first()
    if patient is None:
        return None

    name = " ".join(p for p in (patient.first, patient.last) if p) or "Unknown"
    age = None
    if patient.birthdate:
        today = date.today()
        birth = patient.birthdate if isinstance(patient.birthdate, date) else patient.birthdate.date()
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))

    lines = [f"Patient {display_id}", "", f"Name: {name}"]
    if age is not None:
        lines.append(f"Age: {age}")
    if patient.gender:
        lines.append(f"Gender: {patient.gender}")

    return StructuredAnswer(markdown="\n".join(lines), sources=[_src(patient, "patient", None)])


def answer_medications(db: Session, patient_internal_id: str, limit: int = 5) -> StructuredAnswer | None:
    rows = (
        db.query(Medication)
        .filter(Medication.patient == patient_internal_id)
        .order_by(Medication.start.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return None

    lines = ["Current/recent medications", ""]
    sources = []
    for row in rows:
        lines.append(f"• {row.description}")
        if row.start:
            lines.append(f"  Started: {_fmt_date(row.start)}")
        if row.stop:
            lines.append(f"  Stopped: {_fmt_date(row.stop)}")
        lines.append("")
        sources.append(_src(row, "medication", row.start))

    return StructuredAnswer(markdown="\n".join(lines).strip(), sources=sources)


def answer_conditions(db: Session, patient_internal_id: str, limit: int = 5) -> StructuredAnswer | None:
    rows = (
        db.query(Condition)
        .filter(Condition.patient == patient_internal_id)
        .order_by(Condition.start.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return None

    lines = ["Documented conditions", ""]
    sources = []
    for row in rows:
        lines.append(f"• {row.description}")
        if row.stop:
            lines.append(f"  {_fmt_date(row.start)} – {_fmt_date(row.stop)}")
        elif row.start:
            lines.append(f"  Since: {_fmt_date(row.start)}")
        lines.append("")
        sources.append(_src(row, "condition", row.start))

    return StructuredAnswer(markdown="\n".join(lines).strip(), sources=sources)


def answer_allergies(db: Session, patient_internal_id: str, limit: int = 5) -> StructuredAnswer | None:
    rows = db.query(Allergy).filter(Allergy.patient == patient_internal_id).order_by(Allergy.start.desc()).limit(limit).all()
    if not rows:
        return None

    lines = ["Documented allergies", ""]
    sources = []
    for row in rows:
        lines.append(f"• {row.description}")
        reaction = row.description1 or row.description2
        if reaction:
            severity = f" ({row.severity1 or row.severity2})" if (row.severity1 or row.severity2) else ""
            lines.append(f"  Reaction: {reaction}{severity}")
        lines.append("")
        sources.append(_src(row, "allergy", row.start))

    return StructuredAnswer(markdown="\n".join(lines).strip(), sources=sources)


def answer_procedures(db: Session, patient_internal_id: str, limit: int = 5) -> StructuredAnswer | None:
    rows = (
        db.query(Procedure)
        .filter(Procedure.patient == patient_internal_id)
        .order_by(Procedure.start.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return None

    lines = ["Documented procedures", ""]
    sources = []
    for row in rows:
        lines.append(f"• {row.description} — {_fmt_date(row.start)}")
        sources.append(_src(row, "procedure", row.start))

    return StructuredAnswer(markdown="\n".join(lines).strip(), sources=sources)


def answer_last_encounter(db: Session, patient_internal_id: str, history: bool = False) -> StructuredAnswer | None:
    limit = 5 if history else 1
    rows = (
        db.query(Encounter)
        .filter(Encounter.patient == patient_internal_id)
        .order_by(Encounter.start.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return None

    if not history:
        row = rows[0]
        lines = [
            "Most recent visit",
            "",
            f"Date: {_fmt_date(row.start)}",
            f"Type: {row.encounterclass or 'unspecified'}",
            f"Description: {row.description or 'unspecified'}",
        ]
        sources = [_src(row, "encounter", row.start)]
    else:
        lines = ["Recent visits", ""]
        sources = []
        for row in rows:
            lines.append(f"• {_fmt_date(row.start)} — {row.description or row.encounterclass or 'visit'}")
            sources.append(_src(row, "encounter", row.start))

    return StructuredAnswer(markdown="\n".join(lines).strip(), sources=sources)


def answer_outstanding_balance(db: Session, patient_internal_id: str, display_id: str) -> StructuredAnswer | None:
    rows = db.query(Claim).filter(Claim.patientid == patient_internal_id).all()
    if not rows:
        return None

    total = 0.0
    sources = []
    nonzero = []
    for row in rows:
        outstanding = row.outstandingp if row.outstandingp is not None else row.outstanding1
        if outstanding:
            total += outstanding
            nonzero.append((row, outstanding))

    nonzero.sort(key=lambda pair: pair[1], reverse=True)
    for row, _ in nonzero[:5]:
        sources.append(_src(row, "claim", row.servicedate))
    if not sources:
        sources.append(_src(rows[0], "claim", rows[0].servicedate))

    markdown = f"Outstanding balance for {display_id}: ${total:,.2f}"
    return StructuredAnswer(markdown=markdown, sources=sources)


def answer_payer(db: Session, patient_internal_id: str) -> StructuredAnswer | None:
    transition = (
        db.query(PayerTransition)
        .filter(PayerTransition.patient == patient_internal_id)
        .order_by(PayerTransition.start_date.desc())
        .first()
    )
    if transition is None or not transition.payer:
        return None

    payer = db.query(Payer).filter(Payer.id == transition.payer).first()
    name = payer.name if payer else "Unknown payer"
    return StructuredAnswer(markdown=f"Payer: {name}", sources=[_src(transition, "payer_transition", transition.start_date)])


def answer_recent_observations(
    db: Session, patient_internal_id: str, categories: list[str] | None = None, limit: int = 8
) -> StructuredAnswer | None:
    query = db.query(Observation).filter(Observation.patient == patient_internal_id)
    query = query.filter(Observation.category.in_(categories or CLINICAL_OBSERVATION_CATEGORIES))

    latest_date_row = query.order_by(Observation.date.desc()).first()
    if latest_date_row is None or latest_date_row.date is None:
        return None

    rows = (
        query.filter(Observation.date == latest_date_row.date)
        .order_by(Observation.category)
        .limit(limit)
        .all()
    )

    lines = ["Recent observations", ""]
    sources = []
    for row in rows:
        unit = f" {row.units}" if row.units else ""
        lines.append(f"• {row.description}: {row.value}{unit}")
        sources.append(_src(row, "observation", row.date))
    lines.append("")
    lines.append(f"All listed values are from the most recent available observation date ({_fmt_date(latest_date_row.date)}).")

    return StructuredAnswer(markdown="\n".join(lines).strip(), sources=sources)


# record_type -> (handler, needs display_id). "allergy"/"procedure"/etc.
# are query_classification's intent labels — see app.rag.pipeline's caller.
STRUCTURED_HANDLERS = {
    "patient_identity": lambda db, pid, display_id, ctx: answer_identity(db, pid, display_id),
    "medication": lambda db, pid, display_id, ctx: answer_medications(db, pid),
    "condition": lambda db, pid, display_id, ctx: answer_conditions(db, pid),
    "allergy": lambda db, pid, display_id, ctx: answer_allergies(db, pid),
    "procedure": lambda db, pid, display_id, ctx: answer_procedures(db, pid),
    "encounter": lambda db, pid, display_id, ctx: answer_last_encounter(db, pid, history=ctx.get("history", False)),
    "finance_outstanding": lambda db, pid, display_id, ctx: answer_outstanding_balance(db, pid, display_id),
    "finance_payer": lambda db, pid, display_id, ctx: answer_payer(db, pid),
    "observation": lambda db, pid, display_id, ctx: answer_recent_observations(db, pid, ctx.get("categories")),
}


def answer_summary(db: Session, patient_internal_id: str, display_id: str, allowed_record_types: list[str]) -> StructuredAnswer:
    patient = db.query(Patient).filter(Patient.id == patient_internal_id).first()
    lines = [f"Patient {display_id}", ""]
    sources = [_src(patient, "patient", None)] if patient else []

    clinical_lines = []
    if "condition" in allowed_record_types:
        n = db.query(Condition).filter(Condition.patient == patient_internal_id).count()
        clinical_lines.append(f"• Conditions: {n} documented")
    if "medication" in allowed_record_types:
        n = db.query(Medication).filter(Medication.patient == patient_internal_id).count()
        clinical_lines.append(f"• Medications: {n} documented")
    if "allergy" in allowed_record_types:
        n = db.query(Allergy).filter(Allergy.patient == patient_internal_id).count()
        clinical_lines.append(f"• Allergies: {n} documented")

    if clinical_lines:
        lines.append("Clinical")
        lines.extend(clinical_lines)
        lines.append("")

    activity_lines = []
    if "observation" in allowed_record_types:
        n = (
            db.query(Observation)
            .filter(Observation.patient == patient_internal_id, Observation.category.in_(CLINICAL_OBSERVATION_CATEGORIES))
            .count()
        )
        activity_lines.append(f"• Recent observations: {n} documented")
    if "encounter" in allowed_record_types:
        latest = (
            db.query(Encounter)
            .filter(Encounter.patient == patient_internal_id)
            .order_by(Encounter.start.desc())
            .first()
        )
        if latest:
            activity_lines.append(f"• Latest encounter: {_fmt_date(latest.start)}")
            sources.append(_src(latest, "encounter", latest.start))
    if "procedure" in allowed_record_types:
        n = db.query(Procedure).filter(Procedure.patient == patient_internal_id).count()
        activity_lines.append(f"• Recent procedures: {n} documented")

    if activity_lines:
        lines.append("Recent activity")
        lines.extend(activity_lines)
        lines.append("")

    # Only finance/operational-scoped roles (Finance, Admin) ever reach
    # this — a Doctor/Nurse's allowed_record_types never includes "claim",
    # so this section simply never renders for them (section 42 "role-based
    # answer quality": never let the summary leak a domain the role can't see).
    other_lines = []
    if "claim" in allowed_record_types:
        n = db.query(Claim).filter(Claim.patientid == patient_internal_id).count()
        if n:
            other_lines.append(f"• Claims: {n} documented")
    if other_lines:
        lines.append("Other authorized information")
        lines.extend(other_lines)
        lines.append("")

    lines.append("I can provide more detail on any of these areas.")
    return StructuredAnswer(markdown="\n".join(lines).strip(), sources=sources)
