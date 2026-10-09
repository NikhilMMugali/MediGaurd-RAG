"""Translates an AuthorizationContext into the Qdrant Filter passed straight
into VectorStore.search(). This is the literal implementation of "authZ
enforcement at the retrieval layer": nothing failing this filter is ever
returned by Qdrant, so app.rag.pipeline never even sees it, let alone the
LLM.
"""
from qdrant_client.models import Filter

from app.authorization.context import AuthorizationContext
from app.services.vector_store import match_value_or_any


def build_retrieval_filter(
    ctx: AuthorizationContext, record_types: list[str] | None = None, source_document_id: str | None = None
) -> Filter:
    # record_types, when given, is query-classification's narrowing of what
    # the role is allowed to see (app.rag.query_classification) — it is
    # always already intersected with ctx.allowed_record_types by the
    # caller, never a widening of it.
    must = [
        match_value_or_any("record_type", record_types if record_types is not None else ctx.allowed_record_types),
        match_value_or_any("sensitivity", ctx.allowed_sensitivity),
    ]
    if ctx.assigned_patient_ids is not None:
        # Patient-scoped role (DOCTOR/NURSE): restrict to assigned patients
        # only. An empty list is handled by the caller before this is ever
        # invoked (see app.rag.pipeline) — it short-circuits to a denial
        # rather than relying on Qdrant to reject an empty MatchAny.
        must.append(match_value_or_any("patient_id", ctx.assigned_patient_ids))
    if source_document_id is not None:
        # Document Intelligence Q&A (app.api.upload::query_document) — scopes
        # retrieval to one document's own chunks on top of every other
        # authorization condition above, never in place of them.
        must.append(match_value_or_any("source_document_id", [source_document_id]))

    return Filter(must=must)
