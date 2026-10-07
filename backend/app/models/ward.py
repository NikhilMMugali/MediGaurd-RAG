from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.provenance import new_uuid


class Ward(Base):
    __tablename__ = "wards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)


class PatientAssignment(Base):
    __tablename__ = "patient_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    patient_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    ward_id: Mapped[str | None] = mapped_column(ForeignKey("wards.id"), nullable=True)
    # e.g. "attending", "consulting", "ward_nurse" — kept free-text for demo flexibility.
    assignment_type: Mapped[str] = mapped_column(String(50), default="attending", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class UserDepartment(Base):
    __tablename__ = "user_departments"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), primary_key=True)
