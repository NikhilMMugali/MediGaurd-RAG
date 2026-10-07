import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column


def new_uuid() -> str:
    return str(uuid.uuid4())


@declarative_mixin
class ProvenanceMixin:
    """Columns shared by every table that can be populated from either the
    Synthea import or a PDF upload, so a fact's origin is always traceable."""

    source_type: Mapped[str] = mapped_column(String(20), default="SYNTHEA", nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
