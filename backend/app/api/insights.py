from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.rag.insights import answer_insight_question, build_overview
from app.schemas.insights import BreakdownResponse, InsightsOverviewResponse, InsightsQueryRequest, InsightsQueryResponse, MetricResponse

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/overview", response_model=InsightsOverviewResponse)
def insights_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> InsightsOverviewResponse:
    overview = build_overview(db, user)
    return InsightsOverviewResponse(
        role=overview.role,
        period=overview.period,
        generated_at=overview.generated_at,
        metrics=[MetricResponse(key=m.key, label=m.label, value=m.value, unit=m.unit) for m in overview.metrics],
        breakdown=BreakdownResponse(label=overview.breakdown.label, items=overview.breakdown.items) if overview.breakdown else None,
        note=overview.note,
    )


@router.post("/query", response_model=InsightsQueryResponse)
def insights_query(
    payload: InsightsQueryRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> InsightsQueryResponse:
    result = answer_insight_question(db, user, payload.question)
    return InsightsQueryResponse(
        answer=result.answer,
        metrics=[MetricResponse(key=m.key, label=m.label, value=m.value, unit=m.unit) for m in result.metrics],
        generated_at=result.generated_at,
    )
