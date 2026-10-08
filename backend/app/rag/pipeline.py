"""The secure RAG query pipeline (docs/RAG_DESIGN.md "hybrid retrieval"):

question -> selected-patient context -> AuthorizationContext -> query
classification -> EITHER exact structured DB lookup OR semantic Qdrant
retrieval (never both unfiltered, always authorization-narrowed first) ->
answer assembly -> citation resolution -> audit log.

Per the PS's own principle: use the database when the question requires an
exact fact, semantic RAG when it requires contextual understanding, both
when it requires both, and always apply authorization before either path
touches data. `_authorize_and_classify()` is the one place that computes
the authorization-narrowed record types and resolves which patient (if
any) the question is about — both run_query()'s structured and semantic
branches start from its result, so there is exactly one
retrieval-authorization code path in the app, same as before this
hybrid-routing change.
"""
import re
from dataclasses import dataclass
from datetime import datetime

from qdrant_client.models import Filter
from sqlalchemy.orm import Session

from app.authorization.context import AuthorizationContext, build_authorization_context
from app.authorization.qdrant_filter import build_retrieval_filter
from app.config import get_settings
from app.models.documents import AuditLog, KnowledgeRecord, SourceDocument
from app.models.hospital import Patient
from app.models.provenance import new_uuid
from app.models.user import RoleEnum, User
from app.rag import structured_answers
from app.rag.query_classification import QueryIntent, classify_query
from app.services.embedding_provider import get_embedding_provider
from app.services.llm_provider import get_llm_provider
from app.services.vector_store import get_vector_store

settings = get_settings()

# Synthea ids are UUID-formatted; this lets a pasted id in free-text question
# be honored as an explicit patient reference without a separate API field.
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
# Clean demo-facing patient id ("P001") — what the UI actually shows and
# sends; see Patient.display_id (docs/CLEAN_DATASET.md).
_DISPLAY_ID_RE = re.compile(r"\bP\d{3,}\b", re.IGNORECASE)

# How many SQL candidates the known-patient fast path pulls before ranking —
# wide enough that metadata-filtered recent/relevant records are never
# missed, narrow enough that retrieve_by_ids() stays cheap.
_CANDIDATE_CAP = 200

_RECORD_TYPE_LABELS = {
    "observation": "Clinical observation",
    "medication": "Medication",
    "condition": "Diagnosis/condition",
    "encounter": "Encounter",
    "claim": "Billing",
    "claim_transaction": "Billing",
    "allergy": "Allergy",
    "procedure": "Procedure",
    "payer": "Payer/insurance",
    "payer_transition": "Payer/insurance",
}

# A SOURCE_n the LLM might cite but that doesn't exist in what was actually
# retrieved (section 78 "LLM response validation") — stripped post-hoc so a
# dangling citation never reaches the user.
_SOURCE_CITATION_RE = re.compile(r"\[SOURCE_(\d+)\]")


@dataclass
class Citation:
    source_id: str
    source_type: str
    record_id: str | None
    file_name: str | None
    page: int | None
    section: str | None
    date: str | None = None
    patient_id: str | None = None  # display id ("P001"), never the raw UUID


@dataclass
class RagResult:
    answer: str
    status: str
    citations: list[Citation]
    retrieved_count: int
    debug: dict | None = None


@dataclass
class RetrievalOutcome:
    status: str  # "OK" | "DENIED" | "NO_AUTHORIZED_CONTEXT"
    sources: list[dict]
    debug: dict
    denial_answer: str | None = None


def resolve_patient_reference(db: Session, question: str, explicit_patient_id: str | None) -> str | None:
    """Resolves a patient reference — the UI's clean Pxxx id (explicit
    field or typed in free text), a raw internal id, or a pasted Synthea
    UUID — to the real internal patient id every other table's FK uses.
    Never relies on the LLM to carry this across a follow-up question: the
    frontend resends the selected patient's id with every message in that
    context (see AssistantPanel's patientId prop), so pronoun follow-ups
    ("what about his allergies?") already resolve correctly here."""
    candidate = explicit_patient_id
    if not candidate:
        match = _DISPLAY_ID_RE.search(question) or _UUID_RE.search(question)
        candidate = match.group(0) if match else None
    if not candidate:
        return None

    if _DISPLAY_ID_RE.fullmatch(candidate):
        patient = db.query(Patient).filter(Patient.display_id == candidate.upper()).first()
        return patient.id if patient else None
    return candidate


def _display_id_for(db: Session, internal_patient_id: str) -> str:
    patient = db.query(Patient).filter(Patient.id == internal_patient_id).first()
    return patient.display_id if patient and patient.display_id else internal_patient_id


