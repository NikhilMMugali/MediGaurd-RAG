import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class RoleEnum(str, enum.Enum):
    DOCTOR = "DOCTOR"
    NURSE = "NURSE"
    FINANCE = "FINANCE"
    RECEPTION = "RECEPTION"
    ADMIN = "ADMIN"


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # The user's REAL role, stored server-side. This is the only source of truth
    # for authorization — a client-selected role at login is only ever compared
    # against this value and never trusted on its own.
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False)

    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    department: Mapped[Department | None] = relationship()

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
