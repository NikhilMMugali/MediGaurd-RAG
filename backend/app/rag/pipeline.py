"""The secure RAG query pipeline (docs/RAG_DESIGN.md):

question -> AuthorizationContext -> Qdrant filter -> embed -> filtered
search -> ONLY authorized chunks -> context assembly -> LLM -> cited
answer -> audit log.

retrieve_authorized_sources() is the one and only place that calls the
vector store for a user query, so the retrieval-time authorization boundary
lives in one spot: build_retrieval_filter() runs before search(), never
after. Both run_query() (chat) and app.api.patients's status endpoint call
this same function, rather than each reimplementing the authorization
check — there is exactly one retrieval-authorization code path in the app.
"""
import re
from dataclasses import dataclass
from datetime import datetime

from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy.orm import Session

from app.authorization.context import build_authorization_context
from app.authorization.qdrant_filter import build_retrieval_filter
from app.config import get_settings
from app.models.documents import AuditLog
from app.models.provenance import new_uuid
from app.models.user import User
from app.services.embedding_provider import get_embedding_provider
from app.services.llm_provider import get_llm_provider
from app.services.vector_store import get_vector_store

settings = get_settings()

# Synthea ids are UUID-formatted; this lets a pasted id in free-text question
# be honored as an explicit patient reference without a separate API field.
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


@dataclass
class Citation:
    source_id: str
    source_type: str
    record_id: str | None
    file_name: str | None
    page: int | None
    section: str | None


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


def _detect_patient_id(question: str, explicit_patient_id: str | None) -> str | None:
    if explicit_patient_id:
        return explicit_patient_id
    match = _UUID_RE.search(question)
    return match.group(0) if match else None


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


def retrieve_authorized_sources(
    db: Session, user: User, question: str, patient_id: str | None = None, audit: bool = True
) -> RetrievalOutcome:
    ctx = build_authorization_context(db, user)
    debug: dict = {
        "role": ctx.role.value,
        "allowed_record_types": ctx.allowed_record_types,
        "allowed_sensitivity": ctx.allowed_sensitivity,
        "assigned_patient_ids": ctx.assigned_patient_ids,
    }

    # A patient-scoped role (DOCTOR/NURSE) with zero assignments must never
    # fall through to an unfiltered search — deny before touching Qdrant.
    if ctx.assigned_patient_ids is not None and len(ctx.assigned_patient_ids) == 0:
        if audit:
            _write_audit_log(db, user, question, "NO_AUTHORIZED_CONTEXT", [], "no patients assigned to this user")
        return RetrievalOutcome(
            status="NO_AUTHORIZED_CONTEXT",
            sources=[],
            debug=debug,
            denial_answer="You have no assigned patients, so there is no authorized clinical context to answer from.",
        )

    detected_patient = _detect_patient_id(question, patient_id)
    if detected_patient and ctx.assigned_patient_ids is not None and detected_patient not in ctx.assigned_patient_ids:
        # Hard patient-level deny: never reaches Qdrant, so the restricted
        # patient's data is provably never retrieved, let alone shown to the LLM.
        if audit:
            _write_audit_log(db, user, question, "DENIED", [], f"patient {detected_patient} not assigned to this user")
        debug["detected_patient_id"] = detected_patient
        return RetrievalOutcome(
            status="DENIED",
            sources=[],
            debug=debug,
            denial_answer="That patient's information is restricted for your role.",
        )

    query_filter: Filter = build_retrieval_filter(ctx)
    if detected_patient:
        query_filter.must.append(FieldCondition(key="patient_id", match=MatchValue(value=detected_patient)))
    debug["qdrant_filter"] = str(query_filter)

    embedder = get_embedding_provider()
    store = get_vector_store()
    vector = embedder.embed_text(question)
    hits = store.search(vector, query_filter, settings.rag_top_k, settings.rag_score_threshold)

    if not hits:
        if audit:
            _write_audit_log(db, user, question, "NO_AUTHORIZED_CONTEXT", [], "no authorized chunks matched the query")
        return RetrievalOutcome(
            status="NO_AUTHORIZED_CONTEXT",
            sources=[],
            debug=debug,
            denial_answer="I couldn't find enough authorized information to answer that question.",
        )

    sources = [hit.payload for hit in hits]
    debug["retrieved_ids"] = [s["knowledge_record_id"] for s in sources]
    return RetrievalOutcome(status="OK", sources=sources, debug=debug)


def run_query(db: Session, user: User, question: str, patient_id: str | None = None) -> RagResult:
    outcome = retrieve_authorized_sources(db, user, question, patient_id, audit=False)

    if outcome.status != "OK":
        reason = outcome.denial_answer or ""
        _write_audit_log(db, user, question, outcome.status, [], reason)
        return RagResult(answer=outcome.denial_answer or "", status=outcome.status, citations=[], retrieved_count=0, debug=outcome.debug)

    sources = outcome.sources
    context_text = "\n\n".join(
        f"[SOURCE_{i+1}]\nType: {s['record_type']}\nPatient: {s.get('patient_id')}\nContent:\n{s['content']}"
        for i, s in enumerate(sources)
    )

    llm = get_llm_provider(sources)
    answer = llm.generate(context_text, question)

    citations = [
        Citation(
            source_id=f"SOURCE_{i+1}",
            source_type=s["source_type"],
            record_id=s.get("knowledge_record_id"),
            file_name=s.get("source_document_id"),
            page=s.get("source_page"),
            section=s.get("source_section") or s.get("record_type"),
        )
        for i, s in enumerate(sources)
    ]

    retrieved_ids = [s["knowledge_record_id"] for s in sources]
    _write_audit_log(db, user, question, "ANSWERED", retrieved_ids, None)

    return RagResult(answer=answer, status="ANSWERED", citations=citations, retrieved_count=len(sources), debug=outcome.debug)