def _write_audit_log(db: Session, user: User, question: str, status: str, retrieved_ids: list[str], denial_reason: str | None) -> None:
    db.add(
        AuditLog(
            id=new_uuid(),
            user_id=user.id,
            action="rag_query",
            resource_type="knowledge_record",
            query=question,
            status=status,
            timestamp=datetime.utcnow(),
            metadata_json={"retrieved_ids": retrieved_ids, "denial_reason": denial_reason},
        )
    )
    db.commit()


@dataclass
class _AuthorizedQuery:
    ctx: AuthorizationContext
    intent: QueryIntent
    resolved_patient: str | None
    effective_record_types: list[str]
    debug: dict


def _authorize_and_classify(
    db: Session, user: User, question: str, patient_id: str | None
) -> _AuthorizedQuery | RetrievalOutcome:
    """Authorization + classification shared by every route (structured,
    summary, semantic). Returns a RetrievalOutcome directly when the
    request is denied before any retrieval — the caller just returns that
    outcome rather than touching the database or Qdrant at all."""
    ctx = build_authorization_context(db, user)
    debug: dict = {
        "role": ctx.role.value,
        "allowed_record_types": ctx.allowed_record_types,
        "allowed_sensitivity": ctx.allowed_sensitivity,
        "assigned_patient_ids": ctx.assigned_patient_ids,
    }

    # A patient-scoped role (DOCTOR/NURSE) with zero assignments must never
    # fall through to an unfiltered search — deny before touching anything.
    if ctx.assigned_patient_ids is not None and len(ctx.assigned_patient_ids) == 0:
        return RetrievalOutcome(
            status="NO_AUTHORIZED_CONTEXT",
            sources=[],
            debug=debug,
            denial_answer="You have no assigned patients, so there is no authorized clinical context to answer from.",
        )

    resolved_patient = resolve_patient_reference(db, question, patient_id)
    if resolved_patient and ctx.assigned_patient_ids is not None and resolved_patient not in ctx.assigned_patient_ids:
        # Hard patient-level deny: never reaches structured DB lookup or
        # Qdrant, so the restricted patient's data is provably never
        # retrieved, let alone shown to the LLM.
        debug["detected_patient_id"] = resolved_patient
        return RetrievalOutcome(
            status="DENIED",
            sources=[],
            debug=debug,
            denial_answer="That patient's information is restricted for your role.",
        )

    role_is_clinical = ctx.role in (RoleEnum.DOCTOR, RoleEnum.NURSE, RoleEnum.ADMIN)
    intent = classify_query(question, role_is_clinical)
    debug["query_intent"] = {
        "label": intent.label,
        "record_types": intent.record_types,
        "observation_categories": intent.observation_categories,
        "is_recency": intent.is_recency,
        "intent_kind": intent.intent_kind,
        "route": intent.route,
    }

    # Classification only ever narrows what authorization already allows —
    # it is never allowed to widen it. An explicit intent whose record
    # type(s) don't intersect the role's allowed types is a role-appropriate
    # denial, not an empty-results "try rephrasing" message.
    if intent.record_types is not None:
        effective_record_types = [t for t in intent.record_types if t in ctx.allowed_record_types]
        if not effective_record_types:
            label = _RECORD_TYPE_LABELS.get(intent.record_types[0], intent.label.replace("_", " ").title())
            return RetrievalOutcome(
                status="NO_AUTHORIZED_CONTEXT",
                sources=[],
                debug=debug,
                denial_answer=f"{label} information is not available for your current role.",
            )
    else:
        effective_record_types = ctx.allowed_record_types

    return _AuthorizedQuery(
        ctx=ctx, intent=intent, resolved_patient=resolved_patient, effective_record_types=effective_record_types, debug=debug
    )


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _retrieve_for_known_patient(
    db: Session,
    store,
    query_vector: list[float],
    ctx: AuthorizationContext,
    patient_id: str,
    effective_record_types: list[str],
    intent: QueryIntent,
    debug: dict,
) -> tuple[list[dict], dict]:
    query = db.query(KnowledgeRecord).filter(
        KnowledgeRecord.patient_id == patient_id,
        KnowledgeRecord.record_type.in_(effective_record_types),
        KnowledgeRecord.sensitivity.in_(ctx.allowed_sensitivity),
    )
    # Only meaningful when the classifier narrowed down to observations
    # specifically — an unclassified "tell me about this patient" query
    # still spans every allowed record type and must not be sub-filtered.
    if effective_record_types == ["observation"] and intent.observation_categories:
        query = query.filter(KnowledgeRecord.observation_category.in_(intent.observation_categories))

    if intent.is_recency:
        query = query.order_by(KnowledgeRecord.record_date.desc().nulls_last())
    candidates = query.limit(_CANDIDATE_CAP).all()

    debug["candidate_count"] = len(candidates)
    if not candidates:
        return [], debug

    candidate_ids = [r.id for r in candidates]
    points = store.retrieve_by_ids(candidate_ids)
    vector_by_id = {p.id: p.vector for p in points}

    scored: list[tuple[float, KnowledgeRecord]] = []
    for rank, record in enumerate(candidates):
        vec = vector_by_id.get(record.id)
        relevance = _dot(query_vector, vec) if vec else 0.0
        if intent.is_recency:
            # candidates are already date-sorted; blend relevance with a
            # recency bonus that decays by rank so a highly-relevant but
            # slightly-older record can still edge out the single newest
            # one, instead of recency alone dictating the result (item 10:
            # "relevance + recency", not recency alone).
            recency_bonus = 1.0 - (rank / max(len(candidates), 1))
            score = (0.5 * relevance) + (0.5 * recency_bonus)
        else:
            score = relevance
        scored.append((score, record))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = [record for _, record in scored[: settings.rag_context_k]]
    return [_record_to_source(r) for r in top], debug


