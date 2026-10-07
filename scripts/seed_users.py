"""Seed demo users for each role. Run once the PostgreSQL schema exists.

Usage:
    python scripts/seed_users.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app.models  # noqa: E402,F401  (registers all tables on Base.metadata)
from app.auth.security import hash_password  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models.user import Department, RoleEnum, User  # noqa: E402

DEMO_USERS = [
    ("doctor01", "Dr. Example", RoleEnum.DOCTOR, "Cardiology"),
    ("nurse01", "Nurse Example", RoleEnum.NURSE, "Cardiology"),
    ("finance01", "Finance Example", RoleEnum.FINANCE, None),
    ("reception01", "Reception Example", RoleEnum.RECEPTION, None),
    ("admin01", "Admin Example", RoleEnum.ADMIN, None),
]
DEMO_PASSWORD = "medigaurd123"


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        departments: dict[str, Department] = {}
        for _, _, _, dept_name in DEMO_USERS:
            if dept_name and dept_name not in departments:
                dept = db.query(Department).filter(Department.name == dept_name).first()
                if dept is None:
                    dept = Department(name=dept_name)
                    db.add(dept)
                    db.flush()
                departments[dept_name] = dept

        for username, full_name, role, dept_name in DEMO_USERS:
            existing = db.query(User).filter(User.username == username).first()
            if existing:
                continue
            db.add(
                User(
                    username=username,
                    full_name=full_name,
                    hashed_password=hash_password(DEMO_PASSWORD),
                    role=role,
                    department_id=departments[dept_name].id if dept_name else None,
                )
            )

        db.commit()
        print(f"Seeded {len(DEMO_USERS)} demo users (password: {DEMO_PASSWORD}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
