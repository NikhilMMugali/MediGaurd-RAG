from pydantic import BaseModel


class MetricResponse(BaseModel):
    key: str
    label: str
    value: int | float | str
    unit: str | None = None


class BreakdownResponse(BaseModel):
    label: str
    items: list[tuple[str, int]]


class InsightsOverviewResponse(BaseModel):
    role: str
    period: str
    generated_at: str
    metrics: list[MetricResponse]
    breakdown: BreakdownResponse | None = None
    note: str | None = None


class InsightsQueryRequest(BaseModel):
    question: str


class InsightsQueryResponse(BaseModel):
    answer: str
    metrics: list[MetricResponse]
    generated_at: str