def _record_to_source(record: KnowledgeRecord) -> dict:
    return {
        "knowledge_record_id": record.id,
        "source_type": record.source_type,
        "source_document_id": record.source_document_id,
        "source_page": record.source_page,
        "source_section": record.source_section,
        "patient_id": record.patient_id,
        "record_type": record.record_type,
        "content": record.content,
        "observation_category": record.observation_category,
        "record_date": record.record_date.isoformat() if record.record_date else None,
    }


def _format_source_block(index: int, s: dict) -> str:
    lines = [f"[SOURCE_{index}]", s["content"].strip()]
    if s.get("observation_category"):
        lines.append(f"Observation category: {s['observation_category']}")
    return "\n".join(lines)


def _semantic_retrieve(db: Session, aq: _AuthorizedQuery, question: str) -> RetrievalOutcome:
    embedder = get_embedding_provider()
    store = get_vector_store()
    vector = embedder.embed_text(question)

    if aq.resolved_patient:
        # Fast path: qdrant-client's embedded local mode has no real payload
        # indexes (confirmed by its own startup warning), so a filtered
        # search() does a brute-force scan of the whole collection —
        # multiple seconds over 176k points. When the patient is already
        # known, the SQL knowledge_records table (indexed on patient_id,
        # record_type, record_date, observation_category) can find the
        # already-narrowed candidate set directly, and Qdrant's
        # retrieve-by-id is O(k) regardless of collection size.
        sources, debug = _retrieve_for_known_patient(
            db, store, vector, aq.ctx, aq.resolved_patient, aq.effective_record_types, aq.intent, aq.debug
        )
    else:
        query_filter: Filter = build_retrieval_filter(aq.ctx, aq.effective_record_types)
        aq.debug["qdrant_filter"] = str(query_filter)
        hits = store.search(vector, query_filter, settings.rag_top_k, settings.rag_score_threshold)
        sources = [hit.payload for hit in hits][: settings.rag_context_k]
        debug = aq.debug

    if not sources:
        return RetrievalOutcome(
            status="NO_AUTHORIZED_CONTEXT",
            sources=[],
            debug=debug,
            denial_answer="I couldn't find enough authorized information to answer that question.",
        )

    debug["retrieved_ids"] = [s["knowledge_record_id"] for s in sources]
    return RetrievalOutcome(status="OK", sources=sources, debug=debug)


def _validate_citations(answer: str, source_count: int) -> str:
    """Strips any [SOURCE_n] the model cited that wasn't actually in the
    context it was given (section 78 "LLM response validation") — the
    model never gets to invent a source that doesn't exist."""
    def _strip_invalid(match: re.Match) -> str:
        n = int(match.group(1))
        return match.group(0) if 1 <= n <= source_count else ""

    return _SOURCE_CITATION_RE.sub(_strip_invalid, answer)


def _resolve_file_names(db: Session, doc_ids: set[str]) -> dict[str, str]:
    if not doc_ids:
        return {}
    rows = db.query(SourceDocument.id, SourceDocument.file_name).filter(SourceDocument.id.in_(doc_ids)).all()
    return dict(rows)


def _display_ids_for_internal_ids(db: Session, internal_ids: set[str]) -> dict[str, str]:
    if not internal_ids:
        return {}
    rows = db.query(Patient.id, Patient.display_id).filter(Patient.id.in_(internal_ids)).all()
    return {pid: (display or pid) for pid, display in rows}


