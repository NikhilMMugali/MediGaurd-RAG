from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.provenance import new_uuid


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Where the original PDF bytes were saved (relative to settings.upload_dir)
    # — never returned to the frontend (section 56 "file storage": a
    # citation can name the file, but the raw filesystem path stays
    # internal). Lets a later source-inspection feature re-open the actual
    # document instead of only ever having its extracted text.
    storage_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="UPLOADED_PDF", nullable=False)
    document_type: Mapped[str | None] = mapped_column(String(50))
    patient_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(20), default="clinical", nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RECEIVED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DocumentACL(Base):
    __tablename__ = "document_acls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"), index=True, nullable=False)
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KnowledgeRecord(Base):
    __tablename__ = "knowledge_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    patient_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    record_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="SYNTHEA", nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_section: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(20), default="clinical", nullable=False)
    # The clinical/financial event date the record is actually about (e.g.
    # Observation.date, Condition.start) — distinct from created_at, which is
    # only when this row was ingested. Lets retrieval rank "recent" queries
    # by what the record describes, not by ingestion order (see
    # app.rag.query_classification).
    record_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # Only populated for record_type == "observation" (Synthea's own
    # category: vital-signs, laboratory, survey, social-history, exam,
    # imaging, procedure, therapy). Lets a "recent observations" query from
    # a clinical role prefer vitals/labs over unrelated social-history
    # survey responses without discarding the latter for other queries.
    observation_category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"), index=True, nullable=False)
    knowledge_record_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_records.id"), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="RECEIVED", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunks_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
