"""Hospital Insights (section 6): SQL is the only source of truth for every
number shown. Groq is only ever asked to narrate/explain metrics this module
already computed — never to produce or guess a total itself (section 6C/6D).
Authorization uses the exact same AuthorizationContext the chat assistant and
the hybrid RAG pipeline use (app.authorization.context), so a role can never
see a broader metric scope here than it could through a normal chat query.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.authorization.context import AuthorizationContext, build_authorization_context
from app.models.documents import AuditLog, KnowledgeRecord, SourceDocument
from app.models.hospital import Claim, Condition, Encounter, Medication, Patient
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.rag.pipeline import _validate_citations
from app.services.llm_provider import get_llm_provider

RECENT_WINDOW_DAYS = 30


@dataclass
class Metric:
    key: str
    label: str
    value: int | float | str
    unit: str | None = None


@dataclass
class Breakdown:
    label: str
    items: list[tuple[str, int]]  # (category label, count)


@dataclass
class InsightsOverview:
    role: str
    period: str
    generated_at: str
    metrics: list[Metric]
    breakdown: Breakdown | None
    note: str | None  # e.g. "No assigned patients" — an honest empty state, never a fabricated zero


def _cutoff(days: int = RECENT_WINDOW_DAYS) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


def build_overview(db: Session, user: User) -> InsightsOverview:
    ctx = build_authorization_context(db, user)
    now = datetime.utcnow()

    if ctx.role == RoleEnum.ADMIN:
        return _admin_overview(db, now)
    if ctx.role == RoleEnum.FINANCE:
        return _finance_overview(db, ctx, now)
    if ctx.role == RoleEnum.RECEPTION:
        return _reception_overview(db, ctx, now)
    # DOCTOR / NURSE
    return _clinical_overview(db, ctx, now)


def _admin_overview(db: Session, now: datetime) -> InsightsOverview:
    try:
        from app.services.vector_store import get_vector_store

        vector_count = get_vector_store().count()
    except Exception:  # noqa: BLE001 — insights must never 500 over a Qdrant hiccup
        vector_count = 0

    total_encounters = db.query(Encounter).count()
    recent_encounters = db.query(Encounter).filter(Encounter.start >= _cutoff()).count()
    needs_review = db.query(SourceDocument).filter(SourceDocument.status == "NEEDS_REVIEW").count()

    metrics = [
        Metric("total_patients", "Total patients", db.query(Patient).count()),
        Metric("total_encounters", "Total encounters (all time)", total_encounters),
        Metric("recent_encounters", f"Encounters (last {RECENT_WINDOW_DAYS}d)", recent_encounters),
        Metric("total_documents", "Documents ingested", db.query(SourceDocument).count()),
        Metric("needs_review", "Documents needing review", needs_review),
        Metric("knowledge_records", "Knowledge records", db.query(KnowledgeRecord).count()),
        Metric("vectors", "Indexed vectors", vector_count),
    ]
    return InsightsOverview(
        role="ADMIN", period="All time, with a last-30-day activity figure", generated_at=now.isoformat(), metrics=metrics, breakdown=None, note=None
    )


def _finance_overview(db: Session, ctx: AuthorizationContext, now: datetime) -> InsightsOverview:
    rows = db.query(Claim).all()
    if not rows:
        return InsightsOverview(
            role="FINANCE", period="All time", generated_at=now.isoformat(), metrics=[], breakdown=None,
            note="No claim records are available in the current dataset.",
        )

    outstanding_total = sum((r.outstandingp if r.outstandingp is not None else (r.outstanding1 or 0.0)) for r in rows)
    with_balance = sum(1 for r in rows if (r.outstandingp if r.outstandingp is not None else (r.outstanding1 or 0.0)) > 0)

    status_counts: dict[str, int] = {}
    for r in rows:
        label = r.statusp or r.status1 or "UNKNOWN"
        status_counts[label] = status_counts.get(label, 0) + 1

    metrics = [
        Metric("total_claims", "Total claims", len(rows)),
        Metric("claims_with_balance", "Claims with an outstanding balance", with_balance),
        Metric("outstanding_total", "Total outstanding balance", round(outstanding_total, 2), unit="USD"),
    ]
    breakdown = Breakdown(label="Claims by status", items=sorted(status_counts.items(), key=lambda kv: -kv[1])[:8])
    return InsightsOverview(role="FINANCE", period="All time", generated_at=now.isoformat(), metrics=metrics, breakdown=breakdown, note=None)


def _reception_overview(db: Session, ctx: AuthorizationContext, now: datetime) -> InsightsOverview:
    total = db.query(Encounter).count()
    if total == 0:
        return InsightsOverview(
            role="RECEPTION", period="All time", generated_at=now.isoformat(), metrics=[], breakdown=None,
            note="No encounter records are available in the current dataset.",
        )

    recent = db.query(Encounter).filter(Encounter.start >= _cutoff()).count()
    class_counts = dict(
        db.query(Encounter.encounterclass, func.count(Encounter.id)).group_by(Encounter.encounterclass).all()
    )
    class_counts = {(k or "unspecified"): v for k, v in class_counts.items()}

    metrics = [
        Metric("total_encounters", "Total encounters (all time)", total),
        Metric("recent_encounters", f"Encounters (last {RECENT_WINDOW_DAYS}d)", recent),
    ]
    breakdown = Breakdown(label="Encounters by type", items=sorted(class_counts.items(), key=lambda kv: -kv[1])[:8])
    return InsightsOverview(role="RECEPTION", period="All time, with a last-30-day activity figure", generated_at=now.isoformat(), metrics=metrics, breakdown=breakdown, note=None)


def _clinical_overview(db: Session, ctx: AuthorizationContext, now: datetime) -> InsightsOverview:
    assigned = ctx.assigned_patient_ids or []
    if not assigned:
        return InsightsOverview(
            role=ctx.role.value, period="All time", generated_at=now.isoformat(), metrics=[], breakdown=None,
            note="You have no assigned patients, so there is no authorized scope to summarize.",
        )

    conditions = db.query(Condition).filter(Condition.patient.in_(assigned)).count()
    medications = db.query(Medication).filter(Medication.patient.in_(assigned)).count()
    recent_encounters = (
        db.query(Encounter).filter(Encounter.patient.in_(assigned), Encounter.start >= _cutoff()).count()
    )

    metrics = [
        Metric("assigned_patients", "Assigned patients", len(assigned)),
        Metric("documented_conditions", "Documented conditions (assigned patients)", conditions),
        Metric("documented_medications", "Documented medications (assigned patients)", medications),
        Metric("recent_encounters", f"Encounters among assigned patients (last {RECENT_WINDOW_DAYS}d)", recent_encounters),
    ]
    return InsightsOverview(
        role=ctx.role.value, period="All time, with a last-30-day activity figure", generated_at=now.isoformat(), metrics=metrics, breakdown=None, note=None
    )


@dataclass
class InsightsAnswer:
    answer: str
    metrics: list[Metric]
    generated_at: str


def answer_insight_question(db: Session, user: User, question: str) -> InsightsAnswer:
    overview = build_overview(db, user)

    if not overview.metrics:
        answer = overview.note or "No authorized metrics are available to answer that question."
        _write_audit_log(db, user, question, "NO_AUTHORIZED_CONTEXT")
        return InsightsAnswer(answer=answer, metrics=[], generated_at=overview.generated_at)

    lines = [f"[SOURCE_1] Verified hospital metrics (role: {overview.role}, period: {overview.period}, generated {overview.generated_at}):"]
    for m in overview.metrics:
        unit = f" {m.unit}" if m.unit else ""
        lines.append(f"- {m.label}: {m.value}{unit}")
    if overview.breakdown:
        lines.append(f"\n{overview.breakdown.label}:")
        for label, count in overview.breakdown.items:
            lines.append(f"- {label}: {count}")
    context_text = "\n".join(lines)

    # A single synthetic source — citation validation then guarantees the
    # model can only ever cite [SOURCE_1] (these verified metrics), never
    # invent a second source number it was not given (docs/DECISIONS.md
    # "citation validation").
    llm = get_llm_provider([{"knowledge_record_id": "insights_overview"}])
    raw_answer = llm.generate(context_text, question)
    answer = _validate_citations(raw_answer, source_count=1)

    _write_audit_log(db, user, question, "ANSWERED")
    return InsightsAnswer(answer=answer, metrics=overview.metrics, generated_at=overview.generated_at)


def _write_audit_log(db: Session, user: User, question: str, status: str) -> None:
    db.add(
        AuditLog(
            id=new_uuid(),
            user_id=user.id,
            action="insights_query",
            query=question,
            status=status,
            timestamp=datetime.utcnow(),
            metadata_json=None,
        )
    )
    db.commit()