def _structured_sources_to_citations(db: Session, sources: list, display_id: str) -> list[Citation]:
    doc_ids = {s.source_document_id for s in sources if s.source_document_id}
    file_names = _resolve_file_names(db, doc_ids)
    return [
        Citation(
            source_id=f"SOURCE_{i + 1}",
            source_type=s.source_type,
            record_id=s.record_id,
            file_name=file_names.get(s.source_document_id),
            page=None,
            section=s.record_type,
            date=s.date,
            patient_id=display_id,
        )
        for i, s in enumerate(sources)
    ]


def run_query(db: Session, user: User, question: str, patient_id: str | None = None) -> RagResult:
    authorized = _authorize_and_classify(db, user, question, patient_id)
    if isinstance(authorized, RetrievalOutcome):
        reason = authorized.denial_answer or ""
        _write_audit_log(db, user, question, authorized.status, [], reason)
        return RagResult(answer=authorized.denial_answer or "", status=authorized.status, citations=[], retrieved_count=0, debug=authorized.debug)

    intent = authorized.intent

    # Exact-fact and summary routes never touch Qdrant or the LLM — a
    # deterministic DB lookup can't hallucinate (docs/DECISIONS.md "hybrid
    # RAG"). Only reachable when a specific patient is in context; a
    # structured/summary question with no selected patient falls through to
    # the semantic path below, same as before.
    if authorized.resolved_patient and intent.route in ("structured", "summary"):
        display_id = _display_id_for(db, authorized.resolved_patient)
        if intent.route == "summary":
            structured = structured_answers.answer_summary(
                db, authorized.resolved_patient, display_id, authorized.effective_record_types
            )
        else:
            handler = structured_answers.STRUCTURED_HANDLERS[intent.intent_kind]
            structured = handler(
                db,
                authorized.resolved_patient,
                display_id,
                {"history": intent.history, "categories": intent.observation_categories},
            )

        if structured is None:
            _write_audit_log(db, user, question, "NO_AUTHORIZED_CONTEXT", [], "no structured data available")
            return RagResult(
                answer="I couldn't find enough authorized information to answer that question.",
                status="NO_AUTHORIZED_CONTEXT",
                citations=[],
                retrieved_count=0,
                debug=authorized.debug,
            )

        citations = _structured_sources_to_citations(db, structured.sources, display_id)
        retrieved_ids = [s.record_id for s in structured.sources]
        _write_audit_log(db, user, question, "ANSWERED", retrieved_ids, None)
        return RagResult(
            answer=structured.markdown,
            status="ANSWERED",
            citations=citations,
            retrieved_count=len(structured.sources),
            debug=authorized.debug,
        )

    outcome = _semantic_retrieve(db, authorized, question)
    if outcome.status != "OK":
        reason = outcome.denial_answer or ""
        _write_audit_log(db, user, question, outcome.status, [], reason)
        return RagResult(answer=outcome.denial_answer or "", status=outcome.status, citations=[], retrieved_count=0, debug=outcome.debug)

    sources = outcome.sources
    context_text = "\n\n".join(_format_source_block(i + 1, s) for i, s in enumerate(sources))

    llm = get_llm_provider(sources)
    answer = _validate_citations(llm.generate(context_text, question), len(sources))

    # source_document_id is a SourceDocument FK (a UUID), not a display
    # name — resolve the real file_name in one batch query rather than
    # leaking the raw id into the citation (docs/DECISIONS.md "RAG quality
    # fix", citation display).
    doc_ids = {s["source_document_id"] for s in sources if s.get("source_document_id")}
    file_names = _resolve_file_names(db, doc_ids)
    patient_internal_ids = {s["patient_id"] for s in sources if s.get("patient_id")}
    display_ids = _display_ids_for_internal_ids(db, patient_internal_ids)

    citations = [
        Citation(
            source_id=f"SOURCE_{i+1}",
            source_type=s["source_type"],
            record_id=s.get("knowledge_record_id"),
            file_name=file_names.get(s.get("source_document_id")),
            page=s.get("source_page"),
            section=s.get("source_section") or s.get("record_type"),
            date=s.get("record_date"),
            patient_id=display_ids.get(s.get("patient_id")),
        )
        for i, s in enumerate(sources)
    ]

    retrieved_ids = [s["knowledge_record_id"] for s in sources]
    _write_audit_log(db, user, question, "ANSWERED", retrieved_ids, None)

    return RagResult(answer=answer, status="ANSWERED", citations=citations, retrieved_count=len(sources), debug=outcome.debug)
