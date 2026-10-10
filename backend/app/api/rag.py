from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db.session import get_db
from app.models.user import RoleEnum, User
from app.rag.pipeline import run_query
from app.schemas.rag import CitationResponse, RagQueryRequest, RagQueryResponse

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
def rag_query(
    payload: RagQueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagQueryResponse:
    result = run_query(db, user, payload.question, payload.patient_id)

    return RagQueryResponse(
        answer=result.answer,
        status=result.status,
        citations=[
            CitationResponse(
                source_id=c.source_id,
                source_type=c.source_type,
                record_id=c.record_id,
                file_name=c.file_name,
                page=c.page,
                section=c.section,
                date=c.date,
                patient_id=c.patient_id,
                evidence_text=c.evidence_text,
                document_id=c.document_id,
                highlight_text=c.highlight_text,
            )
            for c in result.citations
        ],
        retrieved_count=result.retrieved_count,
        # Debug detail (authorization filter, retrieved ids) is only ever
        # returned to ADMIN — never leaked to the user whose query it is,
        # and never containing restricted content either way.
        debug=result.debug if user.role == RoleEnum.ADMIN else None,
    )
